"""Efecto Ken Burns: la foto de la presentación se acerca, se aleja o se
desplaza muy despacio mientras está en pantalla.

Todo se expresa respecto al rectángulo donde se dibuja la foto: un factor de
zoom y un desplazamiento del centro (como fracción del ancho y del alto). El
desplazamiento nunca pasa de (zoom - 1) / 2, así la foto siempre sigue
cubriendo su rectángulo y no se asoman orillas.
"""

import math
import random

from . import config as C

OFF, ZOOM, PAN = "off", "zoom", "pan"
# Una foto está en pantalla durante su fundido de entrada, su tiempo y el de salida.
SPAN = C.SLIDE_TIME + 2 * C.FADE_TIME + 0.4
ZOOM_RANGE = 0.08          # solo zoom: de 1.00 a 1.08 (o al revés)
PAN_ZOOM = (1.07, 1.12)    # zoom y paneo: un poco más de zoom para tener espacio
FOCUS = 0.3                # hacia dónde se acerca: hasta 30 % del centro a la orilla
PAN_REACH = 0.85           # cuánto del espacio disponible recorre el paneo


class Motion:
    """El movimiento de una foto. style: OFF, ZOOM o PAN."""

    def __init__(self, style, rng=random):
        self.style = style
        zin = rng.random() < 0.5
        if style == ZOOM:
            self.z0, self.z1 = (1.0, 1.0 + ZOOM_RANGE) if zin else (1.0 + ZOOM_RANGE, 1.0)
            self.fx, self.fy = rng.uniform(-FOCUS, FOCUS), rng.uniform(-FOCUS, FOCUS)
        elif style == PAN:
            self.z0, self.z1 = PAN_ZOOM if zin else PAN_ZOOM[::-1]
            ang = rng.uniform(0, 2 * math.pi)
            self.dx, self.dy = math.cos(ang), math.sin(ang)
        else:
            self.z0 = self.z1 = 1.0

    def at(self, t):
        """(zoom, dx, dy) a los `t` segundos; dx y dy son fracciones del rectángulo."""
        if self.style not in (ZOOM, PAN):
            return 1.0, 0.0, 0.0
        p = min(1.0, max(0.0, t / SPAN))
        z = self.z0 + (self.z1 - self.z0) * p
        if self.style == ZOOM:
            # El punto de enfoque se queda quieto mientras todo crece a su alrededor.
            return z, self.fx * (1 - z), self.fy * (1 - z)
        room = (z - 1) / 2 * PAN_REACH
        k = -1 + 2 * p
        return z, self.dx * k * room, self.dy * k * room


def apply(rect, z, dx, dy, amount=1.0):
    """Aplica el movimiento a un rectángulo (x, y, w, h). amount 0..1 lo
    mezcla con la posición sin efecto (para entrar y salir suave)."""
    x, y, w, h = rect
    z = 1 + (z - 1) * amount
    cx = x + w / 2 + dx * amount * w
    cy = y + h / 2 + dy * amount * h
    w2, h2 = w * z, h * z
    return cx - w2 / 2, cy - h2 / 2, w2, h2
