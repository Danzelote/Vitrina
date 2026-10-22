"""Modo noche: cuándo es de noche (por horario o por la luz del cuarto) y el
brillo real de la pantalla cuando el sistema lo permite.

En la Mac con Vitrina instalado (Linux) se usa el sensor de luz de la Mac y
el brillo de la pantalla; en otras computadoras solo se oscurece la imagen.
"""

import glob
import os
import threading
import time

NEVER, SCHEDULE, LIGHT = "never", "schedule", "light"
SCHEDULES = {"22-7": (22, 7), "23-7": (23, 7), "0-6": (0, 6)}
DIM_TIME = 20 * 60      # se apaga poco a poco en 20 minutos (y amanece igual)
WAKE_TIME = 1.2         # al mover el mouse, despierta en poco más de un segundo
STAY_AWAKE = 120        # tras despertarla, sigue encendida 2 minutos sin uso
REDIM_TIME = 60         # y luego vuelve a apagarse en 1 minuto


def in_schedule(key, t=None):
    """¿La hora local `t` (struct_time) cae dentro del horario nocturno?"""
    start, end = SCHEDULES.get(key, SCHEDULES["23-7"])
    t = t or time.localtime()
    h = t.tm_hour + t.tm_min / 60
    if start < end:
        return start <= h < end
    return h >= start or h < end


class LightSensor:
    """Sensor de luz ambiental. En las MacBook viejas está en applesmc; en
    otras computadoras, en iio. Sin sensor, `available` es False."""

    DARK_SMC = 2         # valores de applesmc (0–255) que cuentan como oscuro
    DARK_LUX = 5         # lux que cuentan como oscuro
    CONFIRM = 60         # segundos seguidos antes de cambiar de opinión

    def __init__(self):
        self.path, self.kind = None, None
        smc = glob.glob("/sys/devices/platform/applesmc.*/light")
        iio = glob.glob("/sys/bus/iio/devices/iio:device*/in_illuminance*_raw") + \
            glob.glob("/sys/bus/iio/devices/iio:device*/in_illuminance*_input")
        if smc:
            self.path, self.kind = smc[0], "smc"
        elif iio:
            self.path, self.kind = iio[0], "iio"
        self.dark = False
        self._since = None
        self._last_read = 0.0

    @property
    def available(self):
        return self.path is not None

    def read(self):
        try:
            with open(self.path) as f:
                raw = f.read().strip()
        except OSError:
            return None
        try:
            if self.kind == "smc":       # "(12,10)": izquierda y derecha
                return max(int(v) for v in raw.strip("()").split(","))
            return float(raw)
        except ValueError:
            return None

    def update(self, now):
        """Lee cada 2 s; cambia de día a noche (o al revés) solo si se mantiene."""
        if not self.available or now - self._last_read < 2.0:
            return self.dark
        self._last_read = now
        v = self.read()
        if v is None:
            return self.dark
        limit = self.DARK_SMC if self.kind == "smc" else self.DARK_LUX
        looks_dark = v <= limit
        if looks_dark == self.dark:
            self._since = None
        elif self._since is None:
            self._since = now
        elif now - self._since >= self.CONFIRM:
            self.dark, self._since = looks_dark, None
        return self.dark


