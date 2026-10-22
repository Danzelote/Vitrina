"""Niveles de agrupación: meses (calendario), años y colecciones.

Este módulo calcula los grupos y su acomodo en pantalla, y dibuja los cuadros
con su mini presentación. Las coordenadas aquí son de pantalla (puntos)."""

from dataclasses import dataclass, field

from . import config as C

MONTH_ABBR = ["Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"]
MONTH_NAMES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
               "septiembre", "octubre", "noviembre", "diciembre"]

# Calendario de meses
M_TILE = 164
M_PITCH = 180
M_LABEL_W = 130
M_BLOCK = 400                      # alto de cada año (dos filas de seis meses)
M_WIDTH = M_LABEL_W + 6 * M_PITCH - (M_PITCH - M_TILE)
TOP = 96                           # bajo la barra superior
BOTTOM = 84

CYCLE = 5.4                        # segundos por foto en la mini presentación
FADE_PART = 0.22                   # fracción del ciclo que dura el fundido


@dataclass
class Group:
    kind: str                      # "month" | "year" | "coll"
    key: object
    members: list = field(default_factory=list)   # índices de fotos, de la más reciente a la más antigua
    order: int = 0                 # para escalonar las mini presentaciones


@dataclass
class Tile:
    group: Group
    x: float
    y: float
    size: float
    title: str
    sub: str


def plural(n, one="foto", many="fotos"):
    return f"{n:,} {one if n == 1 else many}".replace(",", ",")


