import io
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from vitrina import qrscan  # noqa: E402


def test_parse_wifi_basic():
    assert qrscan.parse_wifi("WIFI:T:WPA;S:Casa;P:secreto;;") == {"ssid": "Casa", "password": "secreto", "hidden": False}


def test_parse_wifi_escapes_and_hidden():
    r = qrscan.parse_wifi(r"WIFI:S:Mi\;Red\:5G;T:WPA;P:a\\b\;c;H:true;;")
    assert r == {"ssid": "Mi;Red:5G", "password": "a\\b;c", "hidden": True}


def test_parse_wifi_open_and_invalid():
    assert qrscan.parse_wifi("WIFI:S:Libre;T:nopass;;")["password"] == ""
    assert qrscan.parse_wifi("https://example.com") is None
    assert qrscan.parse_wifi("WIFI:T:WPA;P:x;;") is None


def test_decode_generated_code():
    if not qrscan.AVAILABLE:
        return
    import segno
    from PIL import Image
    from pyzbar import pyzbar
    buf = io.BytesIO()
    segno.make("WIFI:T:WPA;S:Casa;P:secreto;;", error="m").save(buf, kind="png", scale=6, border=4)
    img = Image.open(io.BytesIO(buf.getvalue())).convert("L")
    text = pyzbar.decode(img)[0].data.decode()
    assert qrscan.parse_wifi(text)["ssid"] == "Casa"
