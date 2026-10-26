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


def test_raw_preview(tmp_path):
    from io import BytesIO
    from vitrina import raw
    big, small, tif = BytesIO(), BytesIO(), BytesIO()
    Image.new("RGB", (300, 200), (10, 120, 200)).save(big, "JPEG")
    Image.new("RGB", (40, 30), (200, 0, 0)).save(small, "JPEG")
    im = Image.new("RGB", (8, 8))
    exif = im.getexif()
    exif[0x0112] = 6                       # girada: hay que enderezarla
    exif[306] = "2023:07:15 18:30:00"
    im.save(tif, "TIFF", exif=exif)
    path = tmp_path / "IMG_0001.CR2"
    path.write_bytes(tif.getvalue() + small.getvalue() + b"\x00" * 50 + big.getvalue() + b"\x00" * 10)
    img = raw.open_preview(str(path))
    assert img.size == (200, 300) and img.info["raw_date"] == "2023:07:15 18:30:00"
    it = library.scan_file(str(tmp_path), str(path))
    assert it is not None and it.date == datetime(2023, 7, 15, 18, 30)


def test_duplicates(tmp_path):
    from io import BytesIO
    from vitrina import dupes
    folder = str(tmp_path / "biblio")
    a = os.path.join(folder, "IMG_1.jpg")
    make(a, "2024:05:01 10:00:00")
    lib = livelib.LiveLibrary(folder, library.scan(folder), None)
    d = dupes.Dupes(lib)
    # Idéntica (otro nombre)
    same = str(tmp_path / "copia.jpg")
    with open(a, "rb") as f, open(same, "wb") as g:
        g.write(f.read())
    assert d.find(same) is not None
    # La misma foto guardada de nuevo (otros bytes, misma fecha de cámara)
    again = str(tmp_path / "convertida.jpg")
    img = Image.open(a)
    exif = img.getexif()
    img.save(again, "JPEG", quality=60, exif=exif)
    assert d.find(again) is not None
    # Otra foto tomada en otro momento: no es repetida
    other = str(tmp_path / "otra.jpg")
    make(other, "2024:05:01 10:00:01")
    assert d.find(other) is None


def test_duplicate_just_added(tmp_path):
    """La misma foto que llega justo cuando la primera aún no entra a la biblioteca."""
    from vitrina import dupes
    folder = str(tmp_path / "biblio")
    os.makedirs(folder)
    lib = livelib.LiveLibrary(folder, library.scan(folder), None)
    d = dupes.Dupes(lib)
    first = os.path.join(folder, "IMG_9.jpg")
    make(first, "2024:06:01 12:00:00")
    d.note(first)                       # ya se movió a la biblioteca, pero la app no la ha registrado
    twin = str(tmp_path / "IMG_9 copia.jpg")
    with open(first, "rb") as f, open(twin, "wb") as g:
        g.write(f.read())
    assert d.find(twin) is not None