class Groups:
    def __init__(self, items):
        self.months, self.years, self.colls = {}, {}, {}
        for i, it in enumerate(items):
            mk = (it.date.year, it.date.month)
            self.months.setdefault(mk, Group("month", mk)).members.append(i)
            self.years.setdefault(it.date.year, Group("year", it.date.year)).members.append(i)
            if it.collection:
                self.colls.setdefault(it.collection, Group("coll", it.collection)).members.append(i)
        self.year_list = sorted(self.years, reverse=True)
        self.coll_list = sorted(self.colls, key=lambda k: -len(self.colls[k].members))
        for n, g in enumerate(list(self.months.values()) + list(self.years.values()) + list(self.colls.values())):
            g.order = n

    @property
    def has_years(self):
        return len(self.year_list) >= 2

    # -- calendario de meses ---------------------------------------------------

    def months_geometry(self, vw, vh):
        """(x0, alto del contenido, ty máximo, ty mínimo). ty es el desplazamiento
        vertical: en ty máximo se ve el año más reciente arriba."""
        h = len(self.year_list) * M_BLOCK - (M_BLOCK - 2 * M_PITCH + (M_PITCH - M_TILE))
        avail = vh - TOP - BOTTOM
        x0 = (vw - M_WIDTH) / 2
        if h <= avail:
            ty = TOP + (avail - h) / 2
            return x0, h, ty, ty
        return x0, h, TOP, TOP - (h - avail)

    def month_scroll_for_year(self, year, vw, vh):
        """Fracción de desplazamiento (0..1) que muestra `year` arriba."""
        _x0, _h, ty_max, ty_min = self.months_geometry(vw, vh)
        if ty_max == ty_min or year not in self.year_list:
            return 0.0
        ty = TOP + 20 - self.year_list.index(year) * M_BLOCK
        return min(max((ty_max - ty) / (ty_max - ty_min), 0.0), 1.0)

    def month_layout(self, frac, vw, vh):
        """Devuelve (etiquetas de año, cuadros llenos, huecos vacíos)."""
        x0, _h, ty_max, ty_min = self.months_geometry(vw, vh)
        ty = ty_max - frac * (ty_max - ty_min)
        labels, tiles, empty = [], [], []
        for yi, y in enumerate(self.year_list):
            top = ty + yi * M_BLOCK
            if top > vh or top + M_BLOCK < 0:
                continue
            labels.append((str(y), plural(len(self.years[y].members)), x0, top + 6))
            for m in range(12):
                x = x0 + M_LABEL_W + (m % 6) * M_PITCH
                yy = top + (m // 6) * M_PITCH
                g = self.months.get((y, m + 1))
                if g:
                    tiles.append(Tile(g, x, yy, M_TILE, MONTH_ABBR[m], plural(len(g.members))))
                else:
                    empty.append((MONTH_ABBR[m], x, yy, M_TILE))
        return labels, tiles, empty

    # -- años y colecciones ----------------------------------------------------

    @staticmethod
    def grid_layout(n, vw, vh, max_size=300, gap=28):
        if n == 0:
            return []
        cols = n if n <= 3 else (2 if n == 4 else 3)
        rows = -(-n // cols)
        avail_w, avail_h = min(1200, vw - 80), vh - TOP - BOTTOM - 20
        size = min(max_size, (avail_w - (cols - 1) * gap) / cols, (avail_h - (rows - 1) * gap) / rows)
        w, h = cols * size + (cols - 1) * gap, rows * size + (rows - 1) * gap
        left, top = (vw - w) / 2, TOP + (vh - TOP - BOTTOM - h) / 2
        return [(left + (i % cols) * (size + gap), top + (i // cols) * (size + gap), size) for i in range(n)]

    def year_tiles(self, vw, vh):
        pos = self.grid_layout(len(self.year_list), vw, vh)
        return [Tile(self.years[y], x, yy, s, str(y), plural(len(self.years[y].members)))
                for y, (x, yy, s) in zip(self.year_list, pos)]

    def coll_tiles(self, vw, vh):
        pos = self.grid_layout(len(self.coll_list), vw, vh)
        out = []
        for k, (x, yy, s) in zip(self.coll_list, pos):
            inset = 14  # deja ver las "tarjetas" de atrás
            out.append(Tile(self.colls[k], x, yy + inset, s - inset, k, plural(len(self.colls[k].members))))
        return out


def covers(group, count=4):
    """Hasta `count` fotos repartidas a lo largo del grupo."""
    n = min(count, len(group.members))
    return [group.members[int(k * len(group.members) / n)] for k in range(n)]


class View:
    """Escala la capa alrededor de un punto (para entrar y salir de niveles)."""

    def __init__(self, k=1.0, ox=0.0, oy=0.0):
        self.k, self.ox, self.oy = k, ox, oy

    def pt(self, x, y):
        return self.ox + (x - self.ox) * self.k, self.oy + (y - self.oy) * self.k

    def rect(self, x, y, w, h):
        x2, y2 = self.pt(x, y)
        return x2, y2, w * self.k, h * self.k


def _text(g, s, size, color, bold, x, y, alpha, view, anchor_bottom=False):
    t = g.text(s, size, color, bold)
    w, h = g.tsize(t)
    t.alpha = int(255 * min(alpha, 1.0))
    t.draw(dstrect=view.rect(x, y - (h if anchor_bottom else 0), w, h))
    return h


def draw_tile(g, items, tile, now, alpha, bg, hover=0.0, title_size=16, folder=False, view=None):
    """Un cuadro de grupo con su mini presentación. Devuelve su rectángulo en pantalla."""
    view = view or View()
    if alpha <= 0.003:
        return None
    k = 1 + 0.04 * hover
    size = tile.size * k
    x = tile.x - (size - tile.size) / 2
    y = tile.y - (size - tile.size) / 2
    radius = (16 if tile.size < 200 else 20)
    if folder:
        g.round_rect(*view.rect(x + 26, y - 16, size - 52, size), (255, 255, 255, 18), alpha, radius * view.k)
        g.round_rect(*view.rect(x + 12, y - 8, size - 24, size), (255, 255, 255, 36), alpha, radius * view.k)
    rx, ry, rw, rh = view.rect(x, y, size, size)
    picks = covers(tile.group)
    phase = now / CYCLE + tile.group.order * 0.37
    cur = int(phase) % len(picks)
    frac = (phase % 1 - (1 - FADE_PART)) / FADE_PART
    textures = [g.thumb(items[i]) for i in picks]
    base = textures[cur] or next((t for t in textures if t), None)
    if base:
        g.image(base, rx, ry, rw, rh, alpha)
    else:
        g.rect(rx, ry, rw, rh, C.PLACEHOLDER, alpha)
    if frac > 0 and len(picks) > 1:
        nxt = textures[(cur + 1) % len(picks)]
        if nxt:
            g.image(nxt, rx, ry, rw, rh, alpha * min(frac, 1.0))
    g.gradient.alpha = int(160 * min(alpha, 1.0))
    g.gradient.draw(dstrect=(rx, ry + rh * 0.4, rw, rh * 0.6))
    pad = 14 if tile.size < 200 else 20
    sub_size = 12 if tile.size < 200 else 14
    h2 = _text(g, tile.sub, sub_size, (229, 229, 234), False, x + pad, y + size - pad, alpha, view, True)
    _text(g, tile.title, title_size, C.TEXT, True, x + pad, y + size - pad - h2 + 2, alpha, view, True)
    g.corners(rx, ry, rw, rh, radius * view.k, bg, alpha)
    return (rx, ry, rw, rh)


def draw_empty(g, label, x, y, size, alpha, view=None):
    view = view or View()
    if alpha <= 0.003:
        return
    g.round_rect(*view.rect(x, y, size, size), (255, 255, 255, 10), alpha, 16 * view.k)
    _text(g, label, 15, (142, 142, 147), True, x + 14, y + size - 14, alpha, view, True)


def draw_year_label(g, title, sub, x, y, alpha, view=None):
    view = view or View()
    h = _text(g, title, 34, C.TEXT, True, x, y, alpha, view)
    _text(g, sub, 13, (161, 161, 166), False, x, y + h + 2, alpha, view)
