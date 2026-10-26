import os
import sys
from datetime import datetime
from types import SimpleNamespace as NS

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from vitrina import search  # noqa: E402

ITEMS = [
    NS(is_video=False, date=datetime(2019, 12, 24), collection="Navidad", place="Cancún"),
    NS(is_video=True, date=datetime(2019, 12, 25), collection="Navidad", place="Mérida"),
    NS(is_video=True, date=datetime(2021, 7, 1), collection="", place="París"),
]
place = lambda it: it.place  # noqa: E731


def hits(q):
    ok = search.matcher(q, place)
    return [k for k, it in enumerate(ITEMS) if ok(it)]


def test_kind_year_month_place():
    assert hits("videos") == [1, 2]
    assert hits("fotos") == [0]
    assert hits("2019") == [0, 1]
    assert hits("diciembre") == [0, 1] and hits("December") == [0, 1] and hits("dic") == [0, 1]
    assert hits("cancun") == [0]          # sin acento
    assert hits("navidad video") == [1]   # todas las palabras
    assert hits("videos de 2021") == [2]
    assert search.matcher("   ", place) is None
