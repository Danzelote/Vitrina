"""Detecta fotos repetidas al subirlas (por ejemplo, cuando dos personas con
la misma biblioteca compartida de iCloud suben la misma foto).

Una foto nueva cuenta como repetida si ya hay una:
- idéntica byte por byte (misma huella SHA-1), o
- tomada en el mismo instante (fecha y hora de la cámara, con fracciones de
  segundo si las trae) y que se ve igual (huella visual dHash casi idéntica).
  Esto atrapa la misma foto convertida dos veces (HEIC → JPEG en cada iPhone),
  sin confundir fotos distintas de una ráfaga.
- En videos: misma fecha y misma duración.

Solo se compara contra las fotos con la misma fecha o el mismo tamaño de
archivo, así que es rápido aunque la biblioteca sea grande.
"""

import hashlib
import json
import os
import threading

from PIL import ImageOps

from . import library

DHASH_MAX = 6          # bits distintos (de 64) que aún cuentan como "la misma foto"


def sha1_of(path):
    h = hashlib.sha1()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def visual_print(path):
    """(huella visual dHash de 64 bits, 'fecha.fracción' de la cámara o None)."""
    with library.open_image(path) as img:
        exif = img.getexif()
        sub = exif.get_ifd(0x8769)
        when = sub.get(36867) or exif.get(306)
        frac = sub.get(37521)
        cap = f"{str(when).strip()}.{str(frac).strip()}" if when and frac else (str(when).strip() if when else None)
        img.draft("L", (256, 256))
        small = ImageOps.exif_transpose(img).convert("L").resize((9, 8))
    px = small.tobytes()   # 72 valores de gris
    bits = 0
    for row in range(8):
        for col in range(8):
            bits = (bits << 1) | (px[row * 9 + col] > px[row * 9 + col + 1])
    return bits, cap


class Dupes:
    def __init__(self, lib):
        self.lib = lib
        self.lock = threading.Lock()
        self.path = os.path.join(library.cache_dir(), "huellas.json")
        try:
            with open(self.path) as f:
                self.cache = json.load(f)
        except Exception:
            self.cache = {}
        # Lo recién agregado que la biblioteca todavía no termina de registrar
        # (si llega la misma foto justo en ese momento, también se reconoce).
        self.recent = []        # [(ruta, item, huella)]

    def _record(self, path, is_video, duration):
        rec = {"sha1": sha1_of(path), "v": is_video, "dur": round(duration, 1)}
        if not is_video:
            try:
                rec["dh"], rec["cap"] = visual_print(path)
            except Exception:
                pass
        return rec

    def record(self, it):
        rec = self.cache.get(it.key)
        if rec is None:
            rec = self._record(it.path, it.is_video, it.duration)
            self.cache[it.key] = rec
            self._save()
        return rec

    def _save(self):
        try:
            tmp = self.path + ".tmp"
            with open(tmp, "w") as f:
                json.dump(self.cache, f)
            os.replace(tmp, self.path)
        except OSError:
            pass

    @staticmethod
    def same(a, b, date_equal):
        if a["sha1"] == b["sha1"]:
            return True
        if a["v"] or b["v"]:
            return a["v"] and b["v"] and date_equal and abs(a["dur"] - b["dur"]) <= 0.3
        if a.get("dh") is None or b.get("dh") is None or not a.get("cap") or a.get("cap") != b.get("cap"):
            return False
        return bin(a["dh"] ^ b["dh"]).count("1") <= DHASH_MAX

    def find(self, path):
        """La foto ya existente que es igual a `path` (recién subida), o None."""
        new = library.scan_file(self.lib.folder, path)
        if new is None:
            return None
        size = os.path.getsize(path)
        rec = None
        for it in self.lib.snapshot:
            date_equal = it.date == new.date
            try:
                if not date_equal and os.path.getsize(it.path) != size:
                    continue
            except OSError:
                continue
            try:
                old = self.record(it)
            except OSError:
                continue
            if rec is None:
                rec = self._record(path, new.is_video, new.duration)
            if self.same(rec, old, date_equal):
                return it
        known = {it.path for it in self.lib.snapshot}
        self.recent = [r for r in self.recent if r[0] not in known and os.path.exists(r[0])]
        for _p, it, old in self.recent:
            date_equal = it.date == new.date
            if rec is None:
                rec = self._record(path, new.is_video, new.duration)
            if self.same(rec, old, date_equal):
                return it
        return None

    def note(self, path):
        """Acaba de agregarse `path` (ya en su lugar): se recuerda hasta que la biblioteca lo tenga."""
        try:
            it = library.scan_file(self.lib.folder, path)
            if it is not None:
                self.recent.append((path, it, self._record(path, it.is_video, it.duration)))
                del self.recent[:-200]
        except Exception:      # noqa: BLE001
            pass
