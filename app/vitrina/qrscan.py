"""Conectarse al WiFi mostrando a la cámara el código QR de la red.

El iPhone (app Contraseñas → Wi-Fi → la red → "Mostrar código QR de la red") y
Android (Ajustes → Wi-Fi → Compartir) muestran un código con el formato
estándar:  WIFI:T:WPA;S:<nombre>;P:<contraseña>;H:false;;

La cámara se lee con ffmpeg (cuadros pequeños) y el código con zbar.
"""

import shutil
import subprocess
import threading
import time

try:
    from pyzbar import pyzbar
    from PIL import Image
    AVAILABLE = True
except Exception:          # noqa: BLE001 (sin libzbar)
    AVAILABLE = False

W, H = 480, 360            # tamaño de los cuadros (la iSight es 4:3)
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


class Scanner:
    """Muestra la cámara y busca un código QR de WiFi. `frame` tiene el último
    cuadro (RGB, W×H) para dibujarlo; `result` se llena al encontrar uno."""

    def __init__(self, device):
        self.frame = None
        self.frame_n = 0
        self.result = None
        self.error = None
        self.seen_other = False     # vio un código QR que no es de WiFi
        self.started = time.monotonic()
        self.log = []               # lo que dice ffmpeg (para el Diagnóstico)
        self._stop = False
        self._proc = None
        ffmpeg = shutil.which("ffmpeg")
        if not (AVAILABLE and ffmpeg and device):
            self.error = "unavailable"
            return
        try:
            # Sin filtros que dependan de la hora de cada cuadro (la iSight manda
            # horas raras y un filtro de "cuadros por segundo" se queda esperando).
            self._proc = subprocess.Popen(
                [ffmpeg, "-v", "warning", "-f", "v4l2", "-i", device,
                 "-vf", f"scale={W}:{H}", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, bufsize=W * H * 3)
        except Exception as exc:       # noqa: BLE001
            self.error = str(exc)
            return
        threading.Thread(target=self._read, daemon=True).start()
        threading.Thread(target=self._decode, daemon=True).start()
        threading.Thread(target=self._stderr, daemon=True).start()

    def _stderr(self):
        global LAST_LOG
        for line in self._proc.stderr:
            text = line.decode("utf-8", "replace").strip()
            if text:
                self.log = (self.log + [text])[-12:]
                LAST_LOG = self.log
                print("cámara:", text, flush=True)

    @property
    def stalled(self):
        """Pasaron unos segundos y la cámara no ha mandado ninguna imagen."""
        return self.frame is None and time.monotonic() - self.started > 8

    def _read(self):
        size = W * H * 3
        out = self._proc.stdout
        while not self._stop:
            buf = out.read(size)
            if not buf or len(buf) < size:
                if not self._stop:
                    self.error = "camera"
                break
            self.frame = buf
            self.frame_n += 1

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
            try:
                self._proc.terminate()
                self._proc.wait(timeout=2)
            except Exception:      # noqa: BLE001
                try:
                    self._proc.kill()
                except Exception:  # noqa: BLE001
                    pass
            self._proc = None
