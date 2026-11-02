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


MARGIN = 0.04              # las caras quedan al menos a esta distancia de la orilla


def _fits(faces, z, dx, dy):
    """¿Todas las caras quedan dentro de la pantalla con este zoom y desplazamiento?
    faces: [(x0, y0, x1, y1)] relativas al centro del rectángulo (de -0.5 a 0.5)."""
    lo, hi = -0.5 + MARGIN, 0.5 - MARGIN
    for x0, y0, x1, y1 in faces:
        if dx + x0 * z < lo or dx + x1 * z > hi or dy + y0 * z < lo or dy + y1 * z > hi:
            return False
    return True


class Motion:
    """El movimiento de una foto. style: OFF, ZOOM o PAN.
    faces: cajas de las caras (ver _fits); si hay, el movimiento las respeta:
    nunca quedan cortadas y el zoom se acerca hacia ellas."""

    def __init__(self, style, rng=random, faces=None):
        self.style = style
        zin = rng.random() < 0.5
        faces = [f for f in (faces or []) if _fits([f], 1.0, 0.0, 0.0)]   # las que ya se ven completas
        if faces and style in (ZOOM, PAN) and self._for_faces(style, faces, zin, rng):
            return
        if style == ZOOM:
            self.z0, self.z1 = (1.0, 1.0 + ZOOM_RANGE) if zin else (1.0 + ZOOM_RANGE, 1.0)
            self.fx, self.fy = rng.uniform(-FOCUS, FOCUS), rng.uniform(-FOCUS, FOCUS)
        elif style == PAN:
            self.z0, self.z1 = PAN_ZOOM if zin else PAN_ZOOM[::-1]
            ang = rng.uniform(0, 2 * math.pi)
            self.dx, self.dy = math.cos(ang), math.sin(ang)
        else:
            self.z0 = self.z1 = 1.0

    def _for_faces(self, style, faces, zin, rng):
        """Elige un movimiento que deje las caras completas todo el tiempo."""
        x0 = min(f[0] for f in faces)
        y0 = min(f[1] for f in faces)
        x1 = max(f[2] for f in faces)
        y1 = max(f[3] for f in faces)
        fx, fy = (x0 + x1) / 2, (y0 + y1) / 2
        if style == PAN:
            # Varias direcciones al azar; se queda con la primera en que las
            # caras se ven completas al principio y al final (y en medio, por ser recto).
            for zr in (PAN_ZOOM, (1.05, 1.09), (1.03, 1.06)):
                z0, z1 = zr if zin else zr[::-1]
                for _ in range(24):
                    ang = rng.uniform(0, 2 * math.pi)
                    dx, dy = math.cos(ang), math.sin(ang)
                    r0, r1 = (z0 - 1) / 2 * PAN_REACH, (z1 - 1) / 2 * PAN_REACH
                    if _fits(faces, z0, -dx * r0, -dy * r0) and _fits(faces, z1, dx * r1, dy * r1):
                        self.z0, self.z1, self.dx, self.dy = z0, z1, dx, dy
                        return True
            style = ZOOM            # no hay paneo que sirva: un acercamiento suave a las caras
        # Acercarse hacia las caras (el punto fijo es su centro), lo más que se pueda sin cortarlas.
        top = 1.0 + ZOOM_RANGE
        while top > 1.005 and not _fits(faces, top, fx * (1 - top), fy * (1 - top)):
            top -= 0.005
        if top <= 1.005:
            return False
        self.style = ZOOM
        self.z0, self.z1 = (1.0, top) if zin else (top, 1.0)
        self.fx, self.fy = max(-0.5, min(0.5, fx)), max(-0.5, min(0.5, fy))
        return True

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
