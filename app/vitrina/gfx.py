"""Ayudantes de dibujo sobre el renderizador acelerado de SDL2.

Todo se dibuja como texturas escaladas: es lo más barato para la gráfica y
funciona también con el renderizador por software de SDL si no hay aceleración.
"""

import math
import threading
import time
from collections import OrderedDict

import pygame
from PIL import Image
from pygame._sdl2.video import Texture

from . import config as C
from .theme import T

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


class Loader:
    """Decodifica imágenes (JPEG) en un hilo aparte. La interfaz pide una imagen
    y la recibe lista unos milisegundos después, sin detener las animaciones.
    Atiende primero lo pedido más recientemente (lo que se está viendo)."""

    def __init__(self):
        self.pending = OrderedDict()   # clave -> ruta
        self.done = []                 # (clave, bytes, tamaño)
        self.cv = threading.Condition()
        threading.Thread(target=self._run, daemon=True).start()

    def request(self, key, path):
        with self.cv:
            if key in self.pending:
                self.pending.move_to_end(key)
                return
            self.pending[key] = path
            while len(self.pending) > 400:   # olvida lo que ya no se necesita
                self.pending.popitem(last=False)
            self.cv.notify()

    def take(self, limit):
        with self.cv:
            out, self.done = self.done[:limit], self.done[limit:]
        return out

    def _run(self):
        while True:
            with self.cv:
                while not self.pending:
                    self.cv.wait()
                key, path = self.pending.popitem(last=True)
            try:
                with Image.open(path) as img:
                    # "g": versión en blanco y negro (para el reloj de noche)
                    img = img.convert("L").convert("RGB") if key[0] == "g" else img.convert("RGB")
                    data, size = img.tobytes(), img.size
            except Exception:
                data, size = None, None
            with self.cv:
                self.done.append((key, data, size))


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
        self.grays = LRU(4)
        circ = pygame.Surface((512, 512), pygame.SRCALPHA)
        pygame.draw.circle(circ, (255, 255, 255), (256, 256), 256)
        self.circle = self._tex(pygame.transform.smoothscale(circ, (256, 256)))
        self.texts = LRU(200)
        self.pills = LRU(160)
        self.anims = {}          # estado animado de controles (selectores, interruptores)
        self.now = time.monotonic()
        self.dt = 1 / 60
        self.fonts = {}
        self.loads_left = 0
        self.loader = Loader()
        self.requested = set()
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

    def begin_frame(self, budget_ms=6.0, now=None):
        """Sube a la gráfica las imágenes que el hilo ya decodificó, con un
        límite de tiempo por cuadro para no frenar la animación."""
        t0 = time.monotonic()
        now = t0 if now is None else now
        self.dt = min(max(now - self.now, 0.0), 0.1)
        self.now = now
        while (time.monotonic() - t0) * 1000 < budget_ms:
            batch = self.loader.take(1)
            if not batch:
                break
            (kind, key), data, size = batch[0]
            self.requested.discard((kind, key))
            if data is None:
                continue
            tex = self._tex(pygame.image.frombuffer(data, size, "RGB"))
            {"t": self.thumbs, "s": self.screens, "b": self.backdrops, "g": self.grays}[kind].put(key, tex)

    def rect(self, x, y, w, h, color, alpha=1.0):
        if alpha <= 0.003 or w <= 0 or h <= 0:
            return
        self.white.color = color[:3]
        self.white.alpha = int(255 * min(alpha, 1.0) * (color[3] / 255 if len(color) > 3 else 1))
        self.white.draw(dstrect=(x, y, w, h))

    def snap(self, x, y, w, h):
        """Alinea un rectángulo a píxeles reales, para que la foto y sus esquinas
        coincidan exactamente (si no, quedan rayitas de 1 px en los bordes)."""
        d = self.dpi
        x0, y0 = round(x * d) / d, round(y * d) / d
        x1, y1 = round((x + w) * d) / d, round((y + h) * d) / d
        return x0, y0, x1 - x0, y1 - y0

    def corners(self, x, y, w, h, r, color, alpha=1.0):
        x, y, w, h = self.snap(x, y, w, h)
        r = round(min(r, w / 2, h / 2) * self.dpi) / self.dpi
        if r < 0.75 or alpha <= 0.01:
            return
        t = self.corner
        t.color = color[:3]
        t.alpha = int(255 * min(alpha, 1.0))
        t.draw(dstrect=(x, y, r, r))
        t.draw(dstrect=(x + w - r, y, r, r), flip_x=True)
        t.draw(dstrect=(x, y + h - r, r, r), flip_y=True)
        t.draw(dstrect=(x + w - r, y + h - r, r, r), flip_x=True, flip_y=True)

    def image(self, tex, x, y, w, h, alpha=1.0, radius=0.0, corner_color=None, snap=True):
        """Dibuja `tex` llenando el rectángulo, recortada desde el centro para
        conservar la proporción (como object-fit: cover). Sin `snap` se dibuja
        en posiciones intermedias entre píxeles: movimientos lentos sin saltitos."""
        if alpha <= 0.003 or w <= 0 or h <= 0:
            return
        if snap:
            x, y, w, h = self.snap(x, y, w, h)
        if w <= 0 or h <= 0:
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
            self.corners(x, y, w, h, radius, corner_color or T.bg, alpha)

    # -- texturas de fotos ----------------------------------------------------

    def _cached(self, cache, kind, key, path):
        """La textura si ya está; si no, la pide al hilo de carga y devuelve None."""
        tex = cache.get_item(key)
        if tex is not None or not path:
            return tex
        if (kind, key) not in self.requested:
            self.requested.add((kind, key))
            self.loader.request((kind, key), path)
        return None

    def thumb(self, item, force=False):
        if not item.ready:
            return None
        return self._cached(self.thumbs, "t", item.key, item.thumb_path)

    def screen(self, item, force=False):
        if not item.ready:
            return None
        return self._cached(self.screens, "s", item.key, item.screen_path)

    def backdrop(self, item, force=False):
        if not item.ready or not item.vertical:
            return None
        return self._cached(self.backdrops, "b", item.key, item.backdrop_path)

    def gray(self, item):
        """La foto de pantalla en blanco y negro."""
        if not item.ready:
            return None
        return self._cached(self.grays, "g", item.key, item.screen_path)

    def has_screen(self, item):
        return item.key in self.screens

    # -- texto y píldoras -----------------------------------------------------

    def font(self, size, bold=False):
        key = (size, bold)
        if key not in self.fonts:
            self.fonts[key] = pygame.font.SysFont(FONT_NAMES, size, bold=bold)
        return self.fonts[key]

    def text(self, s, size, color=None, bold=False):
        """Texto renderizado a la resolución real; mide en puntos con tsize()."""
        color = color or T.text
        key = (s, size, bold, self.dpi)
        tex = self.texts.get_item(key)
        if tex is None:
            # Se dibuja en blanco y se tiñe al usarlo: cambiar de color (por ejemplo
            # al pasar de tema claro a oscuro) no obliga a dibujar el texto otra vez.
            surf = self.font(round(size * self.dpi), bold).render(s, True, (255, 255, 255))
            tex = self._tex(surf)
            self.texts.put(key, tex)
        tex.color = color[:3]
        return tex

    def tsize(self, tex):
        return tex.width / self.dpi, tex.height / self.dpi

    def shape(self, w, h, radius=None):
        """Rectángulo redondeado blanco (se tiñe al dibujarlo). radius None = píldora."""
        pw, ph = max(1, round(w * self.dpi)), max(1, round(h * self.dpi))
        r = ph // 2 if radius is None else min(ph // 2, pw // 2, round(radius * self.dpi))
        key = (pw, ph, r)
        tex = self.pills.get_item(key)
        if tex is None:
            surf = pygame.Surface((pw * 2, ph * 2), pygame.SRCALPHA)
            pygame.draw.rect(surf, (255, 255, 255), surf.get_rect(), border_radius=r * 2)
            tex = self._tex(pygame.transform.smoothscale(surf, (pw, ph)))
            self.pills.put(key, tex)
        return tex

    def fill_shape(self, x, y, w, h, color, alpha=1.0, radius=None):
        if alpha <= 0.003 or w < 1 or h < 1:
            return
        tex = self.shape(w, h, radius)
        tex.color = color[:3]
        tex.alpha = int(255 * min(alpha, 1.0) * (color[3] / 255 if len(color) > 3 else 1))
        tex.draw(dstrect=(x, y, w, h))

    def pill(self, label, cx, y, size=14, alpha=1.0, anchor="center", sublabel=None):
        """Una píldora con texto. `anchor` puede ser 'center' (cx es el centro)
        o 'left' (cx es la orilla izquierda). Devuelve su rectángulo."""
        if alpha <= 0.003:
            return None
        t1 = self.text(label, size, T.text, bold=True)
        t2 = self.text(sublabel, size, T.text_dim) if sublabel else None
        w1, h1 = self.tsize(t1)
        w2, h2 = self.tsize(t2) if t2 else (0, 0)
        pad, gap = 18, 8
        w = w1 + (gap + w2 if t2 else 0) + pad * 2
        h = max(40, h1 + 16)
        x = cx - w / 2 if anchor == "center" else cx
        self.fill_shape(x, y, w, h, T.pill, alpha)
        t1 = self.text(label, size, T.text, bold=True)
        t1.alpha = int(255 * alpha)
        t1.draw(dstrect=(x + pad, y + (h - h1) / 2, w1, h1))
        if t2:
            t2 = self.text(sublabel, size, T.text_dim)
            t2.alpha = int(255 * alpha)
            t2.draw(dstrect=(x + pad + w1 + gap, y + (h - h2) / 2, w2, h2))
        return (x, y, w, h)

    def label(self, s, x, y, size, alpha=1.0, bold=False, color=None):
        if alpha <= 0.003:
            return
        t = self.text(s, size, color, bold)
        t.alpha = int(255 * alpha)
        w, h = self.tsize(t)
        t.draw(dstrect=(x, y, w, h))

    def label_shadow(self, s, x, y, size, alpha=1.0, bold=False):
        """Texto blanco con una sombra suave, para leerse sobre cualquier foto."""
        if alpha <= 0.003:
            return 0, 0
        t = self.text(s, size, (0, 0, 0), bold)     # la misma textura, teñida
        w, h = self.tsize(t)
        t.alpha = int(90 * alpha)
        t.draw(dstrect=(x, y + max(1.0, size / 22), w, h))
        t.color = (255, 255, 255)
        t.alpha = int(255 * alpha)
        t.draw(dstrect=(x, y, w, h))
        return w, h

    def label_centered(self, s, cx, y, size, alpha=1.0, bold=False, color=None):
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
        self.fill_shape(x, y, w, h, color, alpha, radius)

    def button(self, label, x, y, h=44, alpha=1.0, active=False, bold=True, size=14, icon=None, pad=18):
        """Botón tipo píldora. Devuelve su rectángulo (x, y, w, h)."""
        fg = T.active_fg if active else T.text
        bg = T.active_bg if active else T.button
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

    def _approach(self, cur, target, tau=0.075):
        """Se acerca a `target` suave (como un resorte sin rebote)."""
        return cur + (target - cur) * (1 - math.exp(-self.dt / tau))

    def segmented(self, options, active_key, x, y, h=44, alpha=1.0, disabled=()):
        """Selector segmentado. options = [(clave, etiqueta)]. Devuelve
        [(clave, rect)] y el ancho total. La pastilla blanca se desliza de una
        opción a otra y los textos cambian de color conforme pasa encima."""
        size, pad, inset = 13, 14, 3
        labels = [(k, lbl, self.tsize(self.text(lbl, size, T.text, True))) for k, lbl in options]
        widths = [tw + pad * 2 for _, _, (tw, _) in labels]
        total = sum(widths) + inset * 2
        self.round_rect(x, y, total, h, T.button, alpha)
        offs, cx = [], inset
        for w in widths:
            offs.append(cx)
            cx += w
        # Posición animada de la pastilla, relativa al selector.
        key = ("seg",) + tuple(k for k, _ in options)
        target = next(((o, w) for (k, _, _), o, w in zip(labels, offs, widths) if k == active_key), None)
        st = self.anims.get(key)
        if target is None:
            self.anims.pop(key, None)
            st = None
        elif st is None or self.now - st[2] > 0.5:   # recién aparece: sin animar
            st = [target[0], target[1], self.now]
        else:
            st = [self._approach(st[0], target[0]), self._approach(st[1], target[1]), self.now]
        if st is not None:
            self.anims[key] = st
            self.round_rect(x + st[0], y + inset, st[1], h - inset * 2, T.active_bg, alpha)
        out = []
        p0, p1 = (x + st[0], x + st[0] + st[1]) if st is not None else (0.0, 0.0)
        for (k, lbl, (tw, th)), o, w in zip(labels, offs, widths):
            a = alpha * (0.4 if k in disabled else 1.0)
            tx, ty = x + o + pad, y + (h - th) / 2
            # La parte del texto que queda sobre la pastilla va en su color; el resto, normal.
            cuts = sorted({tx, tx + tw, min(max(p0, tx), tx + tw), min(max(p1, tx), tx + tw)})
            for c0, c1 in zip(cuts, cuts[1:]):
                if c1 - c0 < 0.01:
                    continue
                on_pill = p0 <= (c0 + c1) / 2 <= p1
                t = self.text(lbl, size, T.active_fg if on_pill else T.text, True)
                t.alpha = int(255 * min(a, 1.0))
                if c0 == tx and c1 == tx + tw:
                    t.draw(dstrect=(tx, ty, tw, th))
                else:
                    sx0, sx1 = (c0 - tx) / tw * t.width, (c1 - tx) / tw * t.width
                    t.draw(srcrect=(sx0, 0, sx1 - sx0, t.height), dstrect=(c0, ty, c1 - c0, th))
            out.append((k, (x + o, y, w, h)))
        return out, total

    def toggle(self, on, x, y, alpha=1.0, key=None):
        """Interruptor; con `key` la bolita se desliza y el color cambia suave."""
        w, h = 52, 32
        v = 1.0 if on else 0.0
        if key is not None:
            st = self.anims.get(("tog", key))
            if st is not None and self.now - st[1] <= 0.5:
                v = self._approach(st[0], v, 0.07)
            self.anims[("tog", key)] = (v, self.now)
        green, off = (36, 138, 61, 255), T.toggle_off
        color = tuple(round(off[i] + (green[i] - off[i]) * v) for i in range(4))
        self.round_rect(x, y, w, h, color, alpha)
        self.round_rect(x + 3 + 20 * v, y + 3, 26, 26, (255, 255, 255, 255), alpha)
        return (x, y, w, h)
