"""La biblioteca "en vivo": la lista de fotos que cambia mientras la app corre
(fotos subidas desde el celular, movidas de colección o borradas).

Todo cambio se hace desde el hilo de la interfaz. El servidor web solo lee
`snapshot`, una lista inmutable que se reemplaza completa en cada cambio.
"""

import os
import shutil
import time

from . import library


class LiveLibrary:
    def __init__(self, folder, items, processor):
        self.folder = os.path.abspath(folder)
        self.items = list(items)
        self.processor = processor
        self.version = 0
        self.snapshot = ()
        self._snap()

    # -- lectura (cualquier hilo) -------------------------------------------------

    def _snap(self):
        self.version += 1
        self.snapshot = tuple(self.items)

    def collections(self):
        """[(nombre, cuántas)] incluyendo carpetas vacías; "" = sin colección."""
        counts = {}
        for it in self.snapshot:
            counts[it.collection] = counts.get(it.collection, 0) + 1
        names = set(library.collections_on_disk(self.folder)) | {c for c in counts if c}
        out = [("", counts.get("", 0))] + [(n, counts.get(n, 0)) for n in sorted(names, key=str.lower)]
        return out

    # -- cambios (hilo de la interfaz) --------------------------------------------

    def add_paths(self, paths):
        """Agrega archivos ya copiados a la carpeta. Devuelve los Items nuevos."""
        known = {it.path for it in self.items}
        new = []
        for p in paths:
            if p in known or not os.path.exists(p):
                continue
            known.add(p)
            it = library.scan_file(self.folder, p)
            if it:
                new.append(it)
        if new:
            if self.processor:
                self.processor.add(new)
            self.items.extend(new)
            self.items.sort(key=lambda it: it.date, reverse=True)
            self._snap()
        return new

    def remove_paths(self, paths):
        gone = set(paths)
        before = len(self.items)
        self.items = [it for it in self.items if it.path not in gone]
        if len(self.items) != before:
            self._snap()

    def moved(self, pairs):
        """pairs: [(ruta vieja, ruta nueva)] de archivos ya movidos."""
        where = dict(pairs)
        for it in self.items:
            if it.path in where:
                it.path = where[it.path]
                it.collection = library.collection_of(self.folder, it.path)
        self._snap()

    def renamed_collection(self, old, new):
        old_dir = os.path.join(self.folder, old)
        new_dir = os.path.join(self.folder, new)
        for it in self.items:
            if it.collection == old:
                it.path = os.path.join(new_dir, os.path.relpath(it.path, old_dir))
                it.collection = new
        self._snap()


# -- operaciones de archivos (las usa el servidor web) ------------------------------

def safe_name(name):
    """Nombre de archivo o colección sin separadores ni caracteres raros."""
    name = os.path.basename(name.replace("\\", "/")).strip()
    name = "".join(ch for ch in name if ch.isprintable() and ch not in '/\\:*?"<>|')
    return name.lstrip(".")[:120]


def unique_path(path):
    base, ext = os.path.splitext(path)
    n = 1
    while os.path.exists(path):
        path = f"{base}_{n}{ext}"
        n += 1
    return path


def collection_dir(folder, collection):
    d = os.path.join(folder, safe_name(collection)) if collection else folder
    os.makedirs(d, exist_ok=True)
    return d


def to_trash(folder, path):
    """Mueve a la papelera de la Vitrina (una carpeta oculta dentro de la biblioteca)."""
    trash = os.path.join(folder, ".papelera", time.strftime("%Y-%m-%d"))
    os.makedirs(trash, exist_ok=True)
    dest = unique_path(os.path.join(trash, os.path.basename(path)))
    shutil.move(path, dest)
    return dest
