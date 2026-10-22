"""Servidor web de Vitrina: la app del celular.

Corre en un hilo aparte y sirve una página (static/) por el WiFi de la casa.
Para entrar hay que emparejar el celular escaneando el código QR que muestra
la Mac: el QR lleva un código temporal y el celular recibe una cookie que lo
identifica desde entonces. Los celulares emparejados se pueden quitar desde la
Mac o desde el propio celular.

Lo que cambia la biblioteca (subir, mover, borrar) se hace en disco aquí y se
avisa a la interfaz por `app.events`; los ajustes también se mandan así, para
que todo lo de la interfaz ocurra en su propio hilo.
"""

import hashlib
import json
import os
import secrets
import shutil
import socket
import threading
import time
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, unquote, urlparse

from .. import __version__
from .. import config as C
from .. import library
from .. import livelib
from .. import qrscan as QRSCAN
from ..dupes import Dupes
from ..places import place_of
from ..settings import config_dir

STATIC = os.path.join(os.path.dirname(__file__), "static")
FONTS = os.path.join(os.path.dirname(os.path.dirname(__file__)), "fonts")
PORTS = [8642, 8643, 8644, 8645, 8080, 8081]
PAIR_MINUTES = 15
COOKIE = "vitrina"
TYPES = {".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8",
         ".css": "text/css; charset=utf-8", ".json": "application/json", ".png": "image/png",
         ".svg": "image/svg+xml", ".ttf": "font/ttf", ".jpg": "image/jpeg", ".webmanifest": "application/manifest+json"}

# Ajustes que se pueden cambiar desde el celular y sus valores válidos.
SETTINGS = {
    "kenburns": ("off", "zoom", "pan"),
    "memories": (True, False),
    "show_info": (True, False),
    "clock": ("off", "12", "24"),
    "shuffle": (True, False),
    "idle_seconds": (10, 15, 30, 60),
    "language": ("es", "en"),
    "theme": ("light", "dark", "auto"),
    "night": ("never", "schedule"),
    "auto_brightness": (True, False),
    "night_hours": ("22-7", "23-7", "0-6"),
    "night_style": ("off", "window", "classic"),
    "night_color": ("white", "blue", "red"),
}


