"""Modo noche: cuándo es de noche (por horario o por la luz del cuarto) y el
brillo real de la pantalla cuando el sistema lo permite.

En la Mac con Vitrina instalado (Linux) se usa el sensor de luz de la Mac y
el brillo de la pantalla; en otras computadoras solo se oscurece la imagen.
"""

import glob
import math
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
    """Sensor de luz ambiental. En las MacBook con teclado iluminado está en
    applesmc; en otras computadoras, en iio. Sin sensor, `available` es False."""

    def __init__(self):
        self.path, self.kind = None, None
        smc = glob.glob("/sys/devices/platform/applesmc.*/light")
        iio = glob.glob("/sys/bus/iio/devices/iio:device*/in_illuminance*_raw") + \
            glob.glob("/sys/bus/iio/devices/iio:device*/in_illuminance*_input")
        if smc:
            self.path, self.kind = smc[0], "smc"
        elif iio:
            self.path, self.kind = iio[0], "iio"
        self.level = None
        self._last_read = -1e9

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

    def update(self, now, fast=False):
        if self.available and now - self._last_read >= 2.0:
            self._last_read = now
            v = self.read()
            if v is not None:
                self.level = round(v)

    def ambient(self):
        """Luz del cuarto de 0 (oscuro) a 1 (muy iluminado), o None."""
        if self.level is None:
            return None
        top = 120 if self.kind == "smc" else 400       # applesmc 0–255 · lux
        return max(0.0, min(1.0, math.log1p(self.level) / math.log1p(top)))


class CameraLight:
    """Sin sensor de luz: usa la cámara (iSight) para medir la luz del cuarto.
    Toma una foto pequeña de vez en cuando, solo mide qué tan clara es y la
    descarta. El foquito verde de la cámara parpadea en cada medición.

    La exposición se fija a mano: si la cámara la ajustara sola, un cuarto
    oscuro se vería casi igual de claro que uno iluminado."""

    EVERY = 20

    def __init__(self):
        import shutil
        self.ffmpeg = shutil.which("ffmpeg")
        self.v4l2ctl = shutil.which("v4l2-ctl")
        self.device = self.find()
        self.kind = "camera"
        self._last = -1e9
        self._busy = False
        self.paused = False       # mientras se usa la cámara para otra cosa (código QR del WiFi)
        self.level = None         # última medición (0–255), para mostrarla en Ajustes
        self.manual_exposure = None

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

    def _fix_exposure(self):
        """Exposición y ganancia fijas (valores de fábrica de la cámara)."""
        import subprocess
        if not self.v4l2ctl:
            return
        try:
            out = subprocess.run([self.v4l2ctl, "-d", self.device, "-l"], capture_output=True,
                                 text=True, timeout=5).stdout
        except Exception:      # noqa: BLE001
            return
        controls = {}
        for line in out.splitlines():
            parts = line.split()
            if not parts:
                continue
            name = parts[0]
            info = dict(p.split("=", 1) for p in parts if "=" in p)
            controls[name] = info
        sets = []
        for auto in ("auto_exposure", "exposure_auto"):
            if auto in controls:
                sets.append(f"{auto}=1")              # 1 = exposición manual (UVC)
        for exp in ("exposure_time_absolute", "exposure_absolute"):
            if exp in controls and "default" in controls[exp]:
                sets.append(f"{exp}={controls[exp]['default']}")
        for flag in ("exposure_dynamic_framerate", "auto_exposure_priority"):
            if flag in controls:
                sets.append(f"{flag}=0")
        if "gain" in controls and "default" in controls["gain"]:
            sets.append(f"gain={controls['gain']['default']}")
        if not sets:
            self.manual_exposure = False
            return
        try:
            r = subprocess.run([self.v4l2ctl, "-d", self.device, "-c", ",".join(sets)],
                               capture_output=True, text=True, timeout=5)
            self.manual_exposure = r.returncode == 0 and any("exposure" in x for x in sets)
        except Exception:      # noqa: BLE001
            self.manual_exposure = False

    def _measure(self):
        import subprocess
        try:
            self._fix_exposure()
            out = subprocess.run(
                [self.ffmpeg, "-v", "error", "-f", "v4l2", "-i", self.device,
                 # el 6.º cuadro (la cámara ya se estabilizó), reducido a 160×120
                 "-vf", "select=eq(n\\,5),scale=160:120", "-frames:v", "1",
                 "-f", "rawvideo", "-pix_fmt", "gray", "-"],
                capture_output=True, timeout=20).stdout
            if out:
                frame = out[-160 * 120:]
                self.level = round(sum(frame) / len(frame))
        except Exception:      # noqa: BLE001
            pass
        finally:
            self._busy = False

    def update(self, now, fast=False):
        """fast: con Ajustes abierto mide cada 3 s, para ver la lectura en vivo."""
        if self.available and not self.paused and not self._busy \
                and now - self._last >= (3 if fast else self.EVERY):
            self._last, self._busy = now, True
            threading.Thread(target=self._measure, daemon=True).start()

    def ambient(self):
        """Luz del cuarto de 0 (oscuro) a 1 (muy iluminado), o None."""
        if self.level is None:
            return None
        return max(0.0, min(1.0, (math.log1p(self.level) - math.log1p(3)) / (math.log1p(150) - math.log1p(3))))


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
        "isight": read("/run/vitrina-isight.log"),
        "isight_firmware": os.path.exists("/lib/firmware/isight.fw"),
    }


