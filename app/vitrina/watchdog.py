"""Vigilante: si la app deja de dibujar (se traba), anota dónde se quedó cada
hilo y la memoria libre, para verlo en el Diagnóstico del celular y en el
registro. No arregla nada: sirve para saber la causa."""

import sys
import threading
import time
import traceback

STUCK_AFTER = 15            # segundos sin dibujar
REPORTS = []                # informes (texto), el último al final


def _memory():
    try:
        with open("/proc/meminfo") as f:
            info = dict(line.split(":", 1) for line in f)
        return "Memoria libre: " + info.get("MemAvailable", "?").strip()
    except OSError:
        return ""


def _report(stuck_for):
    lines = [f"La app no dibuja desde hace {stuck_for:.0f} s. {_memory()}"]
    names = {t.ident: t.name for t in threading.enumerate()}
    for ident, frame in sys._current_frames().items():
        lines.append(f"--- hilo {names.get(ident, ident)}")
        lines.extend(x.rstrip() for x in traceback.format_stack(frame)[-8:])
    return "\n".join(lines)


def start(last_frame):
    """last_frame(): momento (time.monotonic) del último cuadro dibujado."""
    def loop():
        reported = None
        while True:
            time.sleep(5)
            at = last_frame()
            if at is None:
                continue
            stuck = time.monotonic() - at
            if stuck > STUCK_AFTER and reported != at:
                reported = at
                text = _report(stuck)
                REPORTS.append(text)
                del REPORTS[:-3]
                print("VIGILANTE:\n" + text, flush=True)
    threading.Thread(target=loop, name="vigilante", daemon=True).start()
