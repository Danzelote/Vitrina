"""Arranca Vitrina.

    python app/main.py --demo                  # con fotos de prueba
    python app/main.py --folder ~/Pictures/X   # con una carpeta tuya
"""

import argparse
import os
import sys
import threading

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))



def crash_log(library):
    """Si Python se cierra de golpe (por ejemplo, una falla en una librería de
    video), deja el rastro en ~/.cache/vitrina/fallo.log para poder arreglarlo."""
    import faulthandler
    path = os.path.join(library.cache_dir(), "fallo.log")
    try:
        if os.path.getsize(path) > 0:
            print(f"La vez pasada Vitrina se cerró de golpe. Detalles en: {path}")
            os.replace(path, path + ".anterior")
    except OSError:
        pass
    f = open(path, "w")
    faulthandler.enable(file=f, all_threads=True)
    return f


def main():
    ap = argparse.ArgumentParser(prog="vitrina", description="Portarretratos digital para Macs viejas.")
    ap.add_argument("--folder", help="carpeta con fotos (incluye subcarpetas; cada una es una colección)")
    ap.add_argument("--demo", nargs="?", const=140, type=int, metavar="N",
                    help="usa N fotos de prueba (140 si no dices cuántas)")
    ap.add_argument("--fullscreen", action="store_true", help="pantalla completa")
    ap.add_argument("--invert-zoom", action="store_true", help="invierte la dirección del zoom con la rueda")
    ap.add_argument("--debug-input", action="store_true", help="muestra en la terminal los eventos del trackpad")
    ap.add_argument("--no-web", action="store_true", help="sin la app del celular")
    args = ap.parse_args()

    # Lo primero: la ventana con el logo animado. Lo pesado (librerías, leer las
    # fotos) se hace en otro hilo mientras tanto.
    splash = None
    try:
        from vitrina.splash import Splash
        splash = Splash(fullscreen=args.fullscreen)
        splash.frame()
    except Exception as exc:       # noqa: BLE001 (sin logo, la app abre igual)
        print("Sin logo de arranque:", exc)
    loaded = {}

    def load():
        try:
            from vitrina import library
            loaded["log"] = crash_log(library)
            folder = args.folder
            if folder:
                folder = os.path.abspath(os.path.expanduser(folder))
                os.makedirs(folder, exist_ok=True)
            if args.demo or not folder:
                print("Generando fotos de prueba (solo la primera vez)…")
                folder = library.make_demo(args.demo or 140)
            print(f"Leyendo {folder}…")
            items = library.scan(folder)
            print(f"{len(items)} fotos encontradas.")
            processor = library.Processor(items)
            processor.start()
            from vitrina.livelib import LiveLibrary
            import vitrina.ui  # noqa: F401 (carga las librerías de video e imagen)
            loaded.update(folder=folder, items=items, processor=processor,
                          lib=LiveLibrary(folder, items, processor))
        except BaseException as exc:      # noqa: BLE001
            loaded["error"] = exc

    worker = threading.Thread(target=load, daemon=True)
    # Mientras carga, el logo cambia de hilo más seguido (si no, la carga lo traba a saltitos).
    switch = sys.getswitchinterval()
    sys.setswitchinterval(0.0005)
    worker.start()
    if splash:
        splash.run_until(lambda: not worker.is_alive())
    worker.join()
    sys.setswitchinterval(switch)
    if "error" in loaded:
        raise loaded["error"]

    from vitrina.ui import App
    app = App(loaded["items"], loaded["processor"], fullscreen=args.fullscreen, invert_zoom=args.invert_zoom,
              debug_input=args.debug_input, lib=loaded["lib"], splash=splash)
    if not args.no_web:
        try:
            from vitrina.web.server import WebServer
            app.web = WebServer(app, loaded["lib"])
            url = app.web.base_url()
            print(f"App del celular: {url}" if url else "App del celular: sin red por ahora")
        except OSError as exc:
            print("No se pudo iniciar la app del celular:", exc)
    app.run()
    if app.web:
        app.web.close()


if __name__ == "__main__":
    main()
