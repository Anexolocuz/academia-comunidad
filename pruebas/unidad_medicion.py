"""Pruebas de la fase F2 (banco de pruebas de la IA). Aparte de `unidad.py` para no tocar el mismo archivo que otras
ventanas: `python3 pruebas/unidad_medicion.py`. No llaman a ningún modelo ni a la red: usan textos inventados."""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

RAIZ = Path(__file__).resolve().parent.parent
_TMP = tempfile.TemporaryDirectory()
os.environ["ACADEMIA_DATOS"] = _TMP.name
os.environ["ACADEMIA_MEDICION"] = str(Path(_TMP.name) / "medicion")
sys.path.insert(0, str(RAIZ / "app"))

import base  # noqa: E402
base.iniciar()
import medicion as M  # noqa: E402

FUENTES = {"fuentes": [{"titulo": "Wikipedia", "url": "https://es.wikipedia.org/wiki/Teorema_de_Bayes", "texto": "x"},
                       {"titulo": "Otra", "url": "https://example.edu/bayes", "texto": "y"}],
           "papers": [{"titulo": "Un paper", "url": "https://doi.org/10.1/abc", "doi": "10.1/abc", "autores": "Pérez", "anio": 2020,
                       "revista": "Revista", "tipo": "article", "citas": 10, "resumen": "Resumen del paper."}]}

BUENA = ("## Parte 1 · Teorema\n### 🧠 Intuición\n" + "palabra del texto en la lección con que de la " * 120
         + "\n### 📘 Desarrollo\nEl resultado $P(A|B)=\\frac{P(B|A)P(A)}{P(B)}$ según [1] y [P1].\n"
         "### ✍️ Ejemplos resueltos\n" + "el caso de los datos con la prueba para el estudio " * 100
         + "\n### ⚠️ Matices\nLa tasa base importa [2].\n### ✅ Comprueba\n"
         "<details><summary>Respuesta</summary>a</details>\n<details><summary>Respuesta</summary>b</details>\n")


def ejercicios_buenos():
    return {"quiz": [{"tipo": "opcion", "pregunta": f"Pregunta {i}", "opciones": ["a", "b", "c", "d"], "correcta": i % 4,
                      "explicacion": "porque"} for i in range(6)]
            + [{"tipo": "abierta", "pregunta": "Explica por qué", "opciones": [], "correcta": 0, "explicacion": "modelo"}],
            "tarjetas": [{"frente": f"¿Por qué ocurre el fenómeno {i}?", "reverso": "respuesta"} for i in range(8)]}


class Variantes(unittest.TestCase):
    def test_claves(self):
        self.assertEqual(M.variante("g38-alto")["esfuerzo"], "high")
        self.assertTrue(M.variante("local+sk")["skills"])
        self.assertFalse(M.variante("local")["skills"])
        with self.assertRaises(ValueError):
            M.variante("inventada")
        with self.assertRaises(ValueError):
            M.variante("local+otra")

    def test_skills_sin_cabecera_y_con_tope(self):
        with tempfile.TemporaryDirectory() as d:
            for etapa, n in (("09-x", "uno"), ("10-y", "dos")):
                (Path(d) / etapa / n).mkdir(parents=True)
                (Path(d) / etapa / n / "SKILL.md").write_text(
                    f"---\nname: {n}\ndescription: d\n---\n# {n}\n" + ("párrafo largo\n\n" * 400), encoding="utf-8")
            t = M.cargar_skills(("uno", "dos", "no-existe"), carpeta=d, tope=2000)
            self.assertIn("### Método: uno", t)
            self.assertIn("### Método: dos", t)
            self.assertNotIn("description:", t)
            self.assertLess(len(t), 2400)
            self.assertEqual(M.cargar_skills(("no-existe",), carpeta=d), "")

    def test_skills_reales_se_encuentran(self):
        if not M.SKILLS_DIR.exists():
            self.skipTest("la colección de skills no está en este equipo")
        t = M.cargar_skills()
        self.assertIn("ensenar-para-dominar", t)

    def test_prompts_sin_datos_personales(self):
        msgs, tokens = M.mensajes_parte("bayes", FUENTES, True)
        todo = json.dumps(msgs, ensure_ascii=False)
        self.assertNotIn("[[PERFIL]]", todo)
        self.assertIn("Estudiante anónimo", todo)
        self.assertGreater(tokens, 500)
        self.assertEqual(len(M.mensajes_parte("bayes", FUENTES, False)[0][0]["content"]) <
                         len(msgs[0]["content"]), True)


