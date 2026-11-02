"""Dónde hay caras en cada foto (para que el Ken Burns no las corte).

Solo detecta caras, no reconoce de quién son. Usa YuNet (OpenCV), un modelo
chiquito que viene con la app (data/face_detection_yunet_2023mar.onnx).

La detección corre en un proceso aparte, con la prioridad más baja y una
pausa entre foto y foto: la primera vez revisa toda la biblioteca poco a poco
sin calentar la Mac, y luego solo las fotos nuevas. Si OpenCV no está o no
funciona en esta computadora, simplemente no hay caras (todo sigue igual).
Los resultados se guardan en la caché: {clave: [[x, y, ancho, alto], …]}, de 0 a 1.
"""

import json
import os
import subprocess
import sys
import threading
import time

from . import library

MODEL = os.path.join(os.path.dirname(__file__), "data", "face_detection_yunet_2023mar.onnx")
PAUSE = 0.8            # segundos entre foto y foto (para que casi no se note)
DETECT_SIDE = 640      # se busca en la foto reducida a este lado mayor
MIN_SCORE = 0.75


class FaceScanner:
    def __init__(self):
        self.path = os.path.join(library.cache_dir(), "faces.json")
        try:
            with open(self.path) as f:
                self.found = json.load(f)
        except (OSError, ValueError):
            self.found = {}
        self.lock = threading.Lock()
        self.queue = {}          # clave -> Item que falta revisar
        self.status = "esperando"
        self.errors = 0
        self._wake = threading.Event()
        self._thread = None

    def attach(self, items):
        """Pone a cada foto sus caras (si ya se buscaron) y forma las que faltan."""
        with self.lock:
            for it in items:
                f = self.found.get(it.key)
                it.faces = tuple(tuple(b) for b in f) if f else ()
                if f is None and not it.is_video:
                    self.queue[it.key] = it
        self._wake.set()

    def start(self):
        if self._thread is None and os.path.exists(MODEL):
            self._thread = threading.Thread(target=self._run, daemon=True)
            self._thread.start()

    def _save(self):
        tmp = self.path + ".tmp"
        with open(tmp, "w") as f:
            json.dump(self.found, f)
        os.replace(tmp, self.path)

    def _run(self):
        proc = None
        while True:
            self._wake.wait(30)
            self._wake.clear()
            with self.lock:
                todo = [it for it in self.queue.values() if it.ready and it.screen_path and it.key not in self.found]
                for it in todo:
                    self.queue.pop(it.key, None)
            if not todo:
                self.status = "al día"
                if proc:
                    proc.stdin.close()
                    proc.wait(timeout=5)
                    proc = None
                continue
            if proc is None:
                try:
                    proc = subprocess.Popen(
                        ["nice", "-n", "19", sys.executable, "-m", "vitrina.faces", MODEL],
                        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True,
                        bufsize=1, cwd=os.path.dirname(os.path.dirname(__file__)))
                except OSError:
                    self.status = "sin OpenCV"
                    return
            self.status = f"revisando ({len(todo)} pendientes)"
            changed = 0
            for it in todo:
                try:
                    proc.stdin.write(it.screen_path + "\n")
                    line = proc.stdout.readline()
                except (OSError, ValueError):
                    line = ""
                if not line:
                    # El proceso se cerró: OpenCV no funciona en esta computadora.
                    self.errors += 1
                    self.status = "no funciona en esta Mac" if self.errors >= 3 else "reintentando"
                    proc = None
                    if self.errors >= 3:
                        return
                    break
                try:
                    boxes = json.loads(line)
                except ValueError:
                    boxes = []
                with self.lock:
                    self.found[it.key] = boxes
                it.faces = tuple(tuple(b) for b in boxes)
                changed += 1
                if changed % 20 == 0:
                    self._save()
                time.sleep(PAUSE)
            if changed:
                self._save()
            self._wake.set()

    def summary(self):
        with_faces = sum(1 for v in self.found.values() if v)
        return {"estado": self.status, "revisadas": len(self.found), "con_caras": with_faces}


def _worker(model):
    """Proceso aparte: lee rutas por la entrada, responde las caras de cada una."""
    import cv2   # noqa: E402 (solo aquí: si falla, no afecta a la app)
    det = cv2.FaceDetectorYN.create(model, "", (320, 320), MIN_SCORE, 0.3, 50)
    for line in sys.stdin:
        path = line.strip()
        boxes = []
        try:
            img = cv2.imread(path, cv2.IMREAD_COLOR)
            if img is not None:
                h, w = img.shape[:2]
                k = min(1.0, DETECT_SIDE / max(w, h))
                if k < 1.0:
                    img = cv2.resize(img, (int(w * k), int(h * k)), interpolation=cv2.INTER_AREA)
                h2, w2 = img.shape[:2]
                det.setInputSize((w2, h2))
                _ok, faces = det.detect(img)
                for f in (faces if faces is not None else []):
                    x, y, fw, fh, score = float(f[0]), float(f[1]), float(f[2]), float(f[3]), float(f[-1])
                    if score >= MIN_SCORE and fw > 0 and fh > 0:
                        boxes.append([round(max(0.0, x / w2), 4), round(max(0.0, y / h2), 4),
                                      round(min(1.0, fw / w2), 4), round(min(1.0, fh / h2), 4)])
        except Exception:      # noqa: BLE001
            boxes = []
        sys.stdout.write(json.dumps(boxes) + "\n")
        sys.stdout.flush()


if __name__ == "__main__":
    _worker(sys.argv[1])
