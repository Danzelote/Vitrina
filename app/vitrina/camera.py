"""Lógica de la cámara de la cuadrícula, sin nada de dibujo.

Coordenadas:
- "plano": donde viven las miniaturas (a zoom 1, 1 unidad = 1 px).
- "pantalla": píxeles de la ventana.
La cámara se describe con (cx, cy, s): el punto del plano que queda al centro
de la pantalla y la escala. Un punto x del plano cae en pantalla en
tx + s * x, con tx = VW / 2 - s * cx.

Todo se puede probar sin abrir ventana (ver tests/test_camera.py).
"""

from dataclasses import dataclass

from . import config as C


@dataclass
class Plane:
    """Tamaño de la cuadrícula en unidades de plano. Con `count`, la última
    fila (si queda incompleta) va centrada."""
    cols: int
    rows: int
    count: int = None

    def _row_offset(self, row):
        if self.count is None or row != self.rows - 1:
            return 0.0
        missing = self.cols * self.rows - self.count
        return max(0, missing) * (C.CELL + C.GAP) / 2

    @property
    def width(self):
        return self.cols * C.CELL + (self.cols - 1) * C.GAP

    @property
    def height(self):
        return self.rows * C.CELL + (self.rows - 1) * C.GAP

    def cell_center(self, i):
        col, row = i % self.cols, i // self.cols
        pitch = C.CELL + C.GAP
        return self._row_offset(row) + col * pitch + C.CELL / 2, row * pitch + C.CELL / 2

    def index_at(self, px, py, count):
        """Índice de la miniatura en el punto (px, py) del plano, o None."""
        pitch = C.CELL + C.GAP
        if py < 0:
            return None
        row = int(py // pitch)
        px -= self._row_offset(row)
        if px < 0:
            return None
        col = int(px // pitch)
        if col >= self.cols or row >= self.rows:
            return None
        if px - col * pitch > C.CELL or py - row * pitch > C.CELL:
            return None
        i = row * self.cols + col
        return i if i < count else None


def grid_shape(count, aspect=1.6, square_up_to=64):
    """Columnas y filas para `count` fotos. Con pocas fotos la cuadrícula es
    cuadrada y crece desde el centro (4 → 2×2, 9 → 3×3); con muchas, toma
    una proporción parecida a la pantalla."""
    count = max(1, count)
    if count <= square_up_to:
        cols = -(-int(count ** 0.5 * 1000) // 1000)          # techo de la raíz
        while cols * cols < count:
            cols += 1
    else:
        cols = round((count * aspect) ** 0.5)
    rows = max(1, -(-count // cols))
    return cols, rows


def to_screen(cx, cy, s, vw, vh):
    """(cx, cy, s) -> (tx, ty, s)."""
    return vw / 2 - s * cx, vh / 2 - s * cy, s


def from_screen(tx, ty, s, vw, vh):
    """(tx, ty, s) -> (cx, cy, s)."""
    return (vw / 2 - tx) / s, (vh / 2 - ty) / s, s


def bounds(s, plane, vw, vh):
    """Rango permitido para el centro de la cámara a escala s.

    En el límite, la orilla de la cuadrícula queda a MARGIN_* px de la orilla
    de la pantalla."""
    hw, hh = vw / (2 * s), vh / (2 * s)
    return (hw - C.MARGIN_X / s, plane.width - hw + C.MARGIN_X / s,
            hh - C.MARGIN_TOP / s, plane.height - hh + C.MARGIN_BOTTOM / s)


def clamp(cx, cy, s, plane, vw, vh):
    lox, hix, loy, hiy = bounds(s, plane, vw, vh)
    x = plane.width / 2 if lox >= hix else min(max(cx, lox), hix)
    y = plane.height / 2 if loy >= hiy else min(max(cy, loy), hiy)
    return x, y


def active_range(s, vertical, vw, vh):
    """Zona de la pantalla donde el mouse recorre la cuadrícula.

    Termina a la mitad de la primera/última fila visible en el límite, para que
    con el mouse sobre esa fila ya se vea completa."""
    half = C.CELL * s / 2
    if vertical:
        a, b = C.MARGIN_TOP + half, vh - C.MARGIN_BOTTOM - half
        v = vh
    else:
        a, b = C.MARGIN_X + half, vw - C.MARGIN_X - half
        v = vw
    if a >= b:
        a, b = v / 2 - 1, v / 2 + 1
    return a, b


def pw_map(m, m0, c0, lo, hi, a, b, w, v):
    """Posición de la cámara para la posición m del mouse.

    Mezcla dos mapas:
    - uno "anclado": en m0 la cámara está en c0 y se estira hasta lo/hi hacia
      cada orilla (sin saltos al entrar, salir o hacer zoom);
    - uno absoluto: cada posición del mouse es siempre la misma zona.
    w (0..1) es el peso del anclado; decae conforme se mueve el mouse.
    Llegar a cualquier orilla siempre da lo o hi."""
    ma = min(max(m, a), b)
    absolute = lo + (ma - a) / (b - a) * (hi - lo)
    # El tramo anclado se ensancha si el ancla quedó fuera de la zona activa,
    # para que el punto de partida nunca coincida con una orilla.
    a2 = min(a, max(0.0, m0 - 30))
    b2 = max(b, min(v, m0 + 30))
    mm = min(max(m, a2), b2)
    mc = min(max(m0, a2), b2)
    cc = min(max(c0, lo), hi)
    if mm <= a2 + 0.5:
        anchored = lo
    elif mm >= b2 - 0.5:
        anchored = hi
    elif mm <= mc:
        anchored = cc - (mc - mm) / (mc - a2) * (cc - lo)
    else:
        anchored = cc + (mm - mc) / (b2 - mc) * (hi - cc)
    return w * anchored + (1 - w) * absolute


@dataclass
class Anchor:
    mx: float
    my: float
    cx: float
    cy: float
    travel: float = 0.0
    px: float = 0.0
    py: float = 0.0

    def __post_init__(self):
        self.px, self.py = self.mx, self.my

    def moved(self, mx, my):
        self.travel += ((mx - self.px) ** 2 + (my - self.py) ** 2) ** 0.5
        self.px, self.py = mx, my

    @property
    def weight(self):
        import math
        return math.exp(-self.travel / C.ANCHOR_DECAY_PX)


def pan_target(mx, my, anchor, s, plane, vw, vh):
    """Centro de cámara que corresponde al mouse en (mx, my)."""
    lox, hix, loy, hiy = bounds(s, plane, vw, vh)
    w = anchor.weight
    if lox >= hix:
        x = plane.width / 2
    else:
        a, b = active_range(s, False, vw, vh)
        x = pw_map(mx, anchor.mx, anchor.cx, lox, hix, a, b, w, vw)
    if loy >= hiy:
        y = plane.height / 2
    else:
        a, b = active_range(s, True, vw, vh)
        y = pw_map(my, anchor.my, anchor.cy, loy, hiy, a, b, w, vh)
    return x, y


def zoom_at(cx, cy, s0, s1, fx, fy, vw, vh):
    """Nuevo centro al pasar de escala s0 a s1 dejando fijo el punto de
    pantalla (fx, fy), normalmente el cursor."""
    px = cx + (fx - vw / 2) / s0
    py = cy + (fy - vh / 2) / s0
    return px - (fx - vw / 2) / s1, py - (fy - vh / 2) / s1


class Grid:
    """Las fotos que se ven en la cuadrícula (todas, o las de una colección o
    búsqueda), acomodadas en su propia cuadrícula desde el centro. Se usa como
    un Plane, pero con índices de foto (no de casilla)."""

    def __init__(self, members):
        self.members = list(members)
        self.slot = {i: k for k, i in enumerate(self.members)}
        self.plane = Plane(*grid_shape(max(1, len(self.members))), len(self.members))

    cols = property(lambda self: self.plane.cols)
    rows = property(lambda self: self.plane.rows)
    count = property(lambda self: len(self.members))
    width = property(lambda self: self.plane.width)
    height = property(lambda self: self.plane.height)

    def __contains__(self, i):
        return i in self.slot

    def cell_center(self, i):
        k = self.slot.get(i)
        if k is None:                        # no está en esta cuadrícula: el centro
            return self.plane.width / 2, self.plane.height / 2
        return self.plane.cell_center(k)

    def index_at(self, px, py, count=None):
        k = self.plane.index_at(px, py, len(self.members))
        return None if k is None else self.members[k]

    def item_at_slot(self, k):
        return self.members[k] if 0 <= k < len(self.members) else None