class Revision(unittest.TestCase):
    def test_leccion_buena_puntua_alto(self):
        m = M.revisar_parte(BUENA, FUENTES, rango_palabras=(100, 3000))
        self.assertEqual(m["citas_falsas"], 0)
        self.assertEqual(m["enlaces_inventados"], 0)
        self.assertEqual(m["respuestas"], 2)
        self.assertEqual(m["secciones"], 1.0)
        self.assertGreaterEqual(m["objetivo"], 90)

    def test_cita_a_fuente_inexistente_y_enlace_inventado(self):
        texto = BUENA + "\nSegún [7] y [P4], ver https://inventado.example/x y https://es.wikipedia.org/wiki/Teorema_de_Bayes."
        m = M.revisar_parte(texto, FUENTES, rango_palabras=(100, 3000))
        self.assertEqual(m["citas_falsas"], 2)
        self.assertEqual(m["enlaces_inventados"], 1)      # el de Wikipedia sí estaba entre las fuentes
        self.assertLess(m["objetivo"], M.revisar_parte(BUENA, FUENTES, rango_palabras=(100, 3000))["objetivo"])

    def test_indices_de_codigo_no_son_citas(self):
        m = M.revisar_parte(BUENA + "\nEn el arreglo a[9] y x[5] se ve.", FUENTES, rango_palabras=(100, 3000))
        self.assertEqual(m["citas_falsas"], 0)

    def test_bucle_formula_e_idioma(self):
        self.assertEqual(M.revisar_parte(BUENA + ("\\text{ }" * 80), FUENTES, (100, 3000))["bucle"], 1)
        self.assertEqual(M.revisar_parte(BUENA + " $x = 1", FUENTES, (100, 3000))["formula_desbalanceada"], 1)
        ingles = "the of and to is in that for with this are which from " * 150
        self.assertLess(M.revisar_parte(ingles, FUENTES, (100, 3000))["en_español"], 0.7)

    def test_texto_vacio_no_rompe(self):
        m = M.revisar_parte("", FUENTES)
        self.assertEqual(m["palabras"], 0)
        self.assertLess(m["objetivo"], 60)

    def test_ejercicios(self):
        self.assertGreaterEqual(M.revisar_ejercicios(ejercicios_buenos())["objetivo"], 95)
        malo = ejercicios_buenos()
        malo["quiz"][0]["opciones"] = ["a", "a", "b", "c"]
        malo["quiz"][1]["correcta"] = 9
        malo["quiz"][2]["explicacion"] = ""
        r = M.revisar_ejercicios(malo)
        self.assertEqual(r["opciones_mal"], 2)
        self.assertEqual(r["sin_explicacion"], 1)
        self.assertLess(r["objetivo"], 80)
        self.assertEqual(M.revisar_ejercicios("no es un objeto")["objetivo"], 0)

    def test_misma_posicion_de_respuesta(self):
        d = ejercicios_buenos()
        for q in d["quiz"]:
            q["correcta"] = 0
        self.assertEqual(M.revisar_ejercicios(d)["respuesta_siempre_igual"], 1)


class Juez(unittest.TestCase):
    def test_anonimizar_es_reproducible_y_oculta_el_modelo(self):
        items = [("local", "uno"), ("g38-alto", "dos"), ("g38-bajo", "tres")]
        a1, k1 = M.anonimizar(items, "s")
        a2, k2 = M.anonimizar(items, "s")
        self.assertEqual((a1, k1), (a2, k2))
        self.assertEqual(sorted(k1.values()), sorted(v for v, _ in items))
        for i, t in a1:
            self.assertEqual(dict(items)[k1[i]], t)          # la clave devuelve a cada texto su variante
        self.assertNotIn("local", json.dumps([t for _, t in a1]))
        distinto = [M.anonimizar(items, f"s{n}")[1] for n in range(8)]
        self.assertGreater(len({json.dumps(d, sort_keys=True) for d in distinto}), 1)    # otra ronda, otro orden

    def test_mensajes_del_juez_no_nombran_modelos(self):
        anon, _ = M.anonimizar([("local", "texto uno"), ("g38-alto", "texto dos")], "x")
        m = json.dumps(M.mensajes_juez("bayes", anon, FUENTES), ensure_ascii=False)
        self.assertNotIn("gemini", m.lower())
        self.assertNotIn("g38", m)
        self.assertIn("LECCIÓN A", m)


