import os
from datetime import datetime

from PIL import Image

from vitrina import library, livelib


def make(path, date="2024:05:01 10:00:00"):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    img = Image.new("RGB", (40, 30), (200, 100, 50))
    exif = img.getexif()
    exif[306] = date
    img.save(path, "JPEG", exif=exif)


def test_add_move_rename_remove(tmp_path):
    folder = str(tmp_path)
    make(os.path.join(folder, "a.jpg"))
    lib = livelib.LiveLibrary(folder, library.scan(folder), None)
    assert [it.collection for it in lib.items] == [""]
    p = os.path.join(folder, "Viaje", "b.jpg")
    make(p, "2025:01:02 10:00:00")
    new = lib.add_paths([p, p])
    assert len(new) == 1 and lib.items[0].collection == "Viaje" and lib.items[0].date == datetime(2025, 1, 2, 10)
    key = new[0].key
    dest = os.path.join(folder, "Casa", "b.jpg")
    os.makedirs(os.path.dirname(dest))
    os.replace(p, dest)
    lib.moved([(p, dest)])
    assert lib.items[0].collection == "Casa" and lib.items[0].key == key
    os.rename(os.path.join(folder, "Casa"), os.path.join(folder, "Hogar"))
    lib.renamed_collection("Casa", "Hogar")
    assert lib.items[0].path == os.path.join(folder, "Hogar", "b.jpg")
    assert library.scan_file(folder, lib.items[0].path).key == key   # la clave no cambia al moverse
    trash = livelib.to_trash(folder, lib.items[0].path)
    lib.remove_paths([os.path.join(folder, "Hogar", "b.jpg")])
    assert len(lib.items) == 1 and ".papelera" in trash
    assert [it.path for it in library.scan(folder)] == [os.path.join(folder, "a.jpg")]   # la papelera no cuenta
    assert ("Hogar", 0) in lib.collections()


def test_safe_name():
    assert livelib.safe_name("../../etc/passwd") == "passwd"
    assert livelib.safe_name(".oculto") == "oculto"
    assert livelib.safe_name('a/b:c*?"<>|') == "b:c" or livelib.safe_name('a/b:c*?"<>|') == "bc"
