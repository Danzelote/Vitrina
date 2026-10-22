"""WiFi desde la propia Vitrina (en la imagen de Linux, con NetworkManager).

Todo corre en hilos para no trabar la pantalla: buscar redes tarda unos
segundos y conectarse puede tardar hasta medio minuto.
"""

import os
import re
import shutil
import subprocess
import sys
import threading

NMCLI = shutil.which("nmcli")
SYSTEM = bool(os.environ.get("VITRINA_SYSTEM"))     # corriendo como sistema (la imagen de la USB)


def _split(line):
    """nmcli -t separa con ':' y escapa los ':' del texto como '\\:'."""
    out, cur, esc = [], "", False
    for ch in line:
        if esc:
            cur += ch
            esc = False
        elif ch == "\\":
            esc = True
        elif ch == ":":
            out.append(cur)
            cur = ""
        else:
            cur += ch
    out.append(cur)
    return out


def _cmd(args):
    """En la imagen se usa sudo (permitido solo para estos comandos): no depende de polkit."""
    return (["sudo", "-n"] if SYSTEM and shutil.which("sudo") else []) + args


def _run(args, timeout=40):
    try:
        r = subprocess.run(_cmd([NMCLI] + args), capture_output=True, text=True, timeout=timeout)
        return r.returncode, (r.stdout or "") + (r.stderr or "")
    except Exception as exc:           # noqa: BLE001
        return 1, str(exc)


class Wifi:
    def __init__(self):
        self.available = NMCLI is not None
        self.networks = []          # [(ssid, señal 0-100, con contraseña, en uso)]
        self.current = None         # red WiFi conectada
        self.wired = False          # conectada por cable
        self.scanning = False
        self.connecting = None      # nombre de la red a la que se está conectando
        self.message = ""           # último resultado ("ok:…" o "error:…")
        self._lock = threading.Lock()

    @property
    def online(self):
        return bool(self.current or self.wired)

    def _bg(self, fn, *args):
        threading.Thread(target=fn, args=args, daemon=True).start()

    # -- estado ------------------------------------------------------------------

    def refresh_status(self):
        if self.available:
            self._bg(self._status)

    def _status(self):
        code, out = _run(["-t", "-f", "TYPE,STATE,CONNECTION", "device"], 10)
        if code != 0:
            return
        wifi, wired = None, False
        for line in out.splitlines():
            parts = _split(line)
            if len(parts) < 3:
                continue
            kind, state, name = parts[0], parts[1], parts[2]
            if state.startswith("connected") and not state.startswith("connected (externally"):
                if kind == "wifi":
                    wifi = name
                elif kind == "ethernet":
                    wired = True
        self.current, self.wired = wifi, wired

    # -- buscar --------------------------------------------------------------------

    def scan(self):
        if not self.available or self.scanning:
            return
        self.scanning = True
        self._bg(self._scan)

    def _scan(self):
        try:
            code, out = _run(["-t", "-f", "IN-USE,SSID,SIGNAL,SECURITY", "device", "wifi", "list", "--rescan", "yes"], 30)
            found = {}
            if code == 0:
                for line in out.splitlines():
                    parts = _split(line)
                    if len(parts) < 4 or not parts[1]:
                        continue
                    in_use, ssid = parts[0] == "*", parts[1]
                    try:
                        signal = int(parts[2])
                    except ValueError:
                        signal = 0
                    secure = parts[3] not in ("", "--")
                    old = found.get(ssid)
                    if not old or signal > old[1] or in_use:
                        found[ssid] = (ssid, max(signal, old[1] if old else 0), secure, in_use or (old[3] if old else False))
            self.networks = sorted(found.values(), key=lambda n: (not n[3], -n[1], n[0].lower()))
            self._status()
        finally:
            self.scanning = False

    # -- conectar ------------------------------------------------------------------

    def connect(self, ssid, password=""):
        if not self.available or self.connecting:
            return
        self.connecting = ssid
        self.message = ""
        self._bg(self._connect, ssid, password)

    def _connect(self, ssid, password):
        try:
            args = ["device", "wifi", "connect", ssid]
            if password:
                args += ["password", password]
            code, out = _run(args, 60)
            if code == 0:
                self.message = "ok"
            elif "Secrets were required" in out or "802-11-wireless-security.psk" in out:
                self.message = "error:password"
                _run(["connection", "delete", "id", ssid], 10)     # no guardar la contraseña mala
            else:
                self.message = "error:" + (out.strip().splitlines() or ["?"])[-1][:120]
            if code != 0:
                print("WiFi:", out.strip()[:300], flush=True)
            self._status()
        finally:
            self.connecting = None


def power(action):
    """Apagar o reiniciar la Mac (solo en la imagen)."""
    if SYSTEM and action in ("poweroff", "reboot"):
        subprocess.Popen(_cmd(["/usr/bin/systemctl", action]))


def set_timezone(tz):
    """Pone la zona horaria del sistema (la manda el celular al conectarse)."""
    if not SYSTEM or not tz or "/" not in tz or ".." in tz:
        return False
    if not os.path.exists(os.path.join("/usr/share/zoneinfo", tz)):
        return False
    try:
        subprocess.run(_cmd(["/usr/bin/timedatectl", "set-timezone", tz]), timeout=10, check=True, capture_output=True)
        return True
    except Exception:          # noqa: BLE001
        return False


# -- volumen del sistema (teclas de volumen de la Mac) --------------------------------

AMIXER = shutil.which("amixer")


class Volume:
    """Volumen general con ALSA (amixer). En macOS el sistema ya maneja las teclas."""

    STEP = 6

    def __init__(self):
        self.available = bool(AMIXER) and sys.platform.startswith("linux")
        self.level = 80
        self.muted = False
        if self.available:
            threading.Thread(target=self._read, daemon=True).start()

    def _read(self):
        try:
            out = subprocess.run([AMIXER, "-M", "get", "Master"], capture_output=True, text=True, timeout=5).stdout
            m = re.search(r"\[(\d+)%\](?:.*\[(on|off)\])?", out)
            if m:
                self.level = int(m.group(1))
                self.muted = m.group(2) == "off"
        except Exception:      # noqa: BLE001
            pass

    def _apply(self):
        if not self.available:
            return
        args = [AMIXER, "-q", "-M", "sset", "Master", f"{self.level}%", "mute" if self.muted else "unmute"]
        threading.Thread(target=lambda: subprocess.run(args, capture_output=True, timeout=5), daemon=True).start()

    def change(self, step):
        self.muted = False
        self.level = max(0, min(100, self.level + step))
        self._apply()

    def toggle_mute(self):
        self.muted = not self.muted
        self._apply()
