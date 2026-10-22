"""Logo de arranque mientras carga la app.

Es lo primero que se dibuja (antes de cargar las librerías pesadas y de leer
las fotos), en el mismo lugar y con la misma animación que el logo de Linux
(os/rootfs/usr/share/plymouth/themes/vitrina): así no hay hueco negro entre
los dos. Luego la app sigue la animación (ui.py: draw_intro) con el mismo
reloj y hace la entrada a la galería.
"""

import os
import time

import pygame
from pygame._sdl2.video import Renderer, Texture, Window

PERIOD, DELAY = 2.4, 0.6        # una vuelta de los 4 cuadros; desfase entre cuadros
SQ, STEP = 38.5, 45.5           # cuadro y distancia entre cuadros (ventana de 84×84)
FONTS = os.path.join(os.path.dirname(__file__), "fonts")


def smooth(u):
    return u * u * (3 - 2 * u)


def logo_scale(k, t):
    """Cada cuadro crece suave mientras el anterior se encoge (como el hover)."""
    local = ((t - k * DELAY) % PERIOD) / PERIOD
    if local < 0.25:
        return 0.9 + 0.1 * smooth(local / 0.25)
    if local < 0.5:
        return 1.0 - 0.1 * smooth((local - 0.25) / 0.25)
    return 0.9


def logo_origin(vw, vh):
    """Esquina de la ventana del logo (el texto va abajo)."""
    return vw / 2 - 42, vh / 2 - 70


def square_rects(vw, vh, t):
    """Rectángulos de los 4 cuadros en el momento t. Cada uno crece desde su
    propio centro, como las fotos de la cuadrícula al pasar el mouse."""
    wx, wy = logo_origin(vw, vh)
    homes = [(wx, wy), (wx + STEP, wy), (wx + STEP, wy + STEP), (wx, wy + STEP)]
    out = []
    for k in range(4):
        size = SQ * logo_scale(k, t)
        cx, cy = homes[k][0] + SQ / 2, homes[k][1] + SQ / 2
        out.append((cx - size / 2, cy - size / 2, size))
    return out


class Splash:
    def __init__(self, fullscreen=False, size=(1280, 800)):
        pygame.display.init()
        pygame.font.init()
        self.win = Window("Vitrina", size=size, resizable=True, allow_high_dpi=True)
        if fullscreen:
            self.win.set_fullscreen(True)
        self.ren = Renderer(self.win, accelerated=-1, vsync=True)
        pygame.mouse.set_visible(False)
        self.start = time.monotonic()
        self.ren.logical_size = (0, 0)
        out_w = self.ren.get_viewport().width
        win_w, win_h = self.win.size
        dpi = max(1.0, out_w / win_w) if win_w else 1.0
        self.ren.logical_size = (win_w, win_h)
        self.vw, self.vh = win_w, win_h
        # Cuadro blanco redondeado, dibujado grande y reducido (orillas suaves).
        px = max(8, round(SQ * 2 * dpi))
        big = pygame.Surface((px * 4, px * 4), pygame.SRCALPHA)
        pygame.draw.rect(big, (255, 255, 255), big.get_rect(), border_radius=round(px * 4 * 7 / SQ))
        self.square = Texture.from_surface(self.ren, pygame.transform.smoothscale(big, (px, px)))
        bold = pygame.font.Font(os.path.join(FONTS, "Inter-SemiBold.ttf"), round(22 * dpi))
        reg = pygame.font.Font(os.path.join(FONTS, "Inter-Regular.ttf"), round(22 * dpi))
        self.t1 = Texture.from_surface(self.ren, bold.render("Vitrina", True, (255, 255, 255)))
        self.t2 = Texture.from_surface(self.ren, reg.render("OS", True, (142, 142, 147)))
        self.dpi = dpi

    def frame(self):
        t = time.monotonic() - self.start
        self.ren.draw_color = (0, 0, 0, 255)
        self.ren.clear()
        for x, y, size in square_rects(self.vw, self.vh, t):
            self.square.draw(dstrect=(x, y, size, size))
        _wx, wy = logo_origin(self.vw, self.vh)
        w1, h1 = self.t1.width / self.dpi, self.t1.height / self.dpi
        w2 = self.t2.width / self.dpi
        x0 = self.vw / 2 - (w1 + 6 + w2) / 2
        self.t1.draw(dstrect=(x0, wy + 84 + 28, w1, h1))
        self.t2.draw(dstrect=(x0 + w1 + 6, wy + 84 + 28, w2, h1))
        self.ren.present()

    def run_until(self, done):
        """Anima el logo hasta que `done()` sea verdadero (la app ya cargó)."""
        clock = pygame.time.Clock()
        while not done():
            pygame.event.pump()
            self.frame()
            clock.tick(60)
