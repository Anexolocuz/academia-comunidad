"""Pruebas del panel de analítica (`app/analitica.py`): `python3 pruebas/unidad_analitica.py`.
Usan una carpeta temporal y datos inventados.

Regresión 2026-11-18: el navegador registra tiempo con `metodo: "investigacion"` (vistas de paper y verificar)
y `METODOS` no lo tenía; el panel y `/api/hermes/resumen` respondían `KeyError: 'investigacion'`."""
import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
_TMP = tempfile.TemporaryDirectory()
os.environ["ACADEMIA_DATOS"] = _TMP.name
sys.path.insert(0, str(RAIZ / "app"))

import base  # noqa: E402
base.iniciar()
import lectura  # noqa: E402
lectura.iniciar()
import curriculo, adaptativo, lecciones, verificacion  # noqa: E402,F401  (crean sus tablas al importarse)
import analitica  # noqa: E402
from base import ejecutar  # noqa: E402

U = "ana@prueba"


def tiempo(metodo, segundos=120, tema=None):
    ejecutar("INSERT INTO actividad(usuario,tipo,tema,area,valor,detalle,fecha) VALUES(?,?,?,?,?,?,?)",
             (U, "tiempo", tema, None, segundos, json.dumps({"metodo": metodo}), time.time() - 60))


class Metodos(unittest.TestCase):
    def setUp(self):
        ejecutar("DELETE FROM actividad")

    def test_investigacion_cuenta_como_metodo(self):
        tiempo("investigacion", 300)
        met = {m["id"]: m for m in analitica.analitica(U)["metodos"]}
        self.assertIn("investigacion", met)
        self.assertAlmostEqual(met["investigacion"]["min"], 5.0, places=1)

    def test_metodo_desconocido_no_rompe_el_panel(self):
        tiempo("vista_que_aun_no_existe", 60)
        met = {m["id"]: m for m in analitica.analitica(U)["metodos"]}
        self.assertAlmostEqual(met["otro"]["min"], 1.0, places=1)


if __name__ == "__main__":
    r = unittest.main(exit=False, verbosity=2).result
    sys.exit(0 if r.wasSuccessful() else 1)