class Registro(unittest.TestCase):
    def fila(self, var, tarea="parte", obj=80, err=None, seg=10.0, costo=0.01):
        return {"tema": "bayes", "variante": var, "tarea": tarea, "texto": "t", "tin": 100, "tout": 200, "seg": seg,
                "error": err, "costo_usd": costo, "revision": {"objetivo": obj, "citas_falsas": 1, "enlaces_inventados": 0}}

    def test_resumen_y_fallos(self):
        res = [self.fila("a", obj=80), self.fila("a", obj=60, seg=20.0), self.fila("b", err="HTTP 503", obj=0)]
        juicios = [{"tema": "bayes", "ronda": 0, "claves": {"A": "a", "B": "b"},
                    "lecciones": [{"id": "A", "exactitud": 4, "profundidad": 4, "claridad": 4, "ejemplos": 4, "fuentes": 4,
                                   "errores": ["x"]}]}]
        r = M.resumen(res, juicios)
        self.assertEqual(r["a"]["objetivo_parte"], 70)
        self.assertEqual(r["a"]["seg_medio"], 15)
        self.assertEqual(r["a"]["juez_global"], 4)
        self.assertEqual(r["a"]["errores_detectados"], 1)
        self.assertEqual(r["b"]["fallos"], 1)
        self.assertIsNone(r["b"]["juez"])            # sin datos no se inventa nada
        self.assertIsNone(r["b"]["objetivo_parte"])

    def test_correr_es_reanudable_y_anota_fallos(self):
        corrida = "t1"
        ctx = {"n": 0}

        def falso(v, msgs, max_tokens, temperatura=0.5, esquema=None):
            ctx["n"] += 1
            if v["clave"] == "g38-bajo":
                return {"texto": "", "tin": 0, "tout": 0, "seg": 1.0, "error": "HTTP 503", "costo_usd": 0.0}
            return {"texto": BUENA, "tin": 10, "tout": 20, "seg": 2.0, "error": None, "costo_usd": 0.001}

        with mock.patch.object(M, "llamar", falso), mock.patch.object(M, "leer_fuentes", lambda t: FUENTES):
            M.correr(corrida, ["bayes"], ["local", "g38-bajo"], tareas=("parte",), pausa=0)
            primera = ctx["n"]
            M.correr(corrida, ["bayes"], ["local", "g38-bajo"], tareas=("parte",), pausa=0)
        self.assertEqual(ctx["n"], primera + 1)       # lo medido no se repite; solo se reintenta el fallo
        res = M.leer_resultados(corrida)
        self.assertEqual(len(res), 2)
        self.assertEqual([r["error"] for r in res if r["variante"] == "g38-bajo"], ["HTTP 503"])
        self.assertIn("| local |", M.informe(corrida))

    def test_un_fallo_se_reintenta_y_el_reintento_reemplaza_al_fallo(self):
        corrida = "t3"
        estado = {"falla": True}

        def falso(v, msgs, max_tokens, temperatura=0.5, esquema=None):
            if estado["falla"]:
                return {"texto": "", "tin": 0, "tout": 0, "seg": 1.0, "error": "HTTP 429", "costo_usd": 0.0}
            return {"texto": BUENA, "tin": 10, "tout": 20, "seg": 2.0, "error": None, "costo_usd": 0.001}

        with mock.patch.object(M, "llamar", falso), mock.patch.object(M, "leer_fuentes", lambda t: FUENTES):
            M.correr(corrida, ["bayes"], ["g38-alto"], tareas=("parte",), pausa=0)
            self.assertEqual([r["error"] for r in M.leer_resultados(corrida)], ["HTTP 429"])
            estado["falla"] = False
            M.correr(corrida, ["bayes"], ["g38-alto"], tareas=("parte",), pausa=0)
        res = M.leer_resultados(corrida)
        self.assertEqual(len(res), 1)                 # el fallo ya no cuenta: manda el último intento
        self.assertIsNone(res[0]["error"])

    def test_ciega_no_revela_el_modelo(self):
        corrida = "t2"
        for var in ("local", "g38-alto", "g38-medio"):
            M.anotar(corrida, self.fila(var) | {"texto": f"leccion de {var}"})
        # la lección lleva el nombre de la variante solo en este montaje: la clave debe estar aparte del archivo
        temas = M.preparar_ciega(corrida, 1)
        self.assertEqual(temas, ["bayes"])
        archivo = (M.carpeta(corrida) / "ciega" / "bayes.md").read_text(encoding="utf-8")
        self.assertIn("## Lección A", archivo)
        clave = json.loads((M.carpeta(corrida) / "clave_ciega.json").read_text(encoding="utf-8"))
        self.assertEqual(sorted(clave["bayes"].values()), ["g38-alto", "g38-medio", "local"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
