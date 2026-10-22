"""Instalar Vitrina en el disco de la Mac (desde la USB).

La parte que borra e instala es os/rootfs/opt/vitrina/install.sh (corre como
root con sudo); aquí solo se lanza y se lee lo que va diciendo.
"""

import os
import shutil
import subprocess
import threading

SCRIPT = "/opt/vitrina/install.sh"
MEDIUM = "/run/live/medium"

# Peso de cada paso en la barra (copiar el sistema es lo que más tarda).
WEIGHTS = [2, 5, 68, 5, 17, 3]


def running_live():
    """¿Vitrina está corriendo desde la USB (y se puede instalar)?"""
    return os.path.isdir(os.path.join(MEDIUM, "live")) and os.path.exists(SCRIPT)


def _cmd(args):
    return (["sudo", "-n"] if shutil.which("sudo") else []) + [SCRIPT] + args


def human_size(n):
    gb = n / 1e9
    return f"{gb:.0f} GB" if gb >= 10 else f"{gb:.1f} GB"


class Installer:
    def __init__(self):
        self.disks = None           # [(dispositivo, bytes, modelo)] cuando termina de buscar
        self.step = 0
        self.total = len(WEIGHTS)
        self.step_text = ""
        self.pct = 0                # avance dentro del paso
        self.done = False
        self.error = None
        self.running = False

    # -- buscar el disco ------------------------------------------------------------

    def detect(self):
        threading.Thread(target=self._detect, daemon=True).start()

    def _detect(self):
        found = []
        try:
            out = subprocess.run(_cmd(["detect"]), capture_output=True, text=True, timeout=20).stdout
            for line in out.splitlines():
                parts = line.split(" ", 3)
                if len(parts) >= 3 and parts[0] == "DISK":
                    found.append((parts[1], int(parts[2]), parts[3] if len(parts) > 3 else ""))
        except Exception as exc:       # noqa: BLE001
            print("Instalar: no se pudo buscar el disco:", exc, flush=True)
        found.sort(key=lambda d: -d[1])
        self.disks = found

    # -- instalar --------------------------------------------------------------------

    def start(self, disk):
        if self.running:
            return
        self.running, self.done, self.error = True, False, None
        threading.Thread(target=self._run, args=(disk,), daemon=True).start()

    def _run(self, disk):
        try:
            proc = subprocess.Popen(_cmd(["run", disk]), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                    text=True, bufsize=1)
            for line in proc.stdout:
                line = line.strip()
                print("Instalar:", line, flush=True)
                if line.startswith("PASO "):
                    _, n, total, text = line.split(" ", 3)
                    self.step, self.total, self.step_text, self.pct = int(n), int(total), text, 0
                elif line.startswith("AVANCE "):
                    try:
                        self.pct = max(0, min(100, int(line.split()[1])))
                    except ValueError:
                        pass
                elif line == "LISTO":
                    self.done = True
                elif line.startswith("ERROR "):
                    self.error = line[6:]
            proc.wait()
            if not self.done and not self.error:
                self.error = f"El instalador terminó sin avisar (código {proc.returncode})"
        except Exception as exc:       # noqa: BLE001
            self.error = str(exc)
        finally:
            self.running = False

    @property
    def progress(self):
        """Avance total de 0 a 1."""
        if self.done:
            return 1.0
        if self.step <= 0:
            return 0.0
        w = WEIGHTS[: self.total] if self.total <= len(WEIGHTS) else [1] * self.total
        before = sum(w[: self.step - 1])
        cur = w[self.step - 1] * self.pct / 100
        return min(1.0, (before + cur) / sum(w))
