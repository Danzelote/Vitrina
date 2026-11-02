import os
import sys
from datetime import datetime, timedelta
from types import SimpleNamespace as NS

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from vitrina import autos  # noqa: E402

HOME = (25.67, -100.31)        # Monterrey
TRIP = (20.97, -89.62)         # Mérida


def item(k, when, where=None, lens="", w=4000, h=3000, video=False, dated=True):
    lat, lon = where if where else (None, None)
    return NS(key=k, date=when, dated=dated, lat=lat, lon=lon, lens=lens, is_video=video,
              ready=True, width=w, height=h, aspect=w / h)


def test_build():
    t = datetime(2024, 9, 14, 13, 0)
    items = [item(f"h{n}", t - timedelta(days=30 + n), HOME) for n in range(12)]                 # en casa
    items += [item(f"t{n}", datetime(2024, 12, 20 + n // 2, 10), TRIP) for n in range(6)]     # viaje
    items += [item("tnogps", datetime(2024, 12, 21, 18))]                                       # sin ubicación, en el viaje
    items += [item(f"e{n}", t + timedelta(minutes=40 * n), HOME) for n in range(3)]            # fiesta
    items += [item("s", t - timedelta(days=200), HOME, lens="iPhone 13 front camera 2.71mm f/2.2")]
    items += [item("p", t - timedelta(days=300), HOME, w=8000, h=2000)]
    items += [item(f"u{n}", datetime(2025, 1, 1, 12), dated=False) for n in range(5)]          # sin fecha real
    place = lambda it: "Mérida, México" if it.lat and it.lat < 22 else "Monterrey, México"  # noqa: E731
    out = {a.kind: a for a in autos.build(items, place)}
    assert set(out["trip"].keys) == {f"t{n}" for n in range(6)} | {"tnogps"}
    assert out["trip"].title.startswith("Mérida · diciembre 2024")
    assert set(out["event"].keys) == {"e0", "e1", "e2"} and "Monterrey" in out["event"].title
    assert out["selfies"].keys == ["s"] and out["panos"].keys == ["p"]
    assert not any(k.startswith("u") for a in out.values() for k in a.keys)
    hidden = autos.build(items, place, hidden=[out["trip"].key])
    assert all(a.kind != "trip" for a in hidden)
