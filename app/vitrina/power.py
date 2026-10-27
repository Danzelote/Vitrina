"""Cuánto trabaja la Mac: uso del procesador, temperaturas y ventilador.

Lo lee el diagnóstico del celular (/api/diag) para comprobar con números que
la presentación casi no gasta. Nada de esto cambia cómo se comporta la app.
"""

import ctypes
import ctypes.util
import glob
import os
import time


def _read(path):
    try:
        with open(path) as f:
            return f.read().strip()
    except OSError:
        return None


def _cpu_busy():
    """(ocupado, total) del procesador entero, en ticks, desde que arrancó."""
    line = (_read("/proc/stat") or "").splitlines()
    if not line or not line[0].startswith("cpu "):
        return None
    v = [int(x) for x in line[0].split()[1:]]
    idle = v[3] + (v[4] if len(v) > 4 else 0)
    return sum(v) - idle, sum(v)


class Meter:
    """Se llama en cada cuadro; cada pocos segundos guarda el promedio."""

    EVERY = 5.0

    def __init__(self):
        self.at = time.monotonic()
        self.times = os.times()
        self.cpu = _cpu_busy()
        self.frames = 0
        self.app_pct = None      # % de un núcleo que usa la app (sin los videos)
        self.mac_pct = None      # % de todo el procesador (con todo lo demás)
        self.fps = None          # cuadros por segundo que se dibujaron

    def tick(self, now):
        self.frames += 1
        dt = now - self.at
        if dt < self.EVERY:
            return
        t = os.times()
        self.app_pct = round(100 * ((t.user - self.times.user) + (t.system - self.times.system)) / dt, 1)
        cpu = _cpu_busy()
        if cpu and self.cpu and cpu[1] > self.cpu[1]:
            self.mac_pct = round(100 * (cpu[0] - self.cpu[0]) / (cpu[1] - self.cpu[1]), 1)
        self.fps = round(self.frames / dt, 1)
        self.at, self.times, self.cpu, self.frames = now, t, cpu, 0


def sensors():
    """Temperaturas (°C), ventiladores (rpm) y velocidad del procesador."""
    temps, fans = {}, {}
    for hw in sorted(glob.glob("/sys/class/hwmon/hwmon*")):
        name = _read(os.path.join(hw, "name")) or os.path.basename(hw)
        for f in sorted(glob.glob(os.path.join(hw, "temp*_input"))):
            v = _read(f)
            if v and v.lstrip("-").isdigit() and int(v) > 0:
                label = _read(f.replace("_input", "_label")) or os.path.basename(f)[:-6]
                temps[f"{name} {label}"] = round(int(v) / 1000, 1)
    for smc in glob.glob("/sys/devices/platform/applesmc.*"):
        for f in sorted(glob.glob(os.path.join(smc, "fan*_input"))):
            n = os.path.basename(f)[:-6]
            fans[n] = {"rpm": _read(f), "min": _read(os.path.join(smc, n + "_min")),
                       "max": _read(os.path.join(smc, n + "_max"))}
        if not temps:       # kernels sin hwmon para applesmc
            for f in sorted(glob.glob(os.path.join(smc, "temp*_input"))):
                v = _read(f)
                if v and v.isdigit() and int(v) > 0:
                    temps["applesmc " + (_read(f.replace("_input", "_label")) or f)] = round(int(v) / 1000, 1)
    mhz = {}
    for c in sorted(glob.glob("/sys/devices/system/cpu/cpu[0-9]*/cpufreq")):
        cur = _read(os.path.join(c, "scaling_cur_freq"))
        if cur:
            mhz[c.split("/")[-2]] = int(cur) // 1000
    gov = _read("/sys/devices/system/cpu/cpu0/cpufreq/scaling_governor")
    top = _read("/sys/devices/system/cpu/cpu0/cpufreq/cpuinfo_max_freq")
    return {"temperaturas_c": temps, "ventiladores": fans, "cpu_mhz": mhz,
            "cpu_mhz_max": int(top) // 1000 if top else None, "cpu_modo": gov,
            "carga": _read("/proc/loadavg")}


def renderer_info(win):
    """("opengl", "NVAC" …) si la tarjeta de video dibuja; ("software", None) si
    todo lo hace el procesador. Se llama una vez, en el hilo de la ventana."""
    try:
        # Puede haber dos SDL cargadas (la de pygame y la del sistema, que trae
        # ffmpeg): sirve la que conoce la ventana.
        libs = []
        with open("/proc/self/maps") as f:
            for line in f:
                path = line.split()[-1]
                name = os.path.basename(path)
                if path.startswith("/") and name.startswith("libSDL2-2") and path not in libs:
                    libs.append(path)
        libs.sort(key=lambda p: "pygame" not in p)

        class Info(ctypes.Structure):
            _fields_ = [("name", ctypes.c_char_p), ("flags", ctypes.c_uint32), ("n", ctypes.c_uint32),
                        ("formats", ctypes.c_uint32 * 16), ("max_w", ctypes.c_int), ("max_h", ctypes.c_int)]
        ren = None
        for path in libs:
            sdl = ctypes.CDLL(path)
            sdl.SDL_GetWindowFromID.restype = ctypes.c_void_p
            sdl.SDL_GetWindowFromID.argtypes = [ctypes.c_uint32]
            sdl.SDL_GetRenderer.restype = ctypes.c_void_p
            sdl.SDL_GetRenderer.argtypes = [ctypes.c_void_p]
            sdl.SDL_GetRendererInfo.argtypes = [ctypes.c_void_p, ctypes.POINTER(Info)]
            w = sdl.SDL_GetWindowFromID(win.id)
            ren = sdl.SDL_GetRenderer(w) if w else None
            if ren:
                break
        info = Info()
        if not ren or sdl.SDL_GetRendererInfo(ren, ctypes.byref(info)) != 0:
            return None, None
        name, gl = (info.name or b"?").decode(), None
        if name.startswith("opengl"):
            libgl = ctypes.CDLL(ctypes.util.find_library("GL") or "libGL.so.1")
            libgl.glGetString.restype = ctypes.c_char_p
            libgl.glGetString.argtypes = [ctypes.c_uint]
            gl = (libgl.glGetString(0x1F01) or b"").decode() or None    # GL_RENDERER
        return name, gl
    except Exception as exc:       # noqa: BLE001
        return None, str(exc)
