"""Pruebas de la auditoría de claves (`app/auditoria.py`) y de su efecto en el Reto: `python3 pruebas/unidad_auditoria.py`.
Usan una carpeta temporal y datos inventados."""
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
import curriculo, adaptativo, lecciones, verificacion  # noqa: E402,F401
import auditoria as aud  # noqa: E402
import indice  # noqa: E402
from base import ejecutar  # noqa: E402

aud.iniciar()
indice.iniciar()
U = "ana@prueba"
P = {"pregunta": "E[X]=5 y E[X²]=29: ¿varianza?", "opciones": ["34", "24", "4", "145"], "correcta": 3}


class Auditoria(unittest.TestCase):
    def setUp(self):
        ejecutar("DELETE FROM auditoria_pregunta")

    def test_sin_veredicto_se_usa_tal_cual(self):
        self.assertEqual(aud.aplicar(P, aud.mapa(U)), (True, 3, None, None))

    def test_clave_mal_se_corrige(self):
        self.assertIsNone(aud.guardar(U, dict(P, veredicto="clave_mal", real=2, nota="29-25=4"), "claude"))
        usable, c, v, nota = aud.aplicar(P, aud.mapa(U))
        self.assertEqual((usable, c, v), (True, 2, "clave_mal"))

    def test_clave_corregida_vale_con_opciones_barajadas(self):
        aud.guardar(U, dict(P, veredicto="clave_mal", real=2))
        barajada = dict(P, opciones=["4", "145", "34", "24"], correcta=1)     # el Reto baraja
        self.assertEqual(aud.aplicar(barajada, aud.mapa(U))[:2], (True, 0))

    def test_sin_correcta_y_ambigua_no_se_usan(self):
        for ver in ("sin_correcta", "ambigua", "mal_planteada"):
            aud.guardar(U, dict(P, veredicto=ver))
            self.assertFalse(aud.aplicar(P, aud.mapa(U))[0], ver)

    def test_la_huella_ignora_espacios(self):
        aud.guardar(U, dict(P, veredicto="sin_correcta"))
        self.assertFalse(aud.aplicar(dict(P, pregunta="  E[X]=5 y  E[X²]=29: ¿varianza? "), aud.mapa(U))[0])

    def test_validaciones(self):
        self.assertIsNotNone(aud.guardar(U, {"pregunta": "x", "veredicto": "inventado"}))
        self.assertIsNotNone(aud.guardar(U, dict(P, veredicto="clave_mal")))           # falta «real»
        self.assertIsNotNone(aud.guardar(U, dict(P, veredicto="clave_mal", real=9)))   # fuera de rango
        self.assertIsNotNone(aud.guardar(U, {"veredicto": "ok"}))

    def test_cada_persona_ve_solo_lo_suyo(self):
        aud.guardar(U, dict(P, veredicto="sin_correcta"))
        self.assertTrue(aud.aplicar(P, aud.mapa("beto@prueba"))[0])


class RetoRespetaLaAuditoria(unittest.TestCase):
    def test_banco_corrige_y_descarta(self):
        ejecutar("DELETE FROM auditoria_pregunta")
        tid = next(t["id"] for a in curriculo.areas(U).values() for m in a["modulos"] if m.get("nivel") in indice.DIF_NIVEL
                   for t in m["temas_obj"])
        quiz = [dict(P, tipo="opcion", explicacion=""),
                {"tipo": "opcion", "pregunta": "¿Pregunta sin respuesta?", "opciones": ["a", "b", "c", "d"], "correcta": 0}]
        ejecutar("INSERT OR REPLACE INTO leccion(usuario,tema,contenido,ejercicios,creado) VALUES(?,?,?,?,?)",
                 (U, tid, "x", json.dumps({"quiz": quiz, "tarjetas": []}), time.time()))
        aud.guardar(U, dict(P, veredicto="clave_mal", real=2))
        aud.guardar(U, {"pregunta": "¿Pregunta sin respuesta?", "veredicto": "sin_correcta"})
        b = indice.banco(U)
        self.assertEqual([x["correcta"] for x in b if x["pregunta"] == P["pregunta"]], [2])
        self.assertFalse([x for x in b if x["pregunta"] == "¿Pregunta sin respuesta?"])


