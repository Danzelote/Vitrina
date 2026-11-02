import os
import random
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from vitrina import kenburns as KB  # noqa: E402


def visible_all(m, faces, steps=40):
    for k in range(steps + 1):
        z, dx, dy = m.at(KB.SPAN * k / steps)
        if not KB._fits(faces, z, dx, dy):
            return False
    return True


def test_faces_never_cut():
    rng = random.Random(3)
    cases = [
        [(-0.45, -0.40, -0.25, -0.05)],                     # cara en la orilla izquierda
        [(0.20, -0.45, 0.44, -0.10)],                       # arriba a la derecha
        [(-0.40, -0.30, 0.40, 0.35)],                       # grupo grande (muy cerca)
        [(-0.1, -0.1, 0.1, 0.1)],                           # al centro
    ]
    for faces in cases:
        for style in (KB.PAN, KB.ZOOM):
            for _ in range(20):
                m = KB.Motion(style, rng=rng, faces=faces)
                assert visible_all(m, faces), (style, faces)


def test_without_faces_unchanged():
    m = KB.Motion(KB.PAN, rng=random.Random(1))
    assert m.style == KB.PAN and m.z0 != m.z1
