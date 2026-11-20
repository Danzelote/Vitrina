import os
import sys

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pygame  # noqa: E402

from vitrina import textfield as TF  # noqa: E402

CMD = pygame.KMOD_GUI


def key(f, k, mod=0):
    return f.handle(pygame.event.Event(pygame.KEYDOWN, key=k, mod=mod, unicode="", scancode=0))


def typ(f, s):
    f.handle(pygame.event.Event(pygame.TEXTINPUT, text=s))


def test_edit_keys():
    f = TF.TextField("Sábado 14 de septiembre")
    key(f, pygame.K_a, CMD)
    assert f.all
    typ(f, "Cumple")
    assert f.text == "Cumple" and not f.all
    typ(f, " de Laura")
    key(f, pygame.K_BACKSPACE, pygame.KMOD_ALT)
    assert f.text == "Cumple de "
    key(f, pygame.K_LEFT, CMD)
    typ(f, "El ")
    assert f.text == "El Cumple de "
    key(f, pygame.K_RIGHT, CMD)
    key(f, pygame.K_BACKSPACE, CMD)
    assert f.text == "" and f.cur == 0
    f.set("hola")
    key(f, pygame.K_a, pygame.KMOD_CTRL)
    key(f, pygame.K_x, pygame.KMOD_CTRL)
    assert f.text == ""
    key(f, pygame.K_v, CMD)
    key(f, pygame.K_v, CMD)
    assert f.text == "holahola"
    key(f, pygame.K_LEFT)
    key(f, pygame.K_DELETE)
    assert f.text == "holahol"


def test_secret_not_copied():
    TF._clip[0] = "x"
    f = TF.TextField("secreto", secret=True)
    key(f, pygame.K_a, CMD)
    key(f, pygame.K_c, CMD)
    assert TF.clipboard_get() != "secreto"
