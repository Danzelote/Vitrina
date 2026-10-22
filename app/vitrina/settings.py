"""Ajustes que el usuario cambia desde la app y que se conservan entre sesiones."""

import json
import os
from dataclasses import asdict, dataclass

from . import config as C


def config_dir():
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.join(os.path.expanduser("~"), ".config")
    d = os.path.join(base, "vitrina")
    os.makedirs(d, exist_ok=True)
    return d


def _path():
    return os.path.join(config_dir(), "settings.json")


@dataclass
class Settings:
    idle_seconds: int = int(C.IDLE_TIME)
    show_info: bool = True
    shuffle: bool = False
    theme: str = "auto"          # "dark" | "light" | "auto"
    language: str = "es"         # "es" | "en"
    kenburns: str = "pan"        # "off" | "zoom" | "pan" (zoom y paneo)
    memories: bool = True        # "Un día como hoy"
    clock: str = "off"           # "off" | "12" | "24"
    night: str = "never"         # "never" | "schedule"
    night_hours: str = "23-7"    # ver night.SCHEDULES
    night_style: str = "off"     # "off" (apagada) | "window" (reloj ventana) | "classic" (reloj clásico)
    night_color: str = "blue"    # color del reloj clásico: "white" | "blue" | "red"
    auto_brightness: bool = False  # brillo según la luz del cuarto (sensor o cámara)
    brightness: float = -1.0     # brillo elegido, 0–1 (-1: el que tenía la Mac al arrancar)
    bright_offset: float = 0.0   # con brillo automático: ajuste de la persona con las teclas
    min_brightness: float = 0.0  # mínimo visible de la luz de fondo (calibrado); 0 = sin calibrar

    @classmethod
    def load(cls):
        try:
            with open(_path()) as f:
                data = json.load(f)
            if data.get("night_style") == "clock":   # nombre de la versión 0.4.0
                data["night_style"] = "classic"
            if data.get("night") == "light":         # 0.8: el modo noche es por horario; la luz ajusta el brillo
                data["night"] = "schedule"
                data.setdefault("auto_brightness", True)
            return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})
        except Exception:
            return cls()

    def save(self):
        try:
            tmp = _path() + ".tmp"
            with open(tmp, "w") as f:
                json.dump(asdict(self), f, indent=2)
            os.replace(tmp, _path())
        except Exception:
            pass
