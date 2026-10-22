"""Curvas de animación y tweens."""

import time


def cubic_bezier(x1, y1, x2, y2):
    """Devuelve una función f(t) equivalente a cubic-bezier() de CSS."""

    def bx(u):
        return 3 * (1 - u) ** 2 * u * x1 + 3 * (1 - u) * u ** 2 * x2 + u ** 3

    def by(u):
        return 3 * (1 - u) ** 2 * u * y1 + 3 * (1 - u) * u ** 2 * y2 + u ** 3

    def dbx(u):
        return 3 * (1 - u) ** 2 * x1 + 6 * (1 - u) * u * (x2 - x1) + 3 * u ** 2 * (1 - x2)

    def f(t):
        if t <= 0:
            return 0.0
        if t >= 1:
            return 1.0
        u = t
        for _ in range(8):
            d = dbx(u)
            if abs(d) < 1e-6:
                break
            u -= (bx(u) - t) / d
            u = min(max(u, 0.0), 1.0)
        lo, hi = 0.0, 1.0
        for _ in range(20):
            if abs(bx(u) - t) < 1e-5:
                break
            if bx(u) < t:
                lo = u
            else:
                hi = u
            u = (lo + hi) / 2
        return by(u)

    return f


# La curva "tipo Apple" que usamos en el prototipo.
EASE = cubic_bezier(0.2, 0.8, 0.2, 1.0)
EASE_IN_OUT = cubic_bezier(0.65, 0.0, 0.35, 1.0)


def lerp(a, b, t):
    return a + (b - a) * t


class Tween:
    """Interpola una tupla de números entre dos valores durante un tiempo."""

    def __init__(self, start, end, duration, ease=EASE, now=None):
        self.start = tuple(start)
        self.end = tuple(end)
        self.duration = max(duration, 1e-6)
        self.ease = ease
        self.t0 = time.monotonic() if now is None else now

    def progress(self, now):
        return min(max((now - self.t0) / self.duration, 0.0), 1.0)

    def value(self, now):
        k = self.ease(self.progress(now))
        return tuple(lerp(a, b, k) for a, b in zip(self.start, self.end))

    def done(self, now):
        return now - self.t0 >= self.duration
