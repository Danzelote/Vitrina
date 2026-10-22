"""Arranca Vitrina.

    python app/main.py --demo                  # con fotos de prueba
    python app/main.py --folder ~/Pictures/X   # con una carpeta tuya
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from vitrina import library  # noqa: E402


def main():
    ap = argparse.ArgumentParser(prog="vitrina", description="Portarretratos digital para Macs viejas.")
    ap.add_argument("--folder", help="carpeta con fotos (incluye subcarpetas; cada una es una colección)")
    ap.add_argument("--demo", nargs="?", const=140, type=int, metavar="N",
                    help="usa N fotos de prueba (140 si no dices cuántas)")
    ap.add_argument("--fullscreen", action="store_true", help="pantalla completa")
    ap.add_argument("--invert-zoom", action="store_true", help="invierte la dirección del zoom con la rueda")
    ap.add_argument("--debug-input", action="store_true", help="muestra en la terminal los eventos del trackpad")
    args = ap.parse_args()

    folder = args.folder
    if args.demo or not folder:
        print("Generando fotos de prueba (solo la primera vez)…")
        folder = library.make_demo(args.demo or 140)
    print(f"Leyendo {folder}…")
    items = library.scan(folder)
    print(f"{len(items)} fotos encontradas.")
    processor = library.Processor(items)
    processor.start()

    from vitrina.ui import App
    App(items, processor, fullscreen=args.fullscreen, invert_zoom=args.invert_zoom,
        debug_input=args.debug_input).run()


if __name__ == "__main__":
    main()
