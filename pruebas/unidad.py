#!/usr/bin/env python3
"""Pruebas unitarias (biblioteca estándar, sin internet ni IA) de la lógica que no se ve a simple vista: cálculos de
💹 acciones (RSI, tasa base, indicadores, etiquetas, margen que aprende, cartera) y la caché de áreas por persona.
Usa una carpeta de datos temporal. Uso: python3 pruebas/unidad.py   (sale con código 1 si algo falla)"""
import json
import math
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path

for _f in (sys.stdout, sys.stderr):
    try:
        _f.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

RAIZ = Path(__file__).resolve().parent.parent
_TMP = tempfile.TemporaryDirectory()
os.environ["ACADEMIA_DATOS"] = _TMP.name
sys.path.insert(0, str(RAIZ / "app"))

import base  # noqa: E402
base.iniciar()
import curriculo as cur  # noqa: E402
import acciones as ac  # noqa: E402
from base import ejecutar  # noqa: E402

U = "persona@prueba"
DIA = 86400


def serie_de(precios, inicio=1_700_000_000):
    return [[inicio + k * DIA, p, p, p, 1000] for k, p in enumerate(precios)]


def guardar_info(simbolo, precios, moneda="USD", **extra):
    meta = {"precio": precios[-1], "cambio": (precios[-1] / precios[-2] - 1) * 100}
    ejecutar("""INSERT OR REPLACE INTO accion_info(simbolo,nombre,moneda,bolsa,tipo,sector,meta,serie,actualizado)
                VALUES(?,?,?,?,?,?,?,?,?)""",
             (simbolo, extra.get("nombre", simbolo), moneda, "X", "acción", extra.get("sector", "Tecnología"),
              json.dumps(meta), json.dumps(serie_de(precios)), time.time()))   # «actualizado» reciente: sin internet


