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


def test_collections_and_trash(tmp_path):
    folder = str(tmp_path)
    make(os.path.join(folder, "a.jpg"))
    make(os.path.join(folder, "Viaje", "old.jpg"), "2023:03:03 10:00:00")     # carpeta de antes
    lib = livelib.LiveLibrary(folder, library.scan(folder), None)
    by = {os.path.basename(it.path): it for it in lib.items}
    assert by["a.jpg"].collections == () and by["old.jpg"].collections == ("Viaje",)
    # Fotos nuevas en varias colecciones a la vez.
    p = os.path.join(folder, "b.jpg")
    make(p, "2025:01:02 10:00:00")
    new = lib.add_paths([p, p], ["Casa", "Daniel"])
    assert len(new) == 1 and lib.items[0].collections == ("Casa", "Daniel")
    assert lib.items[0].date == datetime(2025, 1, 2, 10)
    key = new[0].key
    lib.add_to([by["a.jpg"].key], "Casa")
    assert dict(lib.collections())["Casa"] == 2
    lib.remove_from([key], "Daniel")
    assert lib.items[0].collections == ("Casa",)
    assert lib.rename_collection("Casa", "Hogar")
    assert lib.items[0].collections == ("Hogar",)
    # Quitar de una colección se recuerda (la carpeta ya no manda).
    lib.remove_from([by["old.jpg"].key], "Viaje")
    lib2 = livelib.LiveLibrary(folder, library.scan(folder), None)
    again = {os.path.basename(it.path): it for it in lib2.items}
    assert again["old.jpg"].collections == () and again["b.jpg"].collections == ("Hogar",)
    assert ("Viaje", 0) in lib2.collections()               # la colección vacía sigue
    lib2.delete_collection("Viaje")
    assert "Viaje" not in dict(lib2.collections())
    # Papelera: se va, se recupera con sus colecciones, se borra a los 30 días.
    assert lib2.trash_keys([key]) == 1
    assert all(it.key != key for it in lib2.items)
    assert [it.path for it in library.scan(folder) if it.key == key] == []     # la papelera no cuenta
    (t_it, rec), = lib2.trash_items()
    assert rec["collections"] == ["Hogar"]
    assert lib2.restore([t_it.path]) == 1
    back = next(it for it in lib2.items if it.key == key)
    assert back.collections == ("Hogar",) and os.path.exists(back.path)
    lib2.trash_keys([key])
    lib2.albums.trash[next(iter(lib2.albums.trash))]["deleted"] -= 31 * 86400
    assert lib2.purge(older_than=30) == 1 and lib2.trash_items() == []


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
