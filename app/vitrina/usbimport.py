"""Importar fotos desde una memoria USB conectada a la Mac.

Cada pocos segundos revisa si hay una memoria nueva (con install.sh usb-list,
como root). Si la hay, la abre solo para leer, cuenta fotos y videos y, si
encuentra algo, la app ofrece importarlos. Copia una por una (saltando las
que ya estaban) a la biblioteca, y al final la cierra para poder quitarla.
"""

import os
import secrets
import shutil
import subprocess
import threading
import time

from . import library
from . import livelib

SCRIPT = "/opt/vitrina/install.sh"
SKIP_DIRS = {".Trashes", ".Spotlight-V100", ".fseventsd", ".TemporaryItems", "System Volume Information",
             "$RECYCLE.BIN", "lost+found"}
MAX_FILES = 20000
SCAN_SECONDS = 25


def available():
    return os.path.exists(SCRIPT) and shutil.which("sudo") is not None and \
        os.environ.get("VITRINA_SYSTEM") == "1"


def _run(args, timeout=20):
    try:
        return subprocess.run(["sudo", "-n", SCRIPT] + args, capture_output=True, text=True,
                              timeout=timeout, stdin=subprocess.DEVNULL).stdout
    except Exception:          # noqa: BLE001
        return ""


def scan(root):
    """[(ruta, es_video)] de las fotos y videos de la memoria (sin carpetas del sistema)."""
    found, start = [], time.monotonic()
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if not d.startswith(".") and d not in SKIP_DIRS)
        for name in sorted(filenames):
            if name.startswith("._"):          # copias ocultas que deja macOS en memorias FAT
                continue
            kind = library.media_kind(name)
            if kind:
                found.append((os.path.join(dirpath, name), kind == "video"))
        if len(found) >= MAX_FILES or time.monotonic() - start > SCAN_SECONDS:
            break
    return found


def safe_label(label):
    label = (label or "").replace("\\x20", " ").strip()
    return label[:40] or "USB"


class UsbImport:
    """Estado (lo lee la interfaz): offer = memoria con fotos esperando respuesta;
    job = importación en curso o terminada."""

    def __init__(self, app):
        self.app = app
        self.offer = None       # {"dev", "label", "mount", "files", "photos", "videos"}
        self.job = None         # {"done", "total", "added", "dupes", "finished", "error", "dev"}
        self.known = set()      # memorias ya vistas (no se vuelve a preguntar hasta que se quite)
        self._stop = False
        if available():
            threading.Thread(target=self._watch, daemon=True).start()

    def _watch(self):
        while not self._stop:
            time.sleep(3)
            try:
                self._poll()
            except Exception as exc:       # noqa: BLE001
                print("USB:", exc, flush=True)

    def _poll(self):
        devs = {}
        for line in _run(["usb-list"]).splitlines():
            parts = line.split(" ", 3)
            if len(parts) >= 3 and parts[0] == "USB":
                devs[parts[1]] = safe_label(parts[3] if len(parts) > 3 else "")
        # Se quitó: se olvida (y si estaba ofrecida, se retira la oferta).
        for dev in list(self.known):
            if dev not in devs:
                self.known.discard(dev)
                if self.offer and self.offer["dev"] == dev:
                    self.offer = None
                if self.job and self.job["dev"] == dev and not self.job["finished"]:
                    self.job["error"] = "La memoria se quitó antes de terminar"
        for dev, label in devs.items():
            if dev in self.known or self.offer or (self.job and not self.job["finished"]):
                continue
            self.known.add(dev)
            out = _run(["usb-mount", dev])
            if "MOUNT " not in out:
                continue
            mount = out.split("MOUNT ", 1)[1].strip()
            files = scan(mount)
            if not files:
                _run(["usb-umount", dev])
                continue
            videos = sum(1 for _, v in files if v)
            self.offer = {"dev": dev, "label": label, "mount": mount, "files": files,
                          "photos": len(files) - videos, "videos": videos, "into_collection": True}

    def decline(self):
        offer, self.offer = self.offer, None
        if offer:
            threading.Thread(target=_run, args=(["usb-umount", offer["dev"]],), daemon=True).start()

    def start(self):
        offer, self.offer = self.offer, None
        if not offer:
            return
        self.job = {"dev": offer["dev"], "label": offer["label"], "done": 0, "total": len(offer["files"]),
                    "added": 0, "dupes": 0, "finished": False, "error": None}
        threading.Thread(target=self._import, args=(offer,), daemon=True).start()

    def _import(self, offer):
        job = self.job
        app = self.app
        lib = app.lib
        web = getattr(app, "web", None)
        v = getattr(web, "v", None)
        try:
            collection = offer["label"] if offer["into_collection"] else ""
            target = livelib.collection_dir(lib.folder, collection)
            tmp_dir = os.path.join(lib.folder, ".subiendo")
            os.makedirs(tmp_dir, exist_ok=True)
            batch = []
            for path, _is_video in offer["files"]:
                if job["error"]:
                    break
                name = os.path.basename(path)
                tmp = os.path.join(tmp_dir, secrets.token_hex(8) + "_" + name)
                try:
                    shutil.copy2(path, tmp)
                except OSError as exc:
                    if not os.path.exists(offer["mount"]) or not os.path.ismount(offer["mount"]):
                        job["error"] = "La memoria se quitó antes de terminar"
                        break
                    print("USB: no se pudo copiar", path, exc, flush=True)
                    job["done"] += 1
                    continue
                lock = v.upload_lock if v else threading.Lock()
                with lock:
                    twin = None
                    if v is not None:
                        try:
                            twin = v.dupes.find(tmp)
                        except Exception:      # noqa: BLE001
                            twin = None
                    if twin is not None:
                        os.remove(tmp)
                        job["dupes"] += 1
                    else:
                        dest = livelib.unique_path(os.path.join(target, name))
                        os.replace(tmp, dest)
                        if v is not None:
                            v.dupes.note(dest)
                        batch.append(dest)
                        job["added"] += 1
                job["done"] += 1
                if len(batch) >= 8:
                    self._tell(batch)
                    batch = []
            if batch:
                self._tell(batch)
        except Exception as exc:       # noqa: BLE001
            job["error"] = str(exc)
        finally:
            _run(["usb-umount", offer["dev"]])
            job["finished"] = True

    def _tell(self, paths):
        done = threading.Event()
        self.app.events.put(("added", list(paths), done))
        done.wait(10)