class Acciones(unittest.TestCase):
    def test_etiquetas_fijas(self):
        self.assertEqual(ac.etiqueta(85), "muy probable")
        self.assertEqual(ac.etiqueta(70), "muy probable")
        self.assertEqual(ac.etiqueta(50), "probable")
        self.assertEqual(ac.etiqueta(30), "poco probable")
        self.assertEqual(ac.etiqueta(5), "muy poco probable")

    def test_simbolos_validos(self):
        for s in ("NVDA", "ECOPETROL.CL", "^GSPC", "USDCOP=X", "BRK-B"):
            self.assertTrue(ac.valido(s), s)
        for s in ("", "<b>", "a b", "x" * 21, "../etc"):
            self.assertFalse(ac.valido(s), s)

    def test_rsi_extremos(self):
        self.assertEqual(ac._rsi(list(range(1, 40))), 100.0)          # solo sube
        self.assertLess(ac._rsi(list(range(40, 1, -1))), 1)            # solo baja
        zigzag = [10 + (k % 2) for k in range(60)]
        self.assertAlmostEqual(ac._rsi(zigzag), 50, delta=5)           # sube y baja igual

    def test_tasa_base(self):
        sube = ac.tasa_base(serie_de([100 * 1.001 ** k for k in range(300)]), 30)
        self.assertEqual(sube["p_sube"], 100.0)
        baja = ac.tasa_base(serie_de([100 * 0.999 ** k for k in range(300)]), 30)
        self.assertEqual(baja["p_sube"], 0.0)
        self.assertIsNone(ac.tasa_base(serie_de([1, 2, 3]), 30))       # muy poca historia
        self.assertLess(baja["p10"], baja["p90"])

    def test_indicadores_y_rango(self):
        precios = [100 * math.exp(0.01 * math.sin(k / 3)) for k in range(400)]
        guardar_info("ZIG", precios)
        ind = ac.indicadores(ac.info("ZIG"))
        self.assertAlmostEqual(ind["precio"], precios[-1])
        r = ind["rangos"][30]
        self.assertLess(r["bajo"], ind["precio"])
        self.assertGreater(r["alto"], ind["precio"])
        self.assertTrue(all("." not in x.split("%")[0][-3:] for x in ac.explicar_indicadores(ind)))   # coma decimal

    def test_margen_que_aprende(self):
        self.assertEqual(ac.margen_ia(U, "MAL")[0], 20)                 # sin historia: de fábrica
        for k in range(6):   # la IA dijo 90 % y siempre bajó; la estadística decía 50 %
            ejecutar("""INSERT INTO accion_pronostico(usuario,simbolo,creado,dias,precio,p_sube,datos,resultado)
                        VALUES(?,?,?,?,?,?,?,?)""",
                     (U, "MAL", time.time() - k, 30, 100, 90, json.dumps({"base": {"p_sube": 50}}),
                      json.dumps({"brier": 0.81, "subio": False, "acierto": False, "dentro_rango": True})))
        self.assertLessEqual(ac.margen_ia(U, "MAL")[0], 10)
        self.assertEqual(ac.margen_ia("otra@persona", "MAL")[0], 20)    # el historial es de cada persona

    def test_cartera(self):
        guardar_info("AAA", [100 + k * 0.1 + (k % 3) for k in range(300)], sector="Tecnología")
        guardar_info("BBB", [50 - (k % 4) + k * 0.05 for k in range(300)], sector="Energía")
        for s, cant, compra in (("AAA", 10, 100), ("BBB", 20, 40)):
            ejecutar("""INSERT OR REPLACE INTO accion_vigilada(usuario,simbolo,orden,alerta_pct,agregada,cantidad,precio_compra)
                        VALUES(?,?,0,4,?,?,?)""", (U, s, time.time(), cant, compra))
        c = ac.cartera(U, moneda="USD")
        self.assertAlmostEqual(sum(p["peso"] for p in c["posiciones"]), 100, places=6)
        self.assertGreater(c["ganancia"], 0)
        self.assertLessEqual(c["riesgo"]["volatilidad"], c["riesgo"]["suma_individual"] + 1e-9)   # diversificar no suma riesgo
        self.assertIsNone(ac.cartera("nadie@prueba"))

    def test_alertas(self):
        v = {"simbolo": "AAA", "alerta_arriba": 150, "alerta_abajo": 90, "alerta_pct": 4}
        self.assertEqual([a["tipo"] for a in ac.alertas_de(v, {"precio": 160, "cambio": 5})], ["arriba", "movimiento"])
        self.assertEqual([a["tipo"] for a in ac.alertas_de(v, {"precio": 100, "cambio": 1})], [])
        self.assertEqual(ac.alertas_de(v, {"precio": None}), [])


class CacheDeAreas(unittest.TestCase):
    def test_se_invalida_al_cambiar(self):
        cur.cargar()
        antes = set(cur.areas(U))
        self.assertIs(cur._CACHE[U][1], cur._CACHE[U][1])
        area = {"id": "zz_prueba", "nombre": "Prueba", "modulos": [{"id": "m", "t": "M", "nivel": 1, "temas": ["Tema"]}]}
        ejecutar("INSERT INTO area_extra(id,usuario,datos,creado) VALUES(?,?,?,0)", ("zz_prueba", U, json.dumps(area)))
        self.assertIn("zz_prueba", cur.areas(U))
        area["modulos"][0]["temas"].append("Otro tema")
        ejecutar("UPDATE area_extra SET datos=? WHERE id='zz_prueba'", (json.dumps(area),))
        self.assertEqual(len(cur.areas(U)["zz_prueba"]["modulos"][0]["temas_obj"]), 2)
        ejecutar("DELETE FROM area_extra WHERE id='zz_prueba'")
        self.assertEqual(set(cur.areas(U)), antes)
        self.assertNotIn("zz_prueba", cur.areas("otra@persona"))      # cada persona su caché

    def test_devuelve_copia_del_diccionario(self):
        a = cur.areas(U)
        a.pop(next(iter(a)))
        self.assertEqual(len(cur.areas(U)), len(a) + 1)


if __name__ == "__main__":
    r = unittest.main(exit=False, verbosity=2).result
    sys.exit(0 if r.wasSuccessful() else 1)