class CameraLight:
    """Sin sensor de luz: usa la cámara (iSight) para saber si el cuarto está a
    oscuras. Toma una foto pequeña cada 30 s, solo mide qué tan clara es y la
    descarta. El foquito verde de la cámara parpadea en cada medición."""

    EVERY = 30
    DARK, LIGHT = 35, 55      # brillo promedio (0–255) con histéresis
    CONFIRM = 2               # mediciones seguidas antes de cambiar de opinión

    def __init__(self):
        import shutil
        self.ffmpeg = shutil.which("ffmpeg")
        self.device = self.find()
        self.kind = "camera"
        self.dark = False
        self._last = -1e9
        self._busy = False
        self._streak = 0
        self.level = None         # última medición (0–255), para mostrarla en Ajustes

    @staticmethod
    def find():
        """La primera cámara que sirve para capturar (/dev/videoN)."""
        for dev in sorted(glob.glob("/dev/video*")):
            n = dev[len("/dev/video"):]
            index = os.path.join("/sys/class/video4linux", f"video{n}", "index")
            try:
                with open(index) as f:
                    if f.read().strip() != "0":      # los demás nodos son de metadatos
                        continue
            except OSError:
                pass
            return dev
        return None

    @property
    def available(self):
        return bool(self.device and self.ffmpeg)

    def _measure(self):
        import subprocess
        try:
            out = subprocess.run(
                [self.ffmpeg, "-v", "error", "-f", "v4l2", "-video_size", "160x120", "-i", self.device,
                 "-vf", "select=eq(n\\,9)", "-frames:v", "1",   # el 10.º cuadro: ya se ajustó la exposición
                 "-f", "rawvideo", "-pix_fmt", "gray", "-"],
                capture_output=True, timeout=20).stdout
            if out:
                frame = out[-160 * 120:]
                level = sum(frame) / len(frame)
                self.level = round(level)
                looks_dark = level < self.DARK if not self.dark else level < self.LIGHT
                if looks_dark != self.dark:
                    self._streak += 1
                    if self._streak >= self.CONFIRM:
                        self.dark, self._streak = looks_dark, 0
                else:
                    self._streak = 0
        except Exception:      # noqa: BLE001
            pass
        finally:
            self._busy = False

    def update(self, now, fast=False):
        """fast: con Ajustes abierto mide cada 3 s, para ver la lectura en vivo."""
        if self.available and not self._busy and now - self._last >= (3 if fast else self.EVERY):
            self._last, self._busy = now, True
            threading.Thread(target=self._measure, daemon=True).start()
        return self.dark


def light_sensor():
    """El sensor de luz de la Mac si tiene; si no, la cámara."""
    s = LightSensor()
    if s.available:
        return s
    cam = CameraLight()
    return cam if cam.available else s


def diagnostics():
    """Lo que la Vitrina encuentra en esta Mac (para revisar sensores y cámara)."""
    import platform

    def read(path):
        try:
            with open(path) as f:
                return f.read().strip()
        except OSError:
            return None
    usb = []
    for d in sorted(glob.glob("/sys/bus/usb/devices/*")):
        prod = read(os.path.join(d, "product"))
        vid, pid = read(os.path.join(d, "idVendor")), read(os.path.join(d, "idProduct"))
        if vid:
            usb.append(f"{vid}:{pid} {prod or ''}".strip())
    return {
        "modelo": read("/sys/class/dmi/id/product_name"),
        "kernel": platform.release(),
        "camaras": {dev: read(f"/sys/class/video4linux/{os.path.basename(dev)}/name")
                    for dev in sorted(glob.glob("/dev/video*"))},
        "uvcvideo_cargado": os.path.exists("/sys/module/uvcvideo"),
        "applesmc": glob.glob("/sys/devices/platform/applesmc.*/*")[:40],
        "sensor_luz": glob.glob("/sys/devices/platform/applesmc.*/light")
        + glob.glob("/sys/bus/iio/devices/iio:device*/in_illuminance*"),
        "brillo": {d: os.access(os.path.join(d, "brightness"), os.W_OK) for d in glob.glob("/sys/class/backlight/*")},
        "usb": usb,
        "grupos": sorted(os.getgroups()),
    }


class Backlight:
    """Brillo real de la pantalla (/sys/class/backlight). Si no se puede
    escribir, no hace nada y la app solo oscurece la imagen."""

    def __init__(self):
        self.dir = None
        for d in sorted(glob.glob("/sys/class/backlight/*")):
            if os.access(os.path.join(d, "brightness"), os.W_OK):
                self.dir = d
                break
        self.max = self._read("max_brightness") or 0
        self.original = self._read("brightness")
        self._last = None
        # Brillo que eligió la persona (teclas de brillo), como fracción del máximo.
        self.user = (self.original / self.max) if self.max and self.original else 1.0
        self.factor = 1.0          # lo que pide el modo noche (1 = normal)

    def change_user(self, step):
        self.user = max(0.06, min(1.0, self.user + step))
        self.set(self.factor)

    @property
    def available(self):
        return self.dir is not None and self.max > 0 and self.original is not None

    def _read(self, name):
        if not self.dir:
            return None
        try:
            with open(os.path.join(self.dir, name)) as f:
                return int(f.read().strip())
        except (OSError, ValueError):
            return None

    def set(self, fraction):
        """fraction 1 = brillo original, 0 = apagada."""
        if not self.available:
            return
        self.factor = fraction
        value = round(self.max * self.user * max(0.0, min(1.0, fraction)))
        if value == self._last:
            return
        try:
            with open(os.path.join(self.dir, "brightness"), "w") as f:
                f.write(str(value))
            self._last = value
        except OSError:
            self.dir = None

    def restore(self):
        if self.available:
            self.set(1.0)
