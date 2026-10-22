"""Relojes grandes para la noche.

- Ventana: números redondos y gruesos sobre negro; por dentro de los números
  se ven tus fotos (tenues y con poco color), como si fueran una ventana.
- Clásico: números altos y angostos de un solo color, con el día a un lado.

Cada número se dibuja una sola vez (a su tamaño) y se reutiliza, así el reloj
no cuesta nada aunque se quede toda la noche.
"""

import os
import time

import pygame
from pygame._sdl2.video import Texture

from .i18n import weekday_abbr

FONT_DIR = os.path.join(os.path.dirname(__file__), "fonts")
ROUND = os.path.join(FONT_DIR, "Fredoka-Bold.ttf")
TALL = os.path.join(FONT_DIR, "BebasNeue-Regular.ttf")

WINDOW_HEIGHT = 0.46    # alto de los números de la ventana (fracción de la pantalla)
CLASSIC_HEIGHT = 0.62   # alto de los números del clásico
COLORS = {"white": (236, 236, 240), "blue": (134, 168, 236), "red": (214, 74, 60)}


class Glyphs:
    """Texturas de caracteres sueltos, recortadas justo a su tinta."""

    def __init__(self, renderer):
        self.r = renderer
        self.cache = {}
        self.ratio = {}

    def _ink_ratio(self, path):
        """Alto de la tinta de un dígito respecto al tamaño de la fuente."""
        if path not in self.ratio:
            f = pygame.font.Font(path, 200)
            self.ratio[path] = f.render("0", True, (255, 255, 255)).get_bounding_rect().height / 200
        return self.ratio[path]

    def get(self, path, ch, ink_px):
        """(textura, ancho, alto) en píxeles reales de `ch` con dígitos de `ink_px` de alto."""
        size = max(8, round(ink_px / self._ink_ratio(path)))
        key = (path, ch, size)
        if key not in self.cache:
            if len(self.cache) > 80:
                self.cache.clear()
            surf = pygame.font.Font(path, size).render(ch, True, (255, 255, 255))
            box = surf.get_bounding_rect()
            surf = surf.subsurface(box).copy() if box.width and box.height else surf
            tex = Texture.from_surface(self.r, surf)
            tex.blend_mode = pygame.BLENDMODE_BLEND
            self.cache[key] = (tex, surf.get_width(), surf.get_height())
        return self.cache[key]


def time_text(clock_setting):
    t = time.localtime()
    if clock_setting == "12":
        return f"{t.tm_hour % 12 or 12}:{t.tm_min:02d}"
    return f"{t.tm_hour}:{t.tm_min:02d}"


def window_layout(glyphs, text, vw, vh, dpi, H=None):
    """Piezas del reloj ventana centradas: [(textura|None, x, y, w, h)] en
    puntos (None = punto de los dos puntos) y el centro del punto de arriba."""
    H = H or vh * WINDOW_HEIGHT
    ink = H * dpi
    parts, x = [], 0.0
    dot = H * 0.2
    top_dot = None
    for ch in text:
        if ch == ":":
            x += H * 0.01
            parts.append((None, x, H * 0.2, dot, dot))
            parts.append((None, x, H * 0.6, dot, dot))
            top_dot = (x + dot / 2, H * 0.2 + dot / 2)
            x += dot + H * 0.035
            continue
        tex, w, h = glyphs.get(ROUND, ch, ink)
        w, h = w / dpi, h / dpi
        parts.append((tex, x, H - h, w, h))
        x += w - H * 0.025     # los números casi se tocan
    total = x + H * 0.025
    if total > vw * 0.9:       # que quepa a lo ancho
        return window_layout(glyphs, text, vw, vh, dpi, H * vw * 0.88 / total)
    ox, oy = (vw - total) / 2, (vh - H) / 2
    parts = [(t, px + ox, py + oy, w, h) for t, px, py, w, h in parts]
    if top_dot is not None:
        top_dot = (top_dot[0] + ox, top_dot[1] + oy)
    return parts, top_dot


def draw_window_mask(g, parts, scale=1.0, origin=(0, 0)):
    """Dibuja los números en blanco (la "ventana"), escalados desde `origin`."""
    zx, zy = origin
    for tex, x, y, w, h in parts:
        x, y, w, h = zx + (x - zx) * scale, zy + (y - zy) * scale, w * scale, h * scale
        t = tex or g.circle
        t.color = (255, 255, 255)
        t.alpha = 255
        t.draw(dstrect=(x, y, w, h))


def draw_classic(g, glyphs, text, vw, vh, dpi, color_key, alpha, drift=(0, 0), H=None):
    """Reloj clásico: la hora grande y, a la derecha, el día."""
    color = COLORS.get(color_key, COLORS["blue"])
    H = H or vh * CLASSIC_HEIGHT
    pieces, x = [], 0.0
    for ch in text:
        if ch == ":":
            tex, w, h = glyphs.get(TALL, ":", H * 0.62 * dpi)
            w, h = w / dpi, h / dpi
            x += H * 0.05
            pieces.append((tex, x, H * 0.22, w, h))
            x += w + H * 0.05
            continue
        tex, w, h = glyphs.get(TALL, ch, H * dpi)
        w, h = w / dpi, h / dpi
        pieces.append((tex, x, H - h, w, h))
        x += w + H * 0.035
    time_w = x - H * 0.035
    t = time.localtime()
    side_h = H * 0.13
    day, num = weekday_abbr(t.tm_wday), str(t.tm_mday)
    side = []
    sx = 0.0
    for s, c in ((day, color), (num, (236, 236, 240))):
        for ch in s:
            tex, w, h = glyphs.get(TALL, ch, side_h * dpi)
            side.append((tex, sx, side_h - h / dpi, w / dpi, h / dpi, c))
            sx += w / dpi + side_h * 0.05
        sx += side_h * 0.3
    gap = H * 0.16
    total = time_w + gap + sx
    if total > vw * 0.9:       # que quepa a lo ancho (por ejemplo, "12:58")
        return draw_classic(g, glyphs, text, vw, vh, dpi, color_key, alpha, drift, H * vw * 0.88 / total)
    ox, oy = (vw - total) / 2 + drift[0], (vh - H) / 2 + drift[1]
    a = int(255 * max(0.0, min(1.0, alpha)))
    for tex, px, py, w, h in pieces:
        tex.color, tex.alpha = color, a
        tex.draw(dstrect=(ox + px, oy + py, w, h))
    for tex, px, py, w, h, c in side:
        tex.color, tex.alpha = c, a
        tex.draw(dstrect=(ox + time_w + gap + px, oy + H * 0.02 + py, w, h))
