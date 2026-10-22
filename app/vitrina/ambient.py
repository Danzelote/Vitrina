"""Fondo de la pantalla sin fotos: cuadros blancos enormes y muy desenfocados
que se asoman por las orillas, se acercan despacio y se desvanecen (uno tras
otro, en distintos lugares). Algo que se mueve, muy leve, detrás del código.

Valores elegidos con la vista previa: opacidad 40 %, velocidad 0.5×,
tamaño 130 %, desenfoque 25 px (en una pantalla de 800 px de alto).
"""

import math
import random

import pygame
from pygame._sdl2.video import Texture

MAX_ALPHA = 0.40
SPEED = 0.5
SIZE = 1.30                 # lado del cuadro, en veces el lado corto de la pantalla
BLUR = 25 / (800 * SIZE)    # desenfoque relativo al tamaño del cuadro
LIFE, EVERY = 9.0, 4.5      # segundos (a velocidad 1): cuánto dura cada uno y cada cuánto sale otro
SPOTS = [(0, 0), (1, 1), (1, 0), (0, 1), (0.5, -0.1), (-0.1, 0.55), (1.1, 0.45), (0.45, 1.1)]


def _smooth(u):
    return u * u * (3 - 2 * u)


class Ambient:
    def __init__(self):
        self.tex = None
        self.wins = []
        self.clock = 0.0
        self.next = EVERY * 0.6
        self.spot = 0
        self.started = False

    def _texture(self, ren):
        """Un cuadro redondeado blanco, ya desenfocado (con margen para el difuminado)."""
        if self.tex is None:
            from PIL import Image, ImageDraw, ImageFilter
            n = 256
            sigma = BLUR * n
            pad = int(sigma * 3) + 2
            im = Image.new("L", (n + 2 * pad, n + 2 * pad), 0)
            ImageDraw.Draw(im).rounded_rectangle((pad, pad, pad + n, pad + n), radius=int(n * 0.18), fill=255)
            im = im.filter(ImageFilter.GaussianBlur(sigma))
            rgba = Image.merge("RGBA", (Image.new("L", im.size, 255),) * 3 + (im,))
            surf = pygame.image.frombuffer(rgba.tobytes(), rgba.size, "RGBA")
            self.tex = Texture.from_surface(ren, surf)
            self.tex.blend_mode = pygame.BLENDMODE_BLEND
            self.pad = pad / n
        return self.tex

    def _spawn(self, vw, vh):
        fx, fy = SPOTS[self.spot % len(SPOTS)]
        self.spot += 1
        size = min(vw, vh) * SIZE * (0.9 + random.random() * 0.25)
        ang = random.random() * math.tau
        dist = size * 0.18
        off_x = 0 if fx == 0.5 else (-size * 0.2 if fx < 0.5 else size * 0.2)
        off_y = 0 if fy == 0.5 else (-size * 0.2 if fy < 0.5 else size * 0.2)
        self.wins.append({"x": fx * vw - size / 2 + off_x, "y": fy * vh - size / 2 + off_y, "size": size,
                          "dx": math.cos(ang) * dist, "dy": math.sin(ang) * dist, "t": 0.0})

    def draw(self, ren, vw, vh, dt):
        if not self.started:
            self.started = True
            self._spawn(vw, vh)
        dt = min(0.1, dt) * SPEED
        self.clock += dt
        if self.clock >= self.next:
            self._spawn(vw, vh)
            self.next = self.clock + EVERY
        tex = self._texture(ren)
        alive = []
        for w in self.wins:
            w["t"] += dt
            if w["t"] >= LIFE:
                continue
            alive.append(w)
            u = w["t"] / LIFE
            a = MAX_ALPHA * math.sin(math.pi * u) ** 2       # sube suave desde 0 y vuelve a 0
            m = _smooth(u)
            s = w["size"] * (0.92 + 0.16 * m)               # se acerca, apenas
            x = w["x"] + w["dx"] * m - (s - w["size"]) / 2
            y = w["y"] + w["dy"] * m - (s - w["size"]) / 2
            p = s * self.pad
            tex.alpha = int(255 * a)
            tex.draw(dstrect=(x - p, y - p, s + 2 * p, s + 2 * p))
        self.wins = alive
