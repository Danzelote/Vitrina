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
    "media": ("all", "photos", "videos"),
    "locked": (True, False),
    "memories": (True, False),
    "show_info": (True, False),
    "clock": ("off", "12", "24"),
    "shuffle": (True, False),
    "idle_seconds": (10, 15, 30, 60),
    "short_loops": (1, 2, 4, 5),
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
        self.trash_map = {}                   # clave -> Item de la papelera (para sus miniaturas)
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
                     dibuja=self.v.app.gpu, cuadros_por_segundo=self.v.app.meter.fps,
                     cpu_app_pct=self.v.app.meter.app_pct, cpu_mac_pct=self.v.app.meter.mac_pct,
                     programas_pct_de_un_nucleo=self.v.app.meter.top,
                     caras=self.v.app.faces.summary(),
                     ultimos_5s=self.v.app.meter.last, ultima_hora=self.v.app.meter.hour(),
                     nucleo=__import__("vitrina.power", fromlist=["kernel_report"]).kernel_report(),
                     **__import__("vitrina.power", fromlist=["sensors"]).sensors(),
                     trabada=__import__("vitrina.watchdog", fromlist=["REPORTS"]).REPORTS)
            return self.send(200, json.dumps(d, ensure_ascii=False, indent=2), "application/json; charset=utf-8")
        if path == "/api/photos":
            return self.photos()
        if path == "/api/trash":
            return self.trash_list()
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
                  "/api/collections/add": self.add_to_collection, "/api/collections/remove": self.remove_from_collection,
                  "/api/collections/delete": self.delete_collection,
                  "/api/autos/hide": self.hide_auto, "/api/autos/keep": self.keep_auto,
                  "/api/trash/restore": self.trash_restore, "/api/trash/purge": self.trash_purge,
                  "/api/timezone": self.timezone, "/api/update": self.update}
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

    def update(self, data):
        """Buscar o instalar una versión nueva (solo en la Vitrina instalada)."""
        if not self.need_device():
            return
        from .. import updater
        up = self.v.app.updater
        if not updater.available():
            return self.send(400, {"error": "Solo en la Vitrina instalada"})
        if data.get("action") == "apply" and up.state == "new":
            up.apply()
        elif data.get("action") == "check":
            up.check()
        return self.send(200, up.as_dict())

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
            "autos": [{"key": k, "title": g.title, "count": len(g.members), "kind": getattr(g, "auto_kind", "")}
                      for k, g in self.v.app.groups.autos.items()],
            "trash": len(lib.albums.trash),
            "disk": disk,
            "settings": {k: getattr(st, k) for k in SETTINGS},
            "light_sensor": self.v.app.sensor.available,
            "update": dict(self.v.app.updater.as_dict(), available=__import__("vitrina.updater", fromlist=["x"]).available()),
        })

    def photos(self):
        if not self.need_device():
            return
        autos = {}
        for k, g in self.v.app.groups.autos.items():
            for i in g.members:
                if i < len(self.v.app.items):
                    autos.setdefault(self.v.app.items[i].key, []).append(k)
        out = [{"id": it.key, "c": list(it.collections), "a": autos.get(it.key, []),
                "d": it.date.strftime("%Y-%m-%d"), "v": it.is_video,
                "dur": round(it.duration), "r": it.ready, "p": place_of(it)}
               for it in self.v.lib.snapshot if not it.failed]
        self.send(200, out)

    def image(self, kind, key):
        if not self.need_device():
            return
        it = next((it for it in self.v.lib.snapshot if it.key == key), None) or self.v.trash_map.get(key)
        if it is None or not it.ready:
            return self.send(404, {"error": "no existe"})
        self.send_file(it.thumb_path if kind == "t" else it.screen_path, "private, max-age=31536000")

    # -- cambios --------------------------------------------------------------------

    def upload(self):
        if not self.need_device():
            return
        lib = self.v.lib
        name = livelib.safe_name(unquote(self.headers.get("X-Name", "")))
        raw = unquote(self.headers.get("X-Collections", "") or "")
        try:
            cols = [livelib.safe_name(str(c)) for c in json.loads(raw)] if raw else []
        except ValueError:
            cols = []
        one = livelib.safe_name(unquote(self.headers.get("X-Collection", "")))   # celulares con la página vieja
        cols = [c for c in dict.fromkeys(cols + ([one] if one else [])) if c]
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
        target = lib.folder
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
            self.v.dupes.note(dest)
            tell_app(self.v.app, "added", ([dest], cols))
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

    def _lib(self, name, *args):
        """Cambio de la biblioteca: lo hace la interfaz (en su hilo) y aquí se espera."""
        tell_app(self.v.app, "lib", (name, args))

    def delete(self, data):
        if not self.need_device():
            return
        ids = [it.key for it in self._items(data.get("ids"))]
        self._lib("trash_keys", ids)
        self.send(200, {"ok": True, "count": len(ids)})

    def move(self, data):
        """Página vieja del celular: "mover a" = agregar a esa colección."""
        data = dict(data, name=data.get("collection"))
        return self.add_to_collection(data)

    def add_to_collection(self, data):
        if not self.need_device():
            return
        name = livelib.safe_name(str(data.get("name") or ""))
        if not name:
            return self.send(400, {"error": "nombre inválido"})
        self._lib("add_to", [it.key for it in self._items(data.get("ids"))], name)
        self.send(200, {"ok": True})

    def remove_from_collection(self, data):
        if not self.need_device():
            return
        name = str(data.get("name") or "")
        self._lib("remove_from", [it.key for it in self._items(data.get("ids"))], name)
        self.send(200, {"ok": True})

    def create_collection(self, data):
        if not self.need_device():
            return
        name = livelib.safe_name(str(data.get("name") or ""))
        if not name:
            return self.send(400, {"error": "nombre inválido"})
        self._lib("create_collection", name)
        self.send(200, {"ok": True, "name": name})

    def rename_collection(self, data):
        if not self.need_device():
            return
        old = str(data.get("old") or "")
        new = livelib.safe_name(str(data.get("new") or ""))
        names = self.v.lib.albums.names
        if not new or old not in names:
            return self.send(400, {"error": "nombre inválido"})
        if new in names and new != old:
            return self.send(409, {"error": "ya existe"})
        self._lib("rename_collection", old, new)
        self.send(200, {"ok": True})

    def delete_collection(self, data):
        if not self.need_device():
            return
        self._lib("delete_collection", str(data.get("name") or ""))
        self.send(200, {"ok": True})

    def hide_auto(self, data):
        if not self.need_device():
            return
        self._lib("hide_auto", str(data.get("key") or ""))
        self.send(200, {"ok": True})

    def keep_auto(self, data):
        """Una automática se vuelve colección normal (con nombre) y deja de ser automática."""
        if not self.need_device():
            return
        key = str(data.get("key") or "")
        g = self.v.app.groups.autos.get(key)
        name = livelib.safe_name(str(data.get("name") or "")) or (g.title if g else "")
        if not g or not name:
            return self.send(400, {"error": "no existe"})
        keys = [self.v.app.items[i].key for i in g.members if i < len(self.v.app.items)]
        self._lib("keep_auto", key, name, keys)
        self.send(200, {"ok": True, "name": name})

    def trash_list(self):
        if not self.need_device():
            return
        out, tmap = [], {}
        for it, rec in self.v.lib.trash_items():
            tmap[it.key] = it
            out.append({"id": it.key, "v": it.is_video, "d": it.date.strftime("%Y-%m-%d"), "r": it.ready,
                        "days": self.v.lib.albums.days_left(rec), "dur": round(it.duration)})
        self.v.trash_map = tmap
        self.send(200, out)

    def _trash_paths(self, ids):
        ids = set(ids or [])
        return [it.path for k, it in self.v.trash_map.items() if k in ids]

    def trash_restore(self, data):
        if not self.need_device():
            return
        self._lib("restore", self._trash_paths(data.get("ids")))
        self.send(200, {"ok": True})

    def trash_purge(self, data):
        if not self.need_device():
            return
        paths = [p for p, _ in self.v.lib.albums.trash_list()] if data.get("all") else self._trash_paths(data.get("ids"))
        self._lib("purge", paths)
        self.send(200, {"ok": True})

    def settings(self, data):
        if not self.need_device():
            return
        changes = {k: v for k, v in data.items() if k in SETTINGS and v in SETTINGS[k]
                   and not (isinstance(v, bool) and not isinstance(SETTINGS[k][0], bool))}
        if changes:
            tell_app(self.v.app, "settings", changes)
        self.send(200, {"ok": True, "applied": list(changes)})