class Backlight:
    """Brillo de la pantalla, como un nivel de 0 a 1 (lo que ve la persona).

    - De SOFT a 1, la luz de fondo va de su mínimo visible (`floor`) al máximo,
      con pasos más finos abajo (como macOS).
    - De 0 a SOFT, la luz de fondo ya está en su mínimo y la app oscurece la
      imagen (`dim`): así se logra un brillo muy bajo de noche sin que la
      pantalla se vaya a negro. (Por debajo de cierto valor, la luz de fondo de
      estas pantallas se apaga por completo.)

    Sin acceso a /sys/class/backlight solo se oscurece la imagen."""

    SOFT = 0.15
    SOFT_DIM = 0.6
    DEFAULT_FLOOR = 0.125     # MacBook5,2: 1/16 ya es negro, 2/16 se ve

    def __init__(self, floor=0.0):
        self.dir = None
        for d in sorted(glob.glob("/sys/class/backlight/*")):
            if os.access(os.path.join(d, "brightness"), os.W_OK):
                self.dir = d
                break
        self.max = self._read("max_brightness") or 0
        self.original = self._read("brightness")
        self._last = None
        self.floor = floor if floor and floor > 0 else self.DEFAULT_FLOOR
        self.dim = 0.0          # oscurecimiento de la imagen (lo dibuja la app)

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

    def initial_level(self):
        """El nivel que corresponde al brillo con el que arrancó la Mac."""
        if not self.available or not self.original:
            return 0.8
        frac = self.original / self.max
        if frac <= self.floor:
            return self.SOFT
        return self.SOFT + (1 - self.SOFT) * math.sqrt((frac - self.floor) / (1 - self.floor))

    def hw_fraction(self, level):
        if level <= self.SOFT:
            return self.floor
        t = (level - self.SOFT) / (1 - self.SOFT)
        return self.floor + (1 - self.floor) * t * t

    def apply(self, level, off=0.0):
        """level 0–1; off 0–1 apaga la luz de fondo (modo noche "apagada")."""
        level = max(0.0, min(1.0, level))
        self.dim = 0.0 if level >= self.SOFT else self.SOFT_DIM * (1 - level / self.SOFT)
        if self.available:
            self.write_raw(round(self.max * self.hw_fraction(level) * (1 - max(0.0, min(1.0, off)))))

    def write_raw(self, value):
        if not self.available or value == self._last:
            return
        try:
            with open(os.path.join(self.dir, "brightness"), "w") as f:
                f.write(str(max(0, min(self.max, int(value)))))
            self._last = value
        except OSError:
            self.dir = None

    def restore(self):
        if self.available and self.original is not None:
            self.write_raw(self.original)
