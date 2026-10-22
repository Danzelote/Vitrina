"""Ayudantes de dibujo sobre el renderizador acelerado de SDL2.

Todo se dibuja como texturas escaladas: es lo más barato para la gráfica y
funciona también con el renderizador por software de SDL si no hay aceleración.
"""

from collections import OrderedDict

import pygame
from pygame._sdl2.video import Texture

from . import config as C

FONT_NAMES = ["helveticaneue", "helvetica", "sfnsdisplay", "inter", "dejavusans", "liberationsans", "arial"]


class LRU(OrderedDict):
    def __init__(self, limit):
        super().__init__()
        self.limit = limit

    def get_item(self, key):
        if key in self:
            self.move_to_end(key)
            return self[key]
        return None

    def put(self, key, value):
        self[key] = value
        self.move_to_end(key)
        while len(self) > self.limit:
            self.popitem(last=False)


class Gfx:
    def __init__(self, renderer):
        self.r = renderer
        white = pygame.Surface((1, 1), pygame.SRCALPHA)
        white.fill((255, 255, 255, 255))
        self.white = self._tex(white)
        self.corner = self._tex(self._corner_surface())
        grad = pygame.Surface((1, 256), pygame.SRCALPHA)
        for y in range(256):
            grad.set_at((0, y), (0, 0, 0, y))
        self.gradient = self._tex(grad)
        self.thumbs = LRU(C.THUMB_CACHE)
        self.screens = LRU(C.SCREEN_CACHE)
        self.backdrops = LRU(8)
        self.texts = LRU(64)
        self.pills = LRU(32)
        self.fonts = {}
        self.loads_left = 0
        self.dpi = 1.0  # píxeles reales por punto (2 en pantallas Retina)

    # -- básicos ------------------------------------------------------------

    def _tex(self, surf):
        t = Texture.from_surface(self.r, surf)
        t.blend_mode = pygame.BLENDMODE_BLEND
        return t

    @staticmethod
    def _corner_surface():
        """Un cuarto de "esquina inversa": opaco fuera del círculo, transparente
        dentro. Pintada del color del fondo, redondea las esquinas."""
        big = pygame.Surface((256, 256), pygame.SRCALPHA)
        big.fill((255, 255, 255, 255))
        pygame.draw.circle(big, (255, 255, 255, 0), (256, 256), 256)
        return pygame.transform.smoothscale(big, (64, 64))

    def begin_frame(self, max_loads=10):
        self.loads_left = max_loads

    def rect(self, x, y, w, h, color, alpha=1.0):
        if alpha <= 0.003 or w <= 0 or h <= 0:
            return
        self.white.color = color[:3]
        self.white.alpha = int(255 * min(alpha, 1.0) * (color[3] / 255 if len(color) > 3 else 1))
        self.white.draw(dstrect=(x, y, w, h))

    def corners(self, x, y, w, h, r, color, alpha=1.0):
        r = min(r, w / 2, h / 2)
        if r < 0.75 or alpha <= 0.01:
            return
        t = self.corner
        t.color = color[:3]
        t.alpha = int(255 * min(alpha, 1.0))
        t.draw(dstrect=(x, y, r, r))
        t.draw(dstrect=(x + w - r, y, r, r), flip_x=True)
        t.draw(dstrect=(x, y + h - r, r, r), flip_y=True)
        t.draw(dstrect=(x + w - r, y + h - r, r, r), flip_x=True, flip_y=True)

    def image(self, tex, x, y, w, h, alpha=1.0, radius=0.0, corner_color=C.BG_GRID):
        """Dibuja `tex` llenando el rectángulo, recortada desde el centro para
        conservar la proporción (como object-fit: cover)."""
        if alpha <= 0.003 or w <= 0 or h <= 0:
            return
        tw, th = tex.width, tex.height
        target = w / h
        if tw / th > target:
            sw = th * target
            src = ((tw - sw) / 2, 0, sw, th)
        else:
            sh = tw / target
            src = (0, (th - sh) / 2, tw, sh)
        tex.alpha = int(255 * min(alpha, 1.0))
        tex.draw(srcrect=pygame.Rect(round(src[0]), round(src[1]), max(1, round(src[2])), max(1, round(src[3]))),
                 dstrect=(x, y, w, h))
        if radius > 0:
            self.corners(x, y, w, h, radius, corner_color, alpha)

    # -- texturas de fotos ----------------------------------------------------

    def _load(self, path):
        try:
            return self._tex(pygame.image.load(path))
        except Exception:
            return None

    def _cached(self, cache, key, path, force=False):
        tex = cache.get_item(key)
        if tex is not None or not path:
            return tex
        if self.loads_left <= 0 and not force:
            return None
        self.loads_left -= 1
        tex = self._load(path)
        if tex is not None:
            cache.put(key, tex)
        return tex

    def thumb(self, item, force=False):
        if not item.ready:
            return None
        return self._cached(self.thumbs, item.key, item.thumb_path, force)

    def screen(self, item, force=False):
        if not item.ready:
            return None
        return self._cached(self.screens, item.key, item.screen_path, force)

    def backdrop(self, item, force=False):
        if not item.ready or not item.vertical:
            return None
        return self._cached(self.backdrops, item.key, item.backdrop_path, force)

    def has_screen(self, item):
        return item.key in self.screens

    # -- texto y píldoras -----------------------------------------------------

    def font(self, size, bold=False):
        key = (size, bold)
        if key not in self.fonts:
            self.fonts[key] = pygame.font.SysFont(FONT_NAMES, size, bold=bold)
        return self.fonts[key]

    def text(self, s, size, color=C.TEXT, bold=False):
        """Texto renderizado a la resolución real; mide en puntos con tsize()."""
        key = (s, size, color, bold, self.dpi)
        tex = self.texts.get_item(key)
        if tex is None:
            surf = self.font(round(size * self.dpi), bold).render(s, True, color)
            tex = self._tex(surf)
            self.texts.put(key, tex)
        return tex

    def tsize(self, tex):
        return tex.width / self.dpi, tex.height / self.dpi

    def pill_shape(self, w, h, color=C.PILL_BG):
        key = (int(w), int(h), color, self.dpi)
        tex = self.pills.get_item(key)
        if tex is None:
            pw, ph = int(w * self.dpi), int(h * self.dpi)
            surf = pygame.Surface((pw * 2, ph * 2), pygame.SRCALPHA)
            pygame.draw.rect(surf, color, surf.get_rect(), border_radius=ph)
            surf = pygame.transform.smoothscale(surf, (pw, ph))
            tex = self._tex(surf)
            self.pills.put(key, tex)
        return tex

    def pill(self, label, cx, y, size=14, alpha=1.0, anchor="center", sublabel=None):
        """Una píldora con texto. `anchor` puede ser 'center' (cx es el centro)
        o 'left' (cx es la orilla izquierda). Devuelve su rectángulo."""
        if alpha <= 0.003:
            return None
        t1 = self.text(label, size, C.TEXT, bold=True)
        t2 = self.text(sublabel, size, C.TEXT_DIM) if sublabel else None
        w1, h1 = self.tsize(t1)
        w2, h2 = self.tsize(t2) if t2 else (0, 0)
        pad, gap = 18, 8
        w = w1 + (gap + w2 if t2 else 0) + pad * 2
        h = max(40, h1 + 16)
        x = cx - w / 2 if anchor == "center" else cx
        bg = self.pill_shape(w, h)
        bg.alpha = int(255 * alpha)
        bg.draw(dstrect=(x, y, w, h))
        t1.alpha = int(255 * alpha)
        t1.draw(dstrect=(x + pad, y + (h - h1) / 2, w1, h1))
        if t2:
            t2.alpha = int(255 * alpha)
            t2.draw(dstrect=(x + pad + w1 + gap, y + (h - h2) / 2, w2, h2))
        return (x, y, w, h)

    def label(self, s, x, y, size, alpha=1.0, bold=False, color=C.TEXT):
        if alpha <= 0.003:
            return
        t = self.text(s, size, color, bold)
        t.alpha = int(255 * alpha)
        w, h = self.tsize(t)
        t.draw(dstrect=(x, y, w, h))

    def label_centered(self, s, cx, y, size, alpha=1.0, bold=False, color=C.TEXT):
        t = self.text(s, size, color, bold)
        w, _ = self.tsize(t)
        self.label(s, cx - w / 2, y, size, alpha, bold, color)

    # -- controles ------------------------------------------------------------

    def triangle(self, pts, color, alpha=1.0):
        if alpha <= 0.003:
            return
        self.r.draw_blend_mode = pygame.BLENDMODE_BLEND
        self.r.draw_color = (*color[:3], int(255 * min(alpha, 1.0)))
        self.r.fill_triangle(*pts)

    def round_rect(self, x, y, w, h, color, alpha=1.0, radius=None):
        """Rectángulo redondeado (por defecto, forma de píldora)."""
        if alpha <= 0.003 or w < 1 or h < 1:
            return
        if radius is None:
            tex = self.pill_shape(w, h, color)
        else:
            key = ("rr", int(w), int(h), int(radius), color, self.dpi)
            tex = self.pills.get_item(key)
            if tex is None:
                pw, ph = int(w * self.dpi), int(h * self.dpi)
                surf = pygame.Surface((pw * 2, ph * 2), pygame.SRCALPHA)
                pygame.draw.rect(surf, color, surf.get_rect(), border_radius=int(radius * self.dpi * 2))
                tex = self._tex(pygame.transform.smoothscale(surf, (pw, ph)))
                self.pills.put(key, tex)
        tex.alpha = int(255 * min(alpha, 1.0))
        tex.draw(dstrect=(x, y, w, h))

    def button(self, label, x, y, h=44, alpha=1.0, active=False, bold=True, size=14, icon=None, pad=18):
        """Botón tipo píldora. Devuelve su rectángulo (x, y, w, h)."""
        fg = (17, 17, 17) if active else C.TEXT
        bg = (245, 245, 247, 255) if active else (44, 44, 46, 255)
        t = self.text(label, size, fg, bold)
        tw, th = self.tsize(t)
        iw = 14 if icon else 0
        w = tw + pad * 2 + (iw + 8 if icon else 0)
        self.round_rect(x, y, w, h, bg, alpha)
        tx = x + pad
        if icon == "play":
            cy = y + h / 2
            self.triangle(((tx + 1, cy - 7), (tx + 1, cy + 7), (tx + 13, cy)), fg, alpha)
            tx += iw + 8
        t.alpha = int(255 * min(alpha, 1.0))
        t.draw(dstrect=(tx, y + (h - th) / 2, tw, th))
        return (x, y, w, h)

    def segmented(self, options, active_key, x, y, h=44, alpha=1.0, disabled=()):
        """Selector segmentado. options = [(clave, etiqueta)]. Devuelve
        [(clave, rect)] y el ancho total."""
        size, pad, inset = 13, 14, 3
        texts = [(k, self.text(lbl, size, (17, 17, 17) if k == active_key else C.TEXT, True)) for k, lbl in options]
        widths = [self.tsize(t)[0] + pad * 2 for _, t in texts]
        total = sum(widths) + inset * 2
        self.round_rect(x, y, total, h, (44, 44, 46, 255), alpha)
        out = []
        cx = x + inset
        for (k, t), w in zip(texts, widths):
            a = alpha * (0.4 if k in disabled else 1.0)
            if k == active_key:
                self.round_rect(cx, y + inset, w, h - inset * 2, (245, 245, 247, 255), alpha)
            tw, th = self.tsize(t)
            t.alpha = int(255 * min(a, 1.0))
            t.draw(dstrect=(cx + pad, y + (h - th) / 2, tw, th))
            out.append((k, (cx, y, w, h)))
            cx += w
        return out, total

    def toggle(self, on, x, y, alpha=1.0):
        w, h = 52, 32
        self.round_rect(x, y, w, h, (36, 138, 61, 255) if on else (72, 72, 74, 255), alpha)
        kx = x + (23 if on else 3)
        self.round_rect(kx, y + 3, 26, 26, (255, 255, 255, 255), alpha)
        return (x, y, w, h)
