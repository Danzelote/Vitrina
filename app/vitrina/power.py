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


def _procs():
    """{pid: (nombre, ticks de procesador usados)} de todos los procesos."""
    out = {}
    for d in os.listdir("/proc"):
        if not d.isdigit():
            continue
        st = _read(f"/proc/{d}/stat")
        if not st or ")" not in st:
            continue
        name = st[st.index("(") + 1:st.rindex(")")]
        f = st[st.rindex(")") + 2:].split()
        try:
            out[int(d)] = (name, int(f[11]) + int(f[12]))
        except (IndexError, ValueError):
            pass
    return out


def _irq_ticks():
    line = (_read("/proc/stat") or "").splitlines()
    if not line or not line[0].startswith("cpu "):
        return 0
    v = [int(x) for x in line[0].split()[1:]]
    return v[5] + v[6] if len(v) > 6 else 0


class Meter:
    """Se llama en cada cuadro; cada pocos segundos guarda el promedio.

    Además de cuánto gasta, anota a qué ritmo dibujó y por qué (para encontrar
    lo que no la deja descansar) y qué eventos le llegaron."""

    EVERY = 5.0
    HOUR = 720                  # ventanas de 5 s en una hora

    def __init__(self):
        self.at = time.monotonic()
        self.times = os.times()
        self.cpu = _cpu_busy()
        self.procs = _procs()
        self.irq = _irq_ticks()
        self.hz = os.sysconf("SC_CLK_TCK") if hasattr(os, "sysconf") else 100
        self.frames = 0
        self.app_pct = None      # % de un núcleo que usa la app (sin los videos)
        self.mac_pct = None      # % de todo el procesador (con todo lo demás)
        self.fps = None          # cuadros por segundo que se dibujaron
        self.top = []            # [(programa, % de un núcleo)] los que más gastan
        self.rates = {}          # ritmo -> segundos, en esta ventana
        self.reasons = {}        # por qué fue rápido -> segundos, en esta ventana
        self.events = {}         # tipo de evento -> cuántos, en esta ventana
        self.last = {}           # lo de la ventana anterior (para el diagnóstico)
        self.history = []        # [(ritmos, motivos)] de la última hora
        self.prev = self.at

    def event(self, name):
        self.events[name] = self.events.get(name, 0) + 1

    def tick(self, now, rate=None, reason=None):
        self.frames += 1
        span = max(0.0, now - self.prev)
        self.prev = now
        if rate is not None:
            key = str(rate)
            self.rates[key] = self.rates.get(key, 0.0) + span
            if reason:
                self.reasons[reason] = self.reasons.get(reason, 0.0) + span
        dt = now - self.at
        if dt < self.EVERY:
            return
        t = os.times()
        self.app_pct = round(100 * ((t.user - self.times.user) + (t.system - self.times.system)) / dt, 1)
        cpu = _cpu_busy()
        if cpu and self.cpu and cpu[1] > self.cpu[1]:
            self.mac_pct = round(100 * (cpu[0] - self.cpu[0]) / (cpu[1] - self.cpu[1]), 1)
        procs = _procs()
        use = {}
        for pid, (name, ticks) in procs.items():
            before = self.procs.get(pid)
            if before and before[0] == name and ticks > before[1]:
                use[name] = use.get(name, 0) + ticks - before[1]
        irq = _irq_ticks()
        if irq > self.irq:
            use["(interrupciones)"] = irq - self.irq
        self.top = sorted(((n, round(100 * v / self.hz / dt, 1)) for n, v in use.items()),
                          key=lambda x: -x[1])[:6]
        self.fps = round(self.frames / dt, 1)
        self.last = {"ritmos": self.rates, "motivos": self.reasons, "eventos": self.events}
        self.history = (self.history + [(self.rates, self.reasons)])[-self.HOUR:]
        self.at, self.times, self.cpu, self.procs, self.irq, self.frames = now, t, cpu, procs, irq, 0
        self.rates, self.reasons, self.events = {}, {}, {}

    def hour(self):
        """Reparto de la última hora: {"ritmos": {"2": 81.0, …}, "motivos": {…}} en %."""
        rates, reasons = {}, {}
        for r, why in self.history:
            for k, v in r.items():
                rates[k] = rates.get(k, 0) + v
            for k, v in why.items():
                reasons[k] = reasons.get(k, 0) + v
        total = sum(rates.values()) or 1

        def pct(d):
            return {k: round(100 * v / total, 1) for k, v in sorted(d.items(), key=lambda kv: -kv[1])}
        return {"minutos": round(total / 60, 1), "ritmos": pct(rates), "motivos": pct(reasons)}


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


def kernel_report():
    """Qué tiene ocupado al núcleo (tareas, interrupciones). Lo mide install.sh
    como root durante ~1.5 s; solo en la Vitrina instalada o en la USB."""
    import json
    import shutil
    import subprocess
    script = "/opt/vitrina/install.sh"
    if not (os.path.exists(script) and shutil.which("sudo")):
        return None
    try:
        out = subprocess.run(["sudo", "-n", script, "kwork"], capture_output=True, text=True,
                             timeout=15, stdin=subprocess.DEVNULL).stdout
        line = next((x for x in out.splitlines() if x.startswith("KWORK ")), None)
        return json.loads(line[6:]) if line else {"error": out[-300:]}
    except Exception as exc:       # noqa: BLE001
        return {"error": str(exc)}
