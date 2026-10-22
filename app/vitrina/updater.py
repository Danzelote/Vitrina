"""Actualizar la Vitrina instalada desde GitHub (sin tocar fotos ni ajustes).

El trabajo lo hace os/rootfs/opt/vitrina/update.sh (como root, con sudo);
aquí solo se lanza y se lee lo que va diciendo. Desde la USB no se puede
actualizar (todo se borra al apagar): ahí no aparece.
"""

import os
import shutil
import subprocess
import threading
import time

SCRIPT = "/opt/vitrina/update.sh"


def available():
    return os.path.exists("/etc/vitrina-instalada") and os.path.exists(SCRIPT)


def _cmd(action):
    return (["sudo", "-n"] if shutil.which("sudo") else []) + [SCRIPT, action]


class Updater:
    def __init__(self):
        self.state = "idle"     # idle · checking · current · new · applying · done · error
        self.latest = None
        self.error = None
        self.step, self.total, self.step_text = 0, 5, ""
        self.checked_at = None

    def as_dict(self):
        return {"state": self.state, "latest": self.latest, "error": self.error,
                "step": self.step, "total": self.total, "text": self.step_text}

    def check(self):
        if not available() or self.state in ("checking", "applying", "done"):
            return
        self.state, self.error = "checking", None
        threading.Thread(target=self._check, daemon=True).start()

    def _check(self):
        try:
            out = subprocess.run(_cmd("check"), capture_output=True, text=True, timeout=40).stdout
            self.checked_at = time.monotonic()
            if "NUEVA " in out:
                self.latest = out.split("NUEVA ", 1)[1].split()[0]
                self.state = "new"
            elif "AL_DIA" in out:
                self.state = "current"
            else:
                err = [line for line in out.splitlines() if line.startswith("ERROR ")]
                self.error = err[0][6:] if err else "No se pudo revisar"
                self.state = "error"
        except Exception as exc:       # noqa: BLE001
            self.error, self.state = str(exc), "error"

    def apply(self):
        if not available() or self.state in ("applying", "done"):
            return
        self.state, self.error, self.step = "applying", None, 0
        threading.Thread(target=self._apply, daemon=True).start()

    def _apply(self):
        try:
            proc = subprocess.Popen(_cmd("apply"), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                    text=True, bufsize=1, stdin=subprocess.DEVNULL)
            for line in proc.stdout:
                line = line.strip()
                print("Actualizar:", line, flush=True)
                if line.startswith("PASO "):
                    _, n, total, text = line.split(" ", 3)
                    self.step, self.total, self.step_text = int(n), int(total), text
                elif line.startswith("LISTO"):
                    self.latest = line[6:].strip() or self.latest
                    self.state = "done"
                elif line.startswith("ERROR "):
                    self.error = line[6:]
            proc.wait()
            if self.state != "done":
                self.state = "error"
                self.error = self.error or f"La actualización terminó sin avisar ({proc.returncode})"
        except Exception as exc:       # noqa: BLE001
            self.error, self.state = str(exc), "error"
