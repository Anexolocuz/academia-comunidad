"""Una lección a medias se retoma desde la parte siguiente tras un reinicio: `python3 pruebas/unidad_retomar.py`.
Usa una carpeta temporal, una IA falsa y ninguna búsqueda real."""
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
import curriculo, adaptativo, verificacion  # noqa: E402,F401
import lecciones as lec  # noqa: E402
from base import ejecutar, fila  # noqa: E402

U = "ana@prueba"


class IAFalsa:
    def __init__(self):
        self.pedidos, self.fases = [], []

    def fase(self, x):
        self.fases.append(x)

    def chat(self, mensajes, max_tokens=0, temperatura=0, esquema=None, **k):
        ultimo = mensajes[-1]["content"]
        self.pedidos.append(ultimo[:60])
        if esquema and "quiz" in json.dumps(esquema):
            return {"quiz": [], "tarjetas": []}
        if esquema:
            raise AssertionError("no debía volver a planear la lección")
        if ultimo.startswith("Escribe ahora la PARTE"):
            n = ultimo.split("PARTE ")[1].split(" ")[0]
            return f"## Parte {n} · nueva\ntexto {n}"
        return "## 🧩 Cómo encaja todo\ncierre"


class Retomar(unittest.TestCase):
    def setUp(self):
        a = next(a for a in curriculo.areas(U).values() if not a.get("idioma") and a.get("grupo") != "Idiomas")
        self.m = a["modulos"][0]
        self.t, self.area = self.m["temas_obj"][0], a
        self.plan = {"partes": [{"titulo": f"P{i}", "ideas": ["x"], "busqueda": "q", "busqueda_en": "q"} for i in (1, 2, 3)],
                     "objetivos": ["o"], "pregunta_guia": "g", "prerrequisitos": [], "consulta_cientifica": "c"}
        contenido = "## 🎯 Objetivos\n1. o\n\n## 🗺️ Mapa\n...\n\n## Parte 1 · P1\ntexto 1\n\n## Parte 2 · P2\ntexto 2 [3]"
        fuentes = [{"titulo": "w1", "url": "u1"}, {"titulo": "w2", "url": "u2"}, {"titulo": "w3", "url": "u3"},
                   {"titulo": "p1", "url": "pu1", "tipo": "paper", "autores": "A", "anio": 2020, "revista": "R",
                    "citas": 1, "abierto": True, "n": "P1"}]
        ejecutar("""INSERT OR REPLACE INTO leccion(usuario,tema,contenido,fuentes,creado,version,completa,plan)
                    VALUES(?,?,?,?,?,?,0,?)""", (U, self.t["id"], contenido, json.dumps(fuentes), time.time(),
                                                 lec.VERSION_LECCION, json.dumps(self.plan)))
        self.antes = (lec._fuentes_web, lec._papers)
        lec._fuentes_web = lambda *a, **k: []
        lec._papers = lambda *a, **k: []

    def tearDown(self):
        lec._fuentes_web, lec._papers = self.antes

    def test_sigue_desde_la_parte_3_sin_replanear(self):
        ia = IAFalsa()
        lec._leccion_a_fondo(ia, self.t, self.area, self.m, {}, U, lec.VERSION_LECCION)
        self.assertIn("Retomando la lección donde iba", ia.fases)
        partes = [p for p in ia.pedidos if p.startswith("Escribe ahora la PARTE")]
        self.assertEqual(len(partes), 1)
        self.assertTrue(partes[0].startswith("Escribe ahora la PARTE 3 de 3"))
        r = fila("SELECT contenido, completa, fuentes FROM leccion WHERE usuario=? AND tema=?", (U, self.t["id"]))
        self.assertEqual(r["completa"], 1)
        for trozo in ("texto 1", "texto 2", "## Parte 3 · nueva", "cierre"):
            self.assertIn(trozo, r["contenido"])
        self.assertIn("u3", r["fuentes"])        # las fuentes de antes se conservan (las citas [3] siguen valiendo)

    def test_otra_version_empieza_de_cero(self):
        self.assertIsNone(lec._retomar_partes(U, self.t["id"], lec.VERSION_MAXIMA))

    def test_partes_desordenadas_empieza_de_cero(self):
        ejecutar("UPDATE leccion SET contenido=? WHERE usuario=? AND tema=?",
                 ("## 🎯 Objetivos\n1. o\n\n## Parte 2 · P2\nx", U, self.t["id"]))
        self.assertIsNone(lec._retomar_partes(U, self.t["id"], lec.VERSION_LECCION))


if __name__ == "__main__":
    r = unittest.main(exit=False, verbosity=2).result
    sys.exit(0 if r.wasSuccessful() else 1)
