import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from vitrina import camera as cam  # noqa: E402
from vitrina import config as C  # noqa: E402

VW, VH = 1280, 800


def plane():
    return cam.Plane(*cam.grid_shape(500))


def test_grid_shape_keeps_screen_like_proportion():
    assert cam.grid_shape(126) == (14, 9)
    cols, rows = cam.grid_shape(500)
    assert cols == 28 and rows == 18


def test_zoom_at_keeps_point_under_cursor():
    cx, cy, s0, s1 = 900.0, 700.0, 0.62, 1.0
    fx, fy = 1100.0, 150.0
    nx, ny = cam.zoom_at(cx, cy, s0, s1, fx, fy, VW, VH)
    before = (cx + (fx - VW / 2) / s0, cy + (fy - VH / 2) / s0)
    after = (nx + (fx - VW / 2) / s1, ny + (fy - VH / 2) / s1)
    assert abs(before[0] - after[0]) < 1e-6 and abs(before[1] - after[1]) < 1e-6


def _edge_cases():
    """Anclas cerca de cada esquina: el bug que el usuario encontró."""
    s = C.ZOOMS[3]
    p = plane()
    lox, hix, loy, hiy = cam.bounds(s, p, VW, VH)
    for mx0, my0 in [(60, 60), (1220, 60), (60, 760), (1220, 760), (640, 400)]:
        cx0, cy0 = cam.clamp((lox + hix) / 2, (loy + hiy) / 2, s, p, VW, VH)
        yield s, p, cam.Anchor(mx0, my0, cx0, cy0), (lox, hix, loy, hiy)


def test_every_edge_is_reachable_from_any_anchor():
    for s, p, anchor, (lox, hix, loy, hiy) in _edge_cases():
        for mx, my, ex, ey in [(0, 0, lox, loy), (VW, 0, hix, loy), (0, VH, lox, hiy), (VW, VH, hix, hiy)]:
            x, y = cam.pan_target(mx, my, anchor, s, p, VW, VH)
            assert abs(x - ex) < 1e-6, (anchor, mx, x, ex)
            assert abs(y - ey) < 1e-6, (anchor, my, y, ey)


def test_no_jump_at_anchor():
    for s, p, anchor, _ in _edge_cases():
        x, y = cam.pan_target(anchor.mx, anchor.my, anchor, s, p, VW, VH)
        assert abs(x - anchor.cx) < 1e-6 and abs(y - anchor.cy) < 1e-6


def test_clamp_centers_small_grids():
    p = cam.Plane(3, 2)
    x, y = cam.clamp(0, 0, C.ZOOMS[0], p, VW, VH)
    assert x == p.width / 2 and y == p.height / 2


def test_index_at():
    p = cam.Plane(10, 3)
    pitch = C.CELL + C.GAP
    assert p.index_at(5, 5, 30) == 0
    assert p.index_at(pitch + 5, pitch + 5, 30) == 11
    assert p.index_at(C.CELL + 5, 5, 30) is None  # en el espacio entre fotos
    assert p.index_at(5, 5, 0) is None