def lan_ip():
    """La dirección de la Mac en la red de la casa (None si no hay red)."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))   # no envía nada; solo elige la interfaz
        ip = s.getsockname()[0]
    except OSError:
        ip = None
    finally:
        s.close()
    return None if not ip or ip.startswith("127.") else ip


def device_name(agent):
    a = agent or ""
    for key, name in (("iPhone", "iPhone"), ("iPad", "iPad"), ("Android", "Android"),
                      ("Macintosh", "Mac"), ("Windows", "Windows")):
        if key in a:
            return name
    return "Navegador"


class Devices:
    """Celulares emparejados. Se guarda solo una huella del token, no el token."""

    def __init__(self):
        self.path = os.path.join(config_dir(), "devices.json")
        self.lock = threading.Lock()
        try:
            with open(self.path) as f:
                self.data = json.load(f)
        except Exception:
            self.data = {}

    @staticmethod
    def _hash(token):
        return hashlib.sha256(token.encode()).hexdigest()

    def _save(self):
        tmp = self.path + ".tmp"
        with open(tmp, "w") as f:
            json.dump(self.data, f, indent=1)
        os.replace(tmp, self.path)

    def add(self, name):
        token = secrets.token_urlsafe(32)
        now = time.time()
        with self.lock:
            self.data[self._hash(token)] = {"name": name, "added": now, "seen": now}
            self._save()
        return token

    def check(self, token):
        if not token:
            return None
        h = self._hash(token)
        with self.lock:
            d = self.data.get(h)
            if d is None:
                return None
            if time.time() - d.get("seen", 0) > 600:
                d["seen"] = time.time()
                self._save()
        return h

    def remove(self, h):
        with self.lock:
            if self.data.pop(h, None) is not None:
                self._save()

    def listing(self):
        """[(huella, nombre, agregado)] del más reciente al más viejo."""
        with self.lock:
            return sorted(((h, d["name"], d["added"]) for h, d in self.data.items()), key=lambda x: -x[2])


class WebServer:
    def __init__(self, app, lib):
        self.app, self.lib = app, lib
        self.devices = Devices()
        self.dupes = Dupes(lib)
        self.upload_lock = threading.Lock()   # revisar repetidas y agregar, de una en una
        self.code, self.code_until = None, 0.0
        self.httpd = None
        for port in PORTS:
            try:
                self.httpd = ThreadingHTTPServer(("0.0.0.0", port), Handler)
                break
            except OSError:
                continue
        if self.httpd is None:
            raise OSError("no hay puerto libre para el servidor web")
        self.httpd.daemon_threads = True
        self.httpd.vitrina = self
        self.port = self.httpd.server_address[1]
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def base_url(self):
        ip = lan_ip()
        return f"http://{ip}:{self.port}" if ip else None

    def pair_url(self):
        """Dirección del QR, con un código que cambia cada 15 minutos."""
        base = self.base_url()
        if not base:
            return None
        if not self.code or time.time() > self.code_until:
            self.code = secrets.token_urlsafe(6)
            self.code_until = time.time() + PAIR_MINUTES * 60
        return f"{base}/p/{self.code}"

    def close(self):
        try:
            self.httpd.shutdown()
            self.httpd.server_close()
        except Exception:
            pass


def tell_app(app, kind, data, wait=3.0):
    """Avisa a la interfaz y espera a que lo aplique (así la siguiente
    petición ya ve la biblioteca actualizada)."""
    done = threading.Event()
    app.events.put((kind, data, done))
    done.wait(wait)


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "Vitrina"

    def log_message(self, *args):   # sin ruido en la terminal
        pass

    @property
    def v(self):
        return self.server.vitrina

    # -- respuestas -----------------------------------------------------------------

    def send(self, code, body=b"", ctype="application/json", headers=None):
        if isinstance(body, (dict, list)):
            body = json.dumps(body, ensure_ascii=False).encode()
        elif isinstance(body, str):
            body = body.encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        for k, val in (headers or {}).items():
            self.send_header(k, val)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def send_file(self, path, cache="no-cache"):
        try:
            with open(path, "rb") as f:
                data = f.read()
        except OSError:
            return self.send(404, {"error": "no existe"})
        ctype = TYPES.get(os.path.splitext(path)[1].lower(), "application/octet-stream")
        self.send(200, data, ctype, {"Cache-Control": cache})

    def redirect(self, to, headers=None):
        h = {"Location": to}
        h.update(headers or {})
        self.send(302, b"", "text/plain", h)

    # -- emparejamiento --------------------------------------------------------------

    def token(self):
        c = SimpleCookie(self.headers.get("Cookie", ""))
        return c[COOKIE].value if COOKIE in c else None

    def device(self):
        return self.v.devices.check(self.token())

    def need_device(self):
        h = self.device()
        if not h:
            self.send(401, {"error": "sin emparejar"})
        return h

    # -- rutas ------------------------------------------------------------------------

    def do_HEAD(self):
        self.do_GET()

    def do_GET(self):
        url = urlparse(self.path)
        path = unquote(url.path)
        if path in ("/", "/index.html"):
            return self.send_file(os.path.join(STATIC, "index.html"))
        if path in ("/app.js", "/style.css", "/manifest.webmanifest", "/icon.png"):
            return self.send_file(os.path.join(STATIC, path[1:]))
        if path.startswith("/fonts/"):
            name = os.path.basename(path)
            if name.startswith("Inter-") and name.endswith(".ttf"):
                return self.send_file(os.path.join(FONTS, name), "max-age=31536000")
            return self.send(404, {"error": "no existe"})
        if path.startswith("/p/"):
            return self.pair(path[3:])
        if path == "/api/me":
            return self.send(200, {"paired": bool(self.device()), "language": self.v.app.settings.language,
                                   "version": __version__})
        if path == "/api/info":
            return self.info()
        if path == "/api/diag":
            if not self.need_device():
                return
            from ..night import diagnostics
            from .. import config as C2
            d = diagnostics()
            d.update(version=__version__, ligero=C2.LIGHT, sensor_en_uso=type(self.v.app.sensor).__name__,
                     sensor_disponible=self.v.app.sensor.available,
                     luz=getattr(self.v.app.sensor, "level", None),
                     exposicion_manual=getattr(self.v.app.sensor, "manual_exposure", None),
                     brillo_minimo=self.v.app.settings.min_brightness,
                     brillo_maximo_raw=self.v.app.backlight.max,
                     camara_qr=QRSCAN.LAST_LOG,
                     trabada=__import__("vitrina.watchdog", fromlist=["REPORTS"]).REPORTS)
            return self.send(200, json.dumps(d, ensure_ascii=False, indent=2), "application/json; charset=utf-8")
        if path == "/api/photos":
            return self.photos()
        if path.startswith("/t/") or path.startswith("/s/"):
            return self.image(path[1], os.path.splitext(os.path.basename(path))[0])
        self.send(404, {"error": "no existe"})

    def do_POST(self):
        path = urlparse(self.path).path
        if path == "/api/upload":
            return self.upload()
        try:
            n = int(self.headers.get("Content-Length") or 0)
            data = json.loads(self.rfile.read(n) or b"{}") if n < 1_000_000 else {}
        except (ValueError, json.JSONDecodeError):
            return self.send(400, {"error": "datos inválidos"})
        routes = {"/api/delete": self.delete, "/api/move": self.move, "/api/settings": self.settings,
                  "/api/collections/create": self.create_collection,
                  "/api/collections/rename": self.rename_collection, "/api/unpair": self.unpair,
                  "/api/timezone": self.timezone}
        fn = routes.get(path)
        if not fn:
            return self.send(404, {"error": "no existe"})
        fn(data)

    def pair(self, code):
        v = self.v
        if not code or code != v.code or time.time() > v.code_until:
            return self.redirect("/?vencido=1")
        token = v.devices.add(device_name(self.headers.get("User-Agent")))
        cookie = f"{COOKIE}={token}; Max-Age=315360000; Path=/; HttpOnly; SameSite=Lax"
        return self.redirect("/", {"Set-Cookie": cookie})

    def timezone(self, data):
        """El celular dice su zona horaria; la Vitrina (en la USB) la toma para su reloj."""
        if not self.need_device():
            return
        from ..wifi import set_timezone
        if set_timezone(str(data.get("tz") or "")):
            tell_app(self.v.app, "tzset", None)
        self.send(200, {"ok": True})

    def unpair(self, _data):
        h = self.device()
        if h:
            self.v.devices.remove(h)
        self.send(200, {"ok": True}, headers={"Set-Cookie": f"{COOKIE}=; Max-Age=0; Path=/"})

    # -- lectura ------------------------------------------------------------------------

    def info(self):
        if not self.need_device():
            return
        lib, st = self.v.lib, self.v.app.settings
        items = lib.snapshot
        try:
            du = shutil.disk_usage(lib.folder)
            disk = {"free": du.free, "total": du.total}
        except OSError:
            disk = None
        self.send(200, {
            "version": __version__,
            "photos": sum(1 for it in items if not it.is_video),
            "videos": sum(1 for it in items if it.is_video),
            "collections": [{"name": n, "count": c} for n, c in lib.collections()],
            "disk": disk,
            "settings": {k: getattr(st, k) for k in SETTINGS},
            "light_sensor": self.v.app.sensor.available,
        })

    def photos(self):
        if not self.need_device():
            return
        out = [{"id": it.key, "c": it.collection, "d": it.date.strftime("%Y-%m-%d"), "v": it.is_video,
                "dur": round(it.duration), "r": it.ready, "p": place_of(it)}
               for it in self.v.lib.snapshot if not it.failed]
        self.send(200, out)

    def image(self, kind, key):
        if not self.need_device():
            return
        it = next((it for it in self.v.lib.snapshot if it.key == key), None)
        if it is None or not it.ready:
            return self.send(404, {"error": "no existe"})
        self.send_file(it.thumb_path if kind == "t" else it.screen_path, "private, max-age=31536000")

    # -- cambios --------------------------------------------------------------------

    def upload(self):
        if not self.need_device():
            return
        lib = self.v.lib
        name = livelib.safe_name(unquote(self.headers.get("X-Name", "")))
        collection = livelib.safe_name(unquote(self.headers.get("X-Collection", "")))
        try:
            size = int(self.headers.get("Content-Length") or 0)
            modified = int(self.headers.get("X-Modified") or 0) / 1000
        except ValueError:
            return self.send(400, {"error": "datos inválidos"})
        if not name or size <= 0 or library.media_kind(name) is None:
            self.discard(size)
            return self.send(415, {"status": "unsupported"})
        if modified and library.item_key(name, size, modified) in {it.key for it in lib.snapshot}:
            self.discard(size)
            return self.send(200, {"status": "duplicate"})
        target = livelib.collection_dir(lib.folder, collection)
        tmp_dir = os.path.join(lib.folder, ".subiendo")
        os.makedirs(tmp_dir, exist_ok=True)
        tmp = os.path.join(tmp_dir, secrets.token_hex(8) + "_" + name)
        left = size
        try:
            with open(tmp, "wb") as f:
                while left > 0:
                    chunk = self.rfile.read(min(1 << 20, left))
                    if not chunk:
                        raise ConnectionError("se cortó la subida")
                    f.write(chunk)
                    left -= len(chunk)
            if modified:
                os.utime(tmp, (modified, modified))
        except Exception:
            try:
                os.remove(tmp)
            except OSError:
                pass
            return self.send(500, {"status": "error"})
        # Si dos celulares suben la misma foto a la vez, la segunda ya ve a la primera.
        with self.v.upload_lock:
            try:
                twin = self.v.dupes.find(tmp)
            except Exception:
                twin = None
            if twin is not None:
                os.remove(tmp)
                return self.send(200, {"status": "duplicate"})
            dest = livelib.unique_path(os.path.join(target, name))
            os.replace(tmp, dest)
            tell_app(self.v.app, "added", [dest])
        self.send(200, {"status": "added"})

    def discard(self, size):
        left = size
        while left > 0:
            chunk = self.rfile.read(min(1 << 20, left))
            if not chunk:
                break
            left -= len(chunk)

    def _items(self, ids):
        ids = set(ids or [])
        return [it for it in self.v.lib.snapshot if it.key in ids]

    def delete(self, data):
        if not self.need_device():
            return
        gone = []
        for it in self._items(data.get("ids")):
            try:
                livelib.to_trash(self.v.lib.folder, it.path)
                gone.append(it.path)
            except OSError:
                pass
        tell_app(self.v.app, "removed", gone)
        self.send(200, {"ok": True, "count": len(gone)})

    def move(self, data):
        if not self.need_device():
            return
        lib = self.v.lib
        collection = livelib.safe_name(str(data.get("collection") or ""))
        target = livelib.collection_dir(lib.folder, collection)
        pairs = []
        for it in self._items(data.get("ids")):
            if it.collection == collection:
                continue
            dest = livelib.unique_path(os.path.join(target, os.path.basename(it.path)))
            try:
                shutil.move(it.path, dest)
                pairs.append((it.path, dest))
            except OSError:
                pass
        tell_app(self.v.app, "moved", pairs)
        self.send(200, {"ok": True, "count": len(pairs)})

    def create_collection(self, data):
        if not self.need_device():
            return
        name = livelib.safe_name(str(data.get("name") or ""))
        if not name:
            return self.send(400, {"error": "nombre inválido"})
        livelib.collection_dir(self.v.lib.folder, name)
        self.send(200, {"ok": True, "name": name})

    def rename_collection(self, data):
        if not self.need_device():
            return
        folder = self.v.lib.folder
        old = livelib.safe_name(str(data.get("old") or ""))
        new = livelib.safe_name(str(data.get("new") or ""))
        src, dst = os.path.join(folder, old), os.path.join(folder, new)
        if not old or not new or not os.path.isdir(src):
            return self.send(400, {"error": "nombre inválido"})
        if os.path.exists(dst):
            return self.send(409, {"error": "ya existe"})
        os.rename(src, dst)
        tell_app(self.v.app, "renamed", (old, new))
        self.send(200, {"ok": True})

    def settings(self, data):
        if not self.need_device():
            return
        changes = {k: v for k, v in data.items() if k in SETTINGS and v in SETTINGS[k]
                   and not (isinstance(v, bool) and not isinstance(SETTINGS[k][0], bool))}
        if changes:
            tell_app(self.v.app, "settings", changes)
        self.send(200, {"ok": True, "applied": list(changes)})
