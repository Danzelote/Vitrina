"""La biblioteca "en vivo": la lista de fotos que cambia mientras la app corre
(fotos subidas desde el celular, movidas de colección o borradas).

Todo cambio se hace desde el hilo de la interfaz. El servidor web solo lee
`snapshot`, una lista inmutable que se reemplaza completa en cada cambio.
"""

import os

from . import library
from .albums import Albums


class LiveLibrary:
    def __init__(self, folder, items, processor):
        self.folder = os.path.abspath(folder)
        self.items = list(items)
        self.processor = processor
        self.albums = Albums(self.folder)
        self.albums.attach(self.items, lambda it: it.folder)
        self.version = 0
        self.snapshot = ()
        self.trash_version = 0
        self._snap()

    # -- lectura (cualquier hilo) -------------------------------------------------

    def _snap(self):
        self.version += 1
        self.snapshot = tuple(self.items)

    def collections(self):
        """[(nombre, cuántas)] de las colecciones de la persona (también vacías)."""
        return self.albums.counts(self.snapshot)

    # -- cambios (hilo de la interfaz) --------------------------------------------

    def add_paths(self, paths, collections=None):
        """Agrega archivos ya copiados a la carpeta. Devuelve los Items nuevos.
        `collections`: colecciones para las fotos nuevas (si no, según su carpeta)."""
        known = {it.path for it in self.items}
        new = []
        for p in paths:
            if p in known or not os.path.exists(p):
                continue
            known.add(p)
            it = library.scan_file(self.folder, p)
            if it:
                if collections is not None:
                    self.albums.set_for(it.key, collections)
                new.append(it)
        if new:
            self.albums.attach(new, lambda it: it.folder)
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

    def add_to(self, keys, name):
        name = safe_name(name)
        if not name:
            return
        self.albums.add([it for it in self.items if it.key in set(keys)], name)
        self._snap()

    def remove_from(self, keys, name):
        self.albums.remove([it for it in self.items if it.key in set(keys)], name)
        self._snap()

    def set_collections(self, key, names):
        it = next((x for x in self.items if x.key == key), None)
        if it:
            self.albums.set_for(key, [safe_name(n) for n in names])
            self.albums.attach([it], lambda _it: "")
            self.albums.save()
            self._snap()

    def create_collection(self, name):
        name = safe_name(name)
        if name:
            self.albums.create(name)
            self._snap()
        return name

    def rename_collection(self, old, new):
        new = safe_name(new)
        ok = self.albums.rename(old, new, self.items)
        if ok:
            self._snap()
        return ok

    def delete_collection(self, name):
        self.albums.delete(name, self.items)
        self._snap()

    def hide_auto(self, key):
        self.albums.hide_auto(key)
        self._snap()

    def keep_auto(self, key, name, keys):
        """Convierte una automática en colección de la persona."""
        name = safe_name(name)
        if name:
            self.albums.add([it for it in self.items if it.key in set(keys)], name)
            self.albums.hide_auto(key)
            self._snap()

    # -- papelera ------------------------------------------------------------------

    def trash_keys(self, keys):
        """Manda a "Eliminadas recientemente". Devuelve cuántas."""
        keys = set(keys)
        moved = []
        for it in [x for x in self.items if x.key in keys]:
            try:
                self.albums.to_trash(it)
                moved.append(it.path)
            except OSError as exc:
                print("No se pudo mover a la papelera:", exc, flush=True)
        if moved:
            self.albums.save()
            self.remove_paths(moved)
            self.trash_version += 1
        return len(moved)

    def trash_items(self):
        """[(Item, registro)] de lo que está en la papelera (con miniaturas)."""
        out = []
        for path, rec in self.albums.trash_list():
            it = library.scan_file(self.folder, path)
            if it:
                if self.processor:
                    self.processor.prepare_only(it)
                out.append((it, rec))
        return out

    def restore(self, trash_paths):
        back = []
        for p in trash_paths:
            r = self.albums.restore(p)
            if r:
                dest, cols = r
                self.add_paths([dest], cols)
                back.append(dest)
        if back:
            self.albums.save()
            self.trash_version += 1
        return len(back)

    def purge(self, trash_paths=None, older_than=None):
        gone = []
        if trash_paths:
            for p in trash_paths:
                gone += self.albums.purge(trash_path=p)
        if older_than is not None:
            gone += self.albums.purge(older_than=older_than)
        if gone:
            self.trash_version += 1
        return len(gone)


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
