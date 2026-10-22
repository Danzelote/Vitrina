"""Ajustes que el usuario cambia desde la app y que se conservan entre sesiones."""

import json
import os
from dataclasses import asdict, dataclass

from . import config as C


def _path():
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.join(os.path.expanduser("~"), ".config")
    d = os.path.join(base, "vitrina")
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, "settings.json")


@dataclass
class Settings:
    idle_seconds: int = int(C.IDLE_TIME)
    show_info: bool = True
    shuffle: bool = False

    @classmethod
    def load(cls):
        try:
            with open(_path()) as f:
                data = json.load(f)
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
