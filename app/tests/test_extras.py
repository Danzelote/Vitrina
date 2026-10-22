import random
import time
from datetime import date, datetime
from types import SimpleNamespace

from vitrina import kenburns as KB
from vitrina import memories as MEM
from vitrina import night as N


def test_kenburns_always_covers_rect():
    rng = random.Random(1)
    for style in (KB.ZOOM, KB.PAN):
        for _ in range(50):
            m = KB.Motion(style, rng)
            for k in range(0, 101):
                z, dx, dy = m.at(KB.SPAN * k / 100)
                x, y, w, h = KB.apply((0, 0, 100, 60), z, dx, dy)
                assert x <= 1e-9 and y <= 1e-9 and x + w >= 100 - 1e-9 and y + h >= 60 - 1e-9


def test_kenburns_amount_zero_is_identity():
    m = KB.Motion(KB.PAN, random.Random(2))
    assert KB.apply((10, 20, 100, 60), *m.at(3.0), amount=0.0) == (10, 20, 100, 60)


def test_on_this_day_window_and_wrap():
    mk = lambda y, mo, d: SimpleNamespace(date=datetime(y, mo, d))
    items = [mk(2023, 10, 21), mk(2024, 10, 24), mk(2024, 10, 25), mk(2026, 10, 21), mk(2022, 12, 30)]
    assert MEM.on_this_day(items, range(len(items)), date(2026, 10, 21)) == [0, 1]
    assert MEM.on_this_day(items, range(len(items)), date(2027, 1, 1)) == [4]
    assert MEM.years_ago(items[0].date, date(2026, 10, 21)) == "Hace 3 años"


def test_schedule_crosses_midnight():
    at = lambda h, m=0: time.struct_time((2026, 10, 21, h, m, 0, 2, 294, -1))
    assert N.in_schedule("23-7", at(23, 30)) and N.in_schedule("23-7", at(3))
    assert not N.in_schedule("23-7", at(7)) and not N.in_schedule("23-7", at(12))
    assert N.in_schedule("0-6", at(0)) and not N.in_schedule("0-6", at(6))