class EsencialDeLaLeccion(unittest.TestCase):
    def test_objetivos_partes_y_comprueba(self):
        import servidor  # noqa: F401  (carga pesada, solo para la función)
        md = ("## 🎯 Objetivos\n1. Calcular X.\n\n## 🗺️ Mapa de la lección\n> **Pregunta guía:** ¿Por qué X?\n\n"
              "## Parte 1 · Primera\n### 📘 Desarrollo\ntexto largo\n### ✅ Comprueba\n1. ¿Qué es X?\n\n"
              "## Parte 2 · Segunda\n### ✅ Comprueba\n1. ¿Y?\n")
        t = servidor._secciones_leccion(md)
        for trozo in ("Calcular X", "¿Por qué X?", "Parte 1 · Primera", "¿Qué es X?", "Parte 2 · Segunda", "¿Y?"):
            self.assertIn(trozo, t)
        self.assertNotIn("texto largo", t)


class Recalificar(unittest.TestCase):
    def test_sube_lo_que_paso_y_baja_lo_que_no_tenia_base(self):
        import servidor
        ejecutar("DELETE FROM auditoria_pregunta")
        m = next(m for a in curriculo.areas(U).values() for m in a["modulos"] if len(m["temas_obj"]) >= 2)
        t0, t1 = m["temas_obj"][0], m["temas_obj"][1]
        q = lambda n, tema, c: {"tema": tema, "pregunta": f"q{n}-{m['ref']}", "opciones": ["aa", "bb", "cc", "dd"], "correcta": c}  # noqa
        preguntas = [q(0, t0["i"], 3), q(1, t0["i"], 3), q(2, t1["i"], 0), q(3, t1["i"], 0)]
        # tema 0: eligió 2 y 2 (la clave decía 3: falsa) · tema 1: eligió 0 y 0 (pasó, pero la clave de q2 es falsa)
        resp = {"0": {"j": 2, "ok": False, "tema": t0["i"], "conf": "seguro"}, "1": {"j": 2, "ok": False, "tema": t0["i"], "conf": "seguro"},
                "2": {"j": 0, "ok": True, "tema": t1["i"], "conf": "seguro"}, "3": {"j": 0, "ok": True, "tema": t1["i"], "conf": "seguro"}}
        resultado = {"bien": 2, "total": 4, "pasados": [{"id": t1["id"], "t": t1["t"]}], "pendientes": []}
        pid = ejecutar("INSERT INTO prueba_nivel(usuario,ref,datos,respuestas,estado,resultado,creada,terminada) VALUES(?,?,?,?,?,?,?,?)",
                       (U, m["ref"], json.dumps({"preguntas": preguntas, "temas": [{"i": t0["i"], "t": "a"}, {"i": t1["i"], "t": "b"}]}),
                        json.dumps(resp), "terminada", json.dumps(resultado), time.time(), time.time())).lastrowid
        curriculo.marcar(U, t1["id"], estado="probado", quiz=1.0)
        for n in (0, 1):
            aud.guardar(U, dict(preguntas[n], veredicto="clave_mal", real=2))
        aud.guardar(U, dict(preguntas[2], veredicto="clave_mal", real=1))
        r = servidor.recalificar_prueba(U, pid)
        self.assertEqual((r["bien"], r["total"]), (3, 4))
        self.assertEqual(r["recalificada"]["subieron"], [t0["id"]])
        self.assertEqual(r["recalificada"]["bajaron"], [t1["id"]])
        self.assertEqual(curriculo.avances(U)[t0["id"]]["estado"], "probado")
        self.assertEqual(curriculo.avances(U)[t1["id"]]["estado"], "visto")
        r2 = servidor.recalificar_prueba(U, pid)                 # repetirlo no cambia nada y conserva el «antes»
        self.assertEqual(r2["recalificada"]["antes"]["bien"], 2)
        self.assertEqual(r2["recalificada"]["subieron"], [])

if __name__ == "__main__":
    r = unittest.main(exit=False, verbosity=2).result
    sys.exit(0 if r.wasSuccessful() else 1)
