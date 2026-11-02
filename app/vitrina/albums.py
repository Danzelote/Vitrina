"""Colecciones y papelera.

Una foto puede estar en varias colecciones: la lista vive en
`<biblioteca>/.vitrina/colecciones.json`, no en carpetas. Los archivos se
quedan donde están.

- Las carpetas de antes se convierten solas: la primera vez que se ve una foto,
  si está dentro de una subcarpeta, queda en la colección con ese nombre.
- "members" guarda cada foto ya vista (con su lista, aunque esté vacía), así
  quitarla de una colección no se deshace al reiniciar.
- La papelera ("Eliminadas recientemente") guarda de dónde venía cada archivo
  y en qué colecciones estaba, para poder recuperarlo. A los 30 días se borra.
"""

import json
import os
import shutil
import threading
import time

TRASH_DAYS = 30
TRASH_DIR = ".papelera"


def _now():
    return time.time()


class Albums:
    def __init__(self, folder):
        self.folder = os.path.abspath(folder)
        self.dir = os.path.join(self.folder, ".vitrina")
        self.path = os.path.join(self.dir, "colecciones.json")
        self.lock = threading.RLock()
        self.names = {}          # nombre -> {"created": t}
        self.members = {}        # clave de la foto -> [nombres]
        self.hidden_auto = []    # automáticas que la persona ocultó
        self.trash = {}          # ruta relativa en la papelera -> registro
        self._load()

    # -- archivo -------------------------------------------------------------------

    def _load(self):
        try:
            with open(self.path) as f:
                data = json.load(f)
        except (OSError, ValueError):
            data = {}
        self.names = dict(data.get("names") or {})
        self.members = {k: list(v) for k, v in (data.get("members") or {}).items()}
        self.hidden_auto = list(data.get("hidden_auto") or [])
        self.trash = dict(data.get("trash") or {})
        # Lo que se borró con versiones anteriores (sin registro): se puede
        # recuperar a la carpeta principal.
        tdir = os.path.join(self.folder, TRASH_DIR)
        known = set(self.trash)
        for root, _dirs, files in os.walk(tdir):
            for name in files:
                p = os.path.join(root, name)
                rel = os.path.relpath(p, self.folder)
                if rel not in known:
                    try:
                        t = os.path.getmtime(root)
                    except OSError:
                        t = _now()
                    self.trash[rel] = {"orig": name, "key": None, "collections": [], "deleted": t}
        # Las carpetas de antes (aunque estén vacías) son colecciones.
        try:
            for d in os.listdir(self.folder):
                if not d.startswith(".") and os.path.isdir(os.path.join(self.folder, d)):
                    self.names.setdefault(d, {"created": _now()})
        except OSError:
            pass

    def save(self):
        with self.lock:
            data = {"version": 1, "names": self.names, "members": self.members,
                    "hidden_auto": self.hidden_auto, "trash": self.trash}
            os.makedirs(self.dir, exist_ok=True)
            tmp = self.path + ".tmp"
            with open(tmp, "w") as f:
                json.dump(data, f, ensure_ascii=False)
            os.replace(tmp, self.path)

    # -- fotos ---------------------------------------------------------------------

    def attach(self, items, folder_of):
        """Pone en cada Item su lista de colecciones. `folder_of(item)` es la
        subcarpeta donde está el archivo ("" si en la raíz): cuenta solo la
        primera vez que se ve la foto."""
        changed = False
        with self.lock:
            for it in items:
                cols = self.members.get(it.key)
                if cols is None:
                    first = folder_of(it)
                    cols = [first] if first else []
                    self.members[it.key] = cols
                    if first:
                        self.names.setdefault(first, {"created": _now()})
                    changed = True
                it.collections = tuple(c for c in cols if c in self.names)
        if changed:
            self.save()

    def set_for(self, key, names):
        with self.lock:
            names = [n for n in dict.fromkeys(names) if n]
            for n in names:
                self.names.setdefault(n, {"created": _now()})
            self.members[key] = names

    def add(self, items, name):
        with self.lock:
            self.names.setdefault(name, {"created": _now()})
            for it in items:
                cols = self.members.setdefault(it.key, [])
                if name not in cols:
                    cols.append(name)
                it.collections = tuple(cols)
        self.save()

    def remove(self, items, name):
        with self.lock:
            for it in items:
                cols = [c for c in self.members.get(it.key, []) if c != name]
                self.members[it.key] = cols
                it.collections = tuple(cols)
        self.save()

    # -- colecciones ---------------------------------------------------------------

    def create(self, name):
        with self.lock:
            self.names.setdefault(name, {"created": _now()})
        self.save()

    def rename(self, old, new, items):
        with self.lock:
            if old not in self.names or not new or new == old:
                return False
            self.names[new] = self.names.pop(old)
            for k, cols in self.members.items():
                if old in cols:
                    self.members[k] = list(dict.fromkeys(new if c == old else c for c in cols))
            for it in items:
                it.collections = tuple(self.members.get(it.key, ()))
        self.save()
        return True

    def delete(self, name, items):
        """Borra la colección; las fotos se quedan en la biblioteca."""
        with self.lock:
            self.names.pop(name, None)
            for k, cols in self.members.items():
                if name in cols:
                    self.members[k] = [c for c in cols if c != name]
            for it in items:
                it.collections = tuple(self.members.get(it.key, ()))
        self.save()

    def counts(self, items):
        """[(nombre, cuántas)] de todas las colecciones, también las vacías."""
        n = {name: 0 for name in self.names}
        for it in items:
            for c in it.collections:
                if c in n:
                    n[c] += 1
        return sorted(n.items(), key=lambda kv: kv[0].lower())

    def hide_auto(self, key):
        with self.lock:
            if key not in self.hidden_auto:
                self.hidden_auto.append(key)
        self.save()

    # -- papelera ------------------------------------------------------------------

    def to_trash(self, it):
        """Mueve el archivo a la papelera y anota cómo recuperarlo. Devuelve la ruta nueva."""
        day = time.strftime("%Y-%m-%d")
        tdir = os.path.join(self.folder, TRASH_DIR, day)
        os.makedirs(tdir, exist_ok=True)
        dest = unique_path(os.path.join(tdir, os.path.basename(it.path)))
        shutil.move(it.path, dest)
        with self.lock:
            self.trash[os.path.relpath(dest, self.folder)] = {
                "orig": os.path.relpath(it.path, self.folder), "key": it.key,
                "collections": list(self.members.get(it.key, [])), "deleted": _now()}
        return dest

    def trash_list(self):
        """[(ruta absoluta en la papelera, registro)] de lo más reciente a lo más viejo."""
        out = []
        with self.lock:
            for rel, rec in list(self.trash.items()):
                p = os.path.join(self.folder, rel)
                if os.path.exists(p):
                    out.append((p, rec))
                else:
                    self.trash.pop(rel, None)
        return sorted(out, key=lambda x: -x[1].get("deleted", 0))

    def restore(self, trash_path):
        """Regresa el archivo a su lugar. Devuelve (ruta, colecciones) o None."""
        rel = os.path.relpath(trash_path, self.folder)
        with self.lock:
            rec = self.trash.get(rel)
            if not rec or not os.path.exists(trash_path):
                return None
            dest = unique_path(os.path.join(self.folder, rec["orig"]))
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            shutil.move(trash_path, dest)
            self.trash.pop(rel, None)
            cols = [c for c in rec.get("collections", []) if c in self.names]
        return dest, cols

    def purge(self, trash_path=None, older_than=None):
        """Borra de verdad: una ruta, o todo lo que pasó de `older_than` días."""
        gone = []
        with self.lock:
            for rel, rec in list(self.trash.items()):
                p = os.path.join(self.folder, rel)
                old = older_than is not None and _now() - rec.get("deleted", 0) > older_than * 86400
                if (trash_path and os.path.abspath(p) == os.path.abspath(trash_path)) or old:
                    try:
                        os.remove(p)
                    except OSError:
                        pass
                    self.trash.pop(rel, None)
                    self.members.pop(rec.get("key"), None)
                    gone.append(p)
        if gone:
            self.save()
        return gone

    def days_left(self, rec):
        return max(0, TRASH_DAYS - int((_now() - rec.get("deleted", 0)) // 86400))


def unique_path(path):
    base, ext = os.path.splitext(path)
    n = 1
    while os.path.exists(path):
        path = f"{base}_{n}{ext}"
        n += 1
    return path
