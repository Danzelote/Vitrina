""""Un día como hoy": fotos tomadas en estas fechas en años anteriores."""

from datetime import date

WINDOW_DAYS = 3     # cuenta como "este día" hasta 3 días antes o después
EVERY = 4           # en la presentación, una de cada 4 fotos es un recuerdo


def _same_day_distance(d, today):
    """Días entre la fecha (sin el año) y hoy, dando la vuelta al año."""
    try:
        this_year = date(today.year, d.month, d.day)
    except ValueError:          # 29 de febrero en un año que no es bisiesto
        this_year = date(today.year, 2, 28)
    diff = abs((this_year - today).days)
    return min(diff, 365 - diff)


def on_this_day(items, indices, today):
    """Índices (de `indices`) tomados en estos días en años anteriores, del más
    antiguo al más reciente."""
    found = [i for i in indices
             if items[i].date.year < today.year and _same_day_distance(items[i].date.date(), today) <= WINDOW_DAYS]
    return sorted(found, key=lambda i: items[i].date)


def years_ago(d, today):
    from .i18n import years_ago as text
    return text(today.year - d.year)
