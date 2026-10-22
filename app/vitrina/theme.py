"""Temas de color: oscuro, claro y automático (según la hora del día).

La presentación siempre es negra (las fotos mandan); el tema cambia la
cuadrícula, los niveles, el visor y los controles. El texto que va encima de
fotos (títulos de los grupos, la descripción en la presentación) siempre es
blanco."""

from contextlib import contextmanager
from datetime import datetime

DAY_START, DAY_END = 7, 19   # horas en que el automático usa el tema claro


class Palette:
    def __init__(self, **kw):
        self.__dict__.update(kw)


DARK = Palette(
    name="dark",
    bg=(13, 13, 15), placeholder=(40, 40, 44),
    pill=(44, 44, 48, 210), button=(44, 44, 46, 255), panel=(30, 30, 34, 245),
    bar=(12, 12, 14), bar_alpha=0.94,
    hairline=(255, 255, 255), hairline_alpha=0.08,
    text=(245, 245, 247), text_dim=(199, 199, 204), text_secondary=(161, 161, 166),
    active_bg=(245, 245, 247, 255), active_fg=(17, 17, 17),
    toggle_off=(72, 72, 74, 255),
    empty=(255, 255, 255, 10), empty_text=(142, 142, 147),
)

LIGHT = Palette(
    name="light",
    bg=(242, 242, 247), placeholder=(218, 218, 224),
    pill=(255, 255, 255, 235), button=(228, 228, 233, 255), panel=(255, 255, 255, 250),
    bar=(249, 249, 251), bar_alpha=0.96,
    hairline=(0, 0, 0), hairline_alpha=0.1,
    text=(28, 28, 30), text_dim=(90, 90, 94), text_secondary=(110, 110, 115),
    active_bg=(28, 28, 30, 255), active_fg=(255, 255, 255),
    toggle_off=(209, 209, 214, 255),
    empty=(0, 0, 0, 12), empty_text=(142, 142, 147),
)


class _Current(Palette):
    def set(self, palette):
        self.__dict__.update(palette.__dict__)


T = _Current()
T.set(DARK)


def resolve(setting, now=None):
    """'dark' | 'light' | 'auto' -> paleta."""
    if setting == "light":
        return LIGHT
    if setting == "dark":
        return DARK
    hour = (now or datetime.now()).hour
    return LIGHT if DAY_START <= hour < DAY_END else DARK


@contextmanager
def using(palette):
    """Usa otra paleta temporalmente (por ejemplo, controles sobre fotos)."""
    saved = dict(T.__dict__)
    T.set(palette)
    try:
        yield
    finally:
        T.__dict__.clear()
        T.__dict__.update(saved)
