"""Nombre del lugar de una foto a partir de su ubicación, sin internet.

Usa una lista de ~145 mil ciudades y pueblos de más de 1000 habitantes
(GeoNames, licencia CC BY 4.0, tomada del paquete reverse_geocoder) y busca
la más cercana. La lista se carga en segundo plano la primera vez que se
necesita; mientras tanto place() devuelve None.
"""

import gzip
import json
import math
import os
import threading

from . import i18n

DATA = os.path.join(os.path.dirname(__file__), "data")
# Los nombres de la lista vienen sin acentos; los más comunes se corrigen aquí.
ES_NAMES = {
    "Mexico City": "Ciudad de México", "Cancun": "Cancún", "Merida": "Mérida", "Queretaro": "Querétaro",
    "Santiago de Queretaro": "Santiago de Querétaro", "Leon de los Aldama": "León", "Mazatlan": "Mazatlán",
    "San Luis Potosi": "San Luis Potosí", "Culiacan": "Culiacán", "Tulum": "Tulum", "Oaxaca de Juarez": "Oaxaca de Juárez",
    "Ciudad Juarez": "Ciudad Juárez", "Torreon": "Torreón", "Tuxtla Gutierrez": "Tuxtla Gutiérrez",
    "San Pedro Garza Garcia": "San Pedro Garza García", "Bogota": "Bogotá", "San Jose": "San José",
    "Medellin": "Medellín", "Panama": "Panamá", "Asuncion": "Asunción", "Brasilia": "Brasilia",
    "Sao Paulo": "São Paulo", "New York City": "Nueva York", "London": "Londres", "Rome": "Roma",
    "Florence": "Florencia", "Venice": "Venecia", "Munich": "Múnich", "Cadiz": "Cádiz", "Malaga": "Málaga",
    "Cordoba": "Córdoba", "Leon": "León", "Tokyo": "Tokio", "Kyoto": "Kioto", "Geneva": "Ginebra",
    "Copenhagen": "Copenhague", "Athens": "Atenas", "Lisbon": "Lisboa", "Moscow": "Moscú",
}
MAX_KM = 60          # más lejos que esto, solo el país (por ejemplo, en el mar o en el campo)


class Places:
    def __init__(self):
        self.ready = False
        self._loading = False
        self._lock = threading.Lock()
        self.cells = {}
        self.countries = {}
        self.memo = {}

    def _load(self):
        cells = {}
        with gzip.open(os.path.join(DATA, "cities.tsv.gz"), "rt", encoding="utf-8") as f:
            for line in f:
                lat, lon, name, admin1, cc = line.rstrip("\n").split("\t")
                lat, lon = float(lat), float(lon)
                cells.setdefault((int(math.floor(lat)), int(math.floor(lon))), []).append((lat, lon, name, admin1, cc))
        with open(os.path.join(DATA, "countries.json"), encoding="utf-8") as f:
            self.countries = json.load(f)
        self.cells = cells
        self.ready = True

    def _ensure(self):
        with self._lock:
            if self.ready or self._loading:
                return
            self._loading = True
        threading.Thread(target=self._load, daemon=True).start()

    def nearest(self, lat, lon):
        """(nombre, región, país, km) del lugar más cercano, o None."""
        best, best_d = None, None
        la0, lo0 = int(math.floor(lat)), int(math.floor(lon))
        k = math.cos(math.radians(lat))
        for r in (1, 2):
            for a in range(la0 - r, la0 + r + 1):
                for b in range(lo0 - r, lo0 + r + 1):
                    for c in self.cells.get((a, (b + 180) % 360 - 180), ()):
                        dy = c[0] - lat
                        dx = ((c[1] - lon + 180) % 360 - 180) * k
                        d = dx * dx + dy * dy
                        if best_d is None or d < best_d:
                            best, best_d = c, d
            if best:
                break
        if not best:
            return None
        return best[2], best[3], best[4], math.sqrt(best_d) * 111.2

    def place(self, lat, lon):
        """"Ciudad, País" en el idioma actual, o None si no hay ubicación (o aún no carga)."""
        if lat is None or lon is None:
            return None
        if not self.ready:
            self._ensure()
            return None
        lang = i18n.lang()
        key = (round(lat, 3), round(lon, 3), lang)
        if key in self.memo:
            return self.memo[key]
        found = self.nearest(lat, lon)
        text = None
        if found:
            name, _admin1, cc, km = found
            names = self.countries.get(cc)
            country = (names[1] if lang == "en" else names[0]) if names else cc
            if lang == "es":
                name = ES_NAMES.get(name, name)
            text = f"{name}, {country}" if km <= MAX_KM else country
        self.memo[key] = text
        return text


PLACES = Places()


def place_of(item):
    return PLACES.place(item.lat, item.lon)
