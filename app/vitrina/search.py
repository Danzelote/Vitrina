"""Búsqueda: qué fotos coinciden con lo que se escribe.

Cada palabra filtra (todas deben cumplirse), en español o inglés:
  videos / fotos          → solo videos o solo fotos
  2019                    → año
  diciembre / december    → mes (también abreviado: dic, dec)
  cualquier otra palabra  → colección o lugar (Cancún, Navidad…)
Sin acentos ni mayúsculas: "cancun" encuentra "Cancún".
"""

import unicodedata

VIDEO_WORDS = {"video", "videos", "vid", "vids", "pelicula", "peliculas", "movie", "movies"}
PHOTO_WORDS = {"foto", "fotos", "photo", "photos", "imagen", "imagenes", "image", "images", "pic", "pics"}
STOP = {"de", "del", "la", "el", "los", "las", "en", "y", "of", "the", "in", "and"}
MONTHS = [
    ("enero", "january", "ene", "jan"), ("febrero", "february", "feb"), ("marzo", "march", "mar"),
    ("abril", "april", "abr", "apr"), ("mayo", "may"), ("junio", "june", "jun"), ("julio", "july", "jul"),
    ("agosto", "august", "ago", "aug"), ("septiembre", "setiembre", "september", "sep", "sept"),
    ("octubre", "october", "oct"), ("noviembre", "november", "nov"), ("diciembre", "december", "dic", "dec"),
]
MONTH_OF = {w: k + 1 for k, words in enumerate(MONTHS) for w in words}


def norm(text):
    text = unicodedata.normalize("NFKD", text or "")
    return "".join(c for c in text if not unicodedata.combining(c)).lower().strip()


def parse(query):
    """[(tipo, valor)] de lo escrito: ("kind", "video"|"photo"), ("year", 2019),
    ("month", 12) o ("text", "cancun")."""
    terms = []
    for word in norm(query).replace(",", " ").split():
        if word in STOP:
            continue
        if word in VIDEO_WORDS:
            terms.append(("kind", "video"))
        elif word in PHOTO_WORDS:
            terms.append(("kind", "photo"))
        elif word.isdigit() and len(word) == 4 and 1900 <= int(word) <= 2100:
            terms.append(("year", int(word)))
        elif word in MONTH_OF:
            terms.append(("month", MONTH_OF[word]))
        else:
            terms.append(("text", word))
    return terms


def matcher(query, place_of):
    """Función item -> bool para lo escrito (None si no hay nada que buscar).
    `place_of(item)` da el nombre del lugar de la foto (o None)."""
    terms = parse(query)
    if not terms:
        return None

    def ok(it):
        for kind, value in terms:
            if kind == "kind":
                if it.is_video != (value == "video"):
                    return False
            elif kind == "year":
                if not it.date or it.date.year != value:
                    return False
            elif kind == "month":
                if not it.date or it.date.month != value:
                    return False
            else:
                hay = norm(it.collection or "") + " " + norm(place_of(it) or "")
                if value not in hay:
                    return False
        return True
    return ok
