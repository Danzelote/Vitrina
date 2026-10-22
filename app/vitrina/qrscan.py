"""Conectarse al WiFi mostrando a la cámara el código QR de la red.

El iPhone (app Contraseñas → Wi-Fi → la red → "Mostrar código QR de la red") y
Android (Ajustes → Wi-Fi → Compartir) muestran un código con el formato
estándar:  WIFI:T:WPA;S:<nombre>;P:<contraseña>;H:false;;

La cámara se lee con ffmpeg (cuadros pequeños) y el código con zbar.
"""

import os
import shutil
import signal
import subprocess
import threading
import time

try:
    from pyzbar import pyzbar
    from PIL import Image
    AVAILABLE = True
except Exception:          # noqa: BLE001 (sin libzbar)
    AVAILABLE = False

W, H = 320, 240            # tamaño de los cuadros (la iSight es 4:3)
LAST_LOG = []              # últimos mensajes de la cámara (para el Diagnóstico)


def parse_wifi(text):
    """'WIFI:S:Casa;T:WPA;P:secreto;;' -> {"ssid", "password", "hidden"} o None."""
    if not text or not text.upper().startswith("WIFI:"):
        return None
    fields, key, cur, esc = {}, None, "", False
    body = text[5:]
    i = 0
    while i < len(body):
        ch = body[i]
        if esc:
            cur += ch
            esc = False
        elif ch == "\\":
            esc = True
        elif key is None and ch == ":":
            key, cur = cur.upper(), ""
        elif ch == ";":
            if key is not None:
                fields[key] = cur
            key, cur = None, ""
        else:
            cur += ch
        i += 1
    if key is not None:
        fields[key] = cur
    ssid = fields.get("S")
    if not ssid:
        return None
    kind = fields.get("T", "").upper()
    password = "" if kind == "NOPASS" else fields.get("P", "")
    return {"ssid": ssid, "password": password, "hidden": fields.get("H", "").lower() == "true"}


def _kill(proc):
    """Cierra ffmpeg (y lo que haya abierto) sin esperar."""
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except Exception:          # noqa: BLE001
        try:
            proc.kill()
        except Exception:      # noqa: BLE001
            pass
    try:
        proc.wait(timeout=2)
    except Exception:          # noqa: BLE001
        pass


class Scanner:
    """Muestra la cámara y busca un código QR de WiFi. `frame` tiene el último
    cuadro (RGB, W×H) para dibujarlo; `result` se llena al encontrar uno.

    La iSight de las MacBook manda muchos cuadros incompletos (les faltan unos
    bytes) y ffmpeg los descarta. A 320×240 llegan completos mucho más seguido.
    Si aun así el video se traba, se cambia a "fotos seguidas": una foto cada
    vez (como la medición de luz, que sí funciona)."""

    SIZE = "320x240"

    def __init__(self, device):
        self.frame = None
        self.frame_n = 0
        self.result = None
        self.error = None
        self.seen_other = False     # vio un código QR que no es de WiFi
        self.started = time.monotonic()
        self.last_frame_at = None
        self.mode = "video"
        self.log = []               # lo que dice ffmpeg (para el Diagnóstico)
        self._stop = False
        self._proc = None
        self.device = device
        self.ffmpeg = shutil.which("ffmpeg")
        if not (AVAILABLE and self.ffmpeg and device):
            self.error = "unavailable"
            return
        threading.Thread(target=self._run, daemon=True).start()
        threading.Thread(target=self._decode, daemon=True).start()

    # -- registro -----------------------------------------------------------------

    def _note(self, text):
        global LAST_LOG
        if text and (not self.log or self.log[-1] != text):
            self.log = (self.log + [text])[-12:]
            LAST_LOG = self.log
            print("cámara:", text, flush=True)

    def _stderr(self, proc):
        for line in proc.stderr:
            self._note(line.decode("utf-8", "replace").strip()[:200])

    def _got(self, buf):
        self.frame = buf
        self.frame_n += 1
        self.last_frame_at = time.monotonic()

    @property
    def stalled(self):
        """Pasaron unos segundos y la cámara no ha mandado ninguna imagen."""
        return self.frame is None and time.monotonic() - self.started > 12

    # -- captura ------------------------------------------------------------------

    def _cmd(self, size, extra):
        args = [self.ffmpeg, "-v", "warning", "-f", "v4l2"]
        if size:
            args += ["-video_size", size]
        return args + ["-i", self.device] + extra + ["-f", "rawvideo", "-pix_fmt", "rgb24", "-"]

    def _run(self):
        if not self._video():
            self.mode = "fotos"
            self._note("se cambia a fotos seguidas")
            self._snapshots()

    def _video(self):
        """Video continuo. Devuelve False si se traba (para cambiar de modo)."""
        try:
            proc = subprocess.Popen(self._cmd(self.SIZE, ["-vf", f"scale={W}:{H}"]),
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, bufsize=W * H * 3,
                                    start_new_session=True)
        except Exception as exc:       # noqa: BLE001
            self._note(str(exc))
            return False
        self._proc = proc
        threading.Thread(target=self._stderr, args=(proc,), daemon=True).start()
        stuck = {"v": False}

        def watchdog():
            while not self._stop and proc.poll() is None:
                time.sleep(0.25)
                now = time.monotonic()
                last = self.last_frame_at or self.started
                limit = 2.0 if self.last_frame_at else 5.0
                if now - last > limit:
                    stuck["v"] = True
                    _kill(proc)
                    return
        threading.Thread(target=watchdog, daemon=True).start()
        size = W * H * 3
        while not self._stop:
            buf = proc.stdout.read(size)
            if not buf or len(buf) < size:
                break
            self._got(buf)
        _kill(proc)
        return self._stop

    def _snapshots(self):
        size_n = W * H * 3
        fails = 0
        sizes = [self.SIZE, None]           # si 320×240 no funciona, el tamaño normal
        while not self._stop and self.result is None:
            size = sizes[0]
            try:
                proc = subprocess.Popen(
                    self._cmd(size, ["-vf", f"select=gte(n\\,2),scale={W}:{H}", "-frames:v", "1"]),
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True)
                self._proc = proc
                out, err = proc.communicate(timeout=10)
            except Exception as exc:       # noqa: BLE001
                out, err = b"", str(exc).encode()
                _kill(proc)
            if self._stop:
                break
            if len(out) >= size_n:
                self._got(out[-size_n:])
                fails = 0
            else:
                fails += 1
                self._note(err.decode("utf-8", "replace").strip().splitlines()[-1][:200] if err else "sin imagen")
                if fails >= 2 and len(sizes) > 1:
                    sizes.pop(0)
                    fails = 0
                elif fails >= 6:
                    self.error = "camera"
                    break
                time.sleep(0.3)

    def _decode(self):
        done = -1
        while not self._stop and self.result is None:
            if self.frame is None or self.frame_n == done:
                time.sleep(0.05)
                continue
            done = self.frame_n
            try:
                img = Image.frombytes("RGB", (W, H), self.frame).convert("L")
                for code in pyzbar.decode(img, symbols=[pyzbar.ZBarSymbol.QRCODE]):
                    text = code.data.decode("utf-8", "replace")
                    wifi = parse_wifi(text)
                    if wifi:
                        self.result = wifi
                        break
                    self.seen_other = True
            except Exception:      # noqa: BLE001
                time.sleep(0.2)

    def close(self):
        self._stop = True
        if self._proc:
            _kill(self._proc)
            self._proc = None
