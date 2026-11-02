"""Colecciones automáticas: se arman solas con los datos de cada foto (fecha,
ubicación, lente, forma), sin internet ni inteligencia artificial.

- Viajes: fotos en días seguidos lejos de donde se toman casi todas.
- Eventos: varias fotos (3 o más) el mismo día, en pocas horas y en el mismo lugar.
- Selfies: tomadas con la cámara frontal (lo dice la foto).
- Panorámicas: muy alargadas.

Cada una tiene una clave estable (para poder ocultarla) y un título.
"""

import math
from collections import Counter
from datetime import timedelta

from . import i18n
from .i18n import tr

HOME_CELL = 0.25        # grados (~25 km) para encontrar "casa"
TRIP_KM = 60            # más lejos que esto de casa es viaje
TRIP_GAP = timedelta(days=2)
TRIP_MIN = 4
EVENT_GAP = timedelta(hours=3)
EVENT_SPAN = timedelta(hours=10)
EVENT_KM = 3
EVENT_MIN = 3
PANO_RATIO = 2.2


class Auto:
    def __init__(self, key, kind, title, keys):
        self.key = key          # "auto:viaje:…"
        self.kind = kind        # "trip" | "event" | "selfies" | "panos"
        self.title = title
        self.keys = keys        # claves de las fotos, en orden


def km(a, b):
    dy = (a[0] - b[0]) * 111.2
    dx = (a[1] - b[1]) * 111.2 * math.cos(math.radians((a[0] + b[0]) / 2))
    return math.hypot(dx, dy)


def _home(items):
    cells = Counter((round(it.lat / HOME_CELL), round(it.lon / HOME_CELL))
                    for it in items if it.lat is not None and it.lon is not None)
    if not cells:
        return None
    (a, b), _ = cells.most_common(1)[0]
    return a * HOME_CELL, b * HOME_CELL


def _city(item, place_of):
    p = place_of(item) if item.lat is not None else None
    return p.split(",")[0].strip() if p else None


def _common_city(items, place_of):
    names = Counter(c for c in (_city(it, place_of) for it in items) if c)
    return names.most_common(1)[0][0] if names else None


def _month_year(d):
    m = (i18n.MONTHS_EN if i18n.lang() == "en" else i18n.MONTHS_ES)[d.month - 1]
    return f"{m} {d.year}"


def _day_title(d):
    if i18n.lang() == "en":
        days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        return f"{days[d.weekday()]}, {i18n.MONTHS_EN[d.month - 1]} {d.day}, {d.year}"
    days = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]
    return f"{days[d.weekday()]} {d.day} de {i18n.MONTHS_ES[d.month - 1]} de {d.year}"


def build(items, place_of, hidden=()):
    """[Auto] para estas fotos (sin las que la persona ocultó)."""
    dated = sorted((it for it in items if it.dated), key=lambda it: it.date)
    out = []
    in_trip = set()
    # -- viajes ------------------------------------------------------------------
    home = _home(dated)
    if home:
        away = [it for it in dated if it.lat is not None and km((it.lat, it.lon), home) > TRIP_KM]
        groups, cur = [], []
        for it in away:
            if cur and it.date - cur[-1].date > TRIP_GAP:
                groups.append(cur)
                cur = []
            cur.append(it)
        if cur:
            groups.append(cur)
        for g in groups:
            # También las fotos sin ubicación tomadas durante el viaje.
            start, end = g[0].date, g[-1].date
            members = [it for it in dated if start <= it.date <= end and
                       (it.lat is None or km((it.lat, it.lon), home) > TRIP_KM)]
            if len(members) < TRIP_MIN:
                continue
            city = _common_city(members, place_of)
            title = f"{city} · {_month_year(start)}" if city else tr("Viaje · {m}", m=_month_year(start))
            out.append(Auto(f"auto:viaje:{start:%Y%m%d}", "trip", title, [it.key for it in members]))
            in_trip.update(it.key for it in members)
    # -- eventos -----------------------------------------------------------------
    rest = [it for it in dated if it.key not in in_trip]
    groups, cur = [], []
    for it in rest:
        if cur and (it.date - cur[-1].date > EVENT_GAP or it.date.date() != cur[0].date.date()
                    or it.date - cur[0].date > EVENT_SPAN):
            groups.append(cur)
            cur = []
        cur.append(it)
    if cur:
        groups.append(cur)
    for g in groups:
        if len(g) < EVENT_MIN:
            continue
        spots = [(it.lat, it.lon) for it in g if it.lat is not None]
        if spots and max(km(a, b) for a in spots for b in spots) > EVENT_KM:
            continue                        # varios lugares: no es un solo evento
        city = _common_city(g, place_of)
        day = _day_title(g[0].date)
        title = f"{day} · {city}" if city else day
        out.append(Auto(f"auto:evento:{g[0].date:%Y%m%d%H%M}", "event", title, [it.key for it in g]))
    # -- selfies y panorámicas ---------------------------------------------------
    selfies = [it.key for it in items if "front" in (it.lens or "").lower()]
    if selfies:
        out.append(Auto("auto:selfies", "selfies", tr("Selfies"), selfies))
    panos = [it.key for it in items if not it.is_video and it.ready and it.height and
             max(it.aspect, 1 / it.aspect) >= PANO_RATIO]
    if panos:
        out.append(Auto("auto:panoramicas", "panos", tr("Panorámicas"), panos))
    hidden = set(hidden)
    trips = sorted((a for a in out if a.kind == "trip"), key=lambda a: a.key, reverse=True)
    events = sorted((a for a in out if a.kind == "event"), key=lambda a: a.key, reverse=True)
    others = [a for a in out if a.kind in ("selfies", "panos")]
    return [a for a in trips + events + others if a.key not in hidden]
