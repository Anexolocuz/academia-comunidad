"""Pruebas de «actualizar comparando» (rutas y lecciones) frente a «forzar» (rehacer todo).
`python3 pruebas/unidad_actualizar.py`. Usan una carpeta de datos temporal y una IA simulada (sin red ni GPU)."""
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
import curriculo as cur  # noqa: E402
import lecciones as lec  # noqa: E402
import revision  # noqa: E402
import verificacion  # noqa: E402,F401  (crea la tabla verificacion, como en el servidor)
from base import ejecutar, fila, kv_get  # noqa: E402

cur.cargar()
U = "persona@prueba"


class Ctx:
    """Contexto de IA simulado: registra las fases y responde en orden lo que se le dé."""
    def __init__(self, respuestas=()):
        self.respuestas, self.llamadas, self.fases = list(respuestas), [], []

    def fase(self, f):
        self.fases.append(f)

    def chat(self, mensajes, **kw):
        self.llamadas.append(mensajes)
        if not self.respuestas:
            raise AssertionError("la IA no debía llamarse otra vez")
        r = self.respuestas.pop(0)
        return r(mensajes) if callable(r) else r


def tema_real():
    for a in cur.areas(U).values():
        if a.get("grupo") != "Idiomas" and not a.get("idioma") and a["modulos"] and a["modulos"][0]["temas_obj"]:
            return a["modulos"][0]["temas_obj"][0]["id"], a["id"]
    raise RuntimeError("sin temas en el currículo")


SIN_CAMBIOS_RUTA = {"resumen": "al día", "temas_nuevos": [], "modulos_nuevos": [], "en_declive": []}


class ComparacionRuta(unittest.TestCase):
    def setUp(self):
        self.tid, self.area = tema_real()
        base.kv_set(f"revision:{U}:{self.area}", None)
        self.orig = revision._evidencia
        self.ev = "MERCADO DE HOY:\n- N1 Competencia A\n- N2 Competencia B"
        revision._evidencia = lambda u, a: self.ev

    def tearDown(self):
        revision._evidencia = self.orig

    def test_misma_evidencia_no_llama_a_la_ia_y_forzar_si(self):
        ctx = Ctx([SIN_CAMBIOS_RUTA])
        r1 = revision.revisar(ctx, U, {}, self.area)
        self.assertEqual(len(ctx.llamadas), 1)
        self.assertTrue(r1["comparacion"]["primera"])
        r2 = revision.revisar(ctx, U, {}, self.area)          # misma evidencia y misma ruta: no hay IA
        self.assertEqual(len(ctx.llamadas), 1)
        self.assertTrue(r2["sin_cambios"])
        reg = kv_get(f"revision:{U}:{self.area}")
        self.assertTrue(reg["comparacion"]["sin_cambios"])
        self.assertEqual(reg["resumen"], "al día")             # lo revisado antes se conserva
        ctx.respuestas.append(SIN_CAMBIOS_RUTA)
        r3 = revision.revisar(ctx, U, {}, self.area, forzar=True)   # ⚡ forzar: revisa todo aunque no haya nada nuevo
        self.assertEqual(len(ctx.llamadas), 2)
        self.assertTrue(r3["comparacion"]["forzada"])

    def test_evidencia_nueva_se_revisa_centrada_en_lo_nuevo(self):
        ctx = Ctx([SIN_CAMBIOS_RUTA, SIN_CAMBIOS_RUTA])
        revision.revisar(ctx, U, {}, self.area)
        self.ev += "\n- N3 Competencia C nueva"
        r = revision.revisar(ctx, U, {}, self.area)
        self.assertEqual(len(ctx.llamadas), 2)
        self.assertEqual(r["comparacion"]["nuevas"], 1)
        prompt = ctx.llamadas[1][-1]["content"]
        self.assertIn("LO NUEVO DESDE LA ÚLTIMA REVISIÓN", prompt)
        self.assertIn("Competencia C nueva", prompt.split("RUTA ACTUAL")[0])

    def test_citas_y_cobertura_que_cambian_solas_no_cuentan_como_nuevo(self):
        self.ev = ("MERCADO DE HOY:\n- N1 Competencia A (técnica, sube; NO la enseña la ruta)\n"
                   "INVESTIGACIÓN RECIENTE de «M»:\n- (2025, review, 12 citas) Un paper\nLíneas: x (madura); y (emergente)")
        ctx = Ctx([SIN_CAMBIOS_RUTA])
        revision.revisar(ctx, U, {}, self.area)
        self.ev = ("MERCADO DE HOY:\n- N1 Competencia A (técnica, sube; módulos: M1, M2)\n"
                   "INVESTIGACIÓN RECIENTE de «M»:\n- (2025, review, 40 citas) Un paper\nLíneas: y (emergente); x (madura)")
        r = revision.revisar(ctx, U, {}, self.area)
        self.assertTrue(r["sin_cambios"])
        self.assertEqual(len(ctx.llamadas), 1)


PARTE1 = "## Parte 1 · Base\n### 🧠 Intuición\nTexto uno con cita [1].\n\n"
PARTE2 = "## Parte 2 · Avance\n### 📘 Desarrollo\nTexto dos con cita [2] y [P1].\n\n"
CIERRE = "## 🧩 Cómo encaja todo\nCierre.\n\n## 📚 Fuentes y lecturas\n- [1] A — https://a.org\n- [2] B — https://b.org\n"
CONTENIDO = "## 🎯 Objetivos\n1. Algo\n\n" + PARTE1 + PARTE2 + CIERRE
FUENTES = [{"titulo": "A", "url": "https://a.org"}, {"titulo": "B", "url": "https://b.org"},
           {"titulo": "Paper viejo", "url": "https://doi.org/10.1/viejo", "tipo": "paper", "n": "P1"}]


class ActualizarLeccion(unittest.TestCase):
    def setUp(self):
        self.tid, _ = tema_real()
        ejecutar("DELETE FROM leccion_anterior WHERE usuario=? AND tema=?", (U, self.tid))
        ejecutar("""INSERT OR REPLACE INTO leccion(usuario,tema,contenido,ejercicios,fuentes,modelo,creado,version,completa,plan)
                    VALUES(?,?,?,?,?,?,?,?,1,NULL)""",
                 (U, self.tid, CONTENIDO, '{"quiz":[1],"tarjetas":[]}', json.dumps(FUENTES), "claude-opus-5-5",
                  time.time() - 5 * 86400, 3))
        self.orig = lec._fuentes_web, lec._papers
        self.web, self.pap = [], []
        lec._fuentes_web = lambda q, vistas, n: list(self.web)
        lec._papers = lambda q, vistas, n: list(self.pap)

    def tearDown(self):
        lec._fuentes_web, lec._papers = self.orig

    def fila(self):
        return fila("SELECT * FROM leccion WHERE usuario=? AND tema=?", (U, self.tid))

    def test_sin_fuentes_nuevas_no_toca_nada_ni_llama_a_la_ia(self):
        self.web = [{"titulo": "A otra vez", "url": "http://www.a.org/", "texto": "x"}]      # misma fuente escrita distinto
        self.pap = [{"titulo": "Paper viejo", "url": "https://openalex.org/W1", "doi": "10.1/viejo"}]
        antes = self.fila()
        r = lec.actualizar_leccion(Ctx(), self.tid, U, {})
        self.assertTrue(r["sin_cambios"])
        d = self.fila()
        self.assertEqual((d["contenido"], d["fuentes"], d["creado"]), (antes["contenido"], antes["fuentes"], antes["creado"]))
        self.assertTrue(lec.comparacion_leccion(U, self.tid)["sin_cambios"])

    def test_la_ia_no_ve_cambios_y_la_leccion_queda_igual(self):
        self.web = [{"titulo": "C", "url": "https://c.org", "texto": "repite lo mismo"}]
        r = lec.actualizar_leccion(Ctx([{"resumen": "nada nuevo", "cambios": []}]), self.tid, U, {})
        self.assertTrue(r["sin_cambios"])
        self.assertEqual(self.fila()["contenido"], CONTENIDO)

    def test_solo_cambia_la_parte_marcada_y_las_citas_viejas_siguen(self):
        self.web = [{"titulo": "C nueva", "url": "https://c.org", "texto": "dato reciente"}]
        self.pap = [{"titulo": "Paper nuevo", "url": "https://openalex.org/W2", "doi": "10.1/nuevo", "autores": "X",
                     "anio": 2026, "revista": "R", "citas": 1, "abierto": None, "resumen": "hallazgo"}]
        nueva_p2 = ("## Parte 2 · Avance\n### 📘 Desarrollo\nTexto dos con cita [2] y [P1]. Dato reciente [3] y "
                    "hallazgo [P2].\n")
        ctx = Ctx([{"resumen": "hay un dato nuevo", "cambios": [{"parte": 2, "que": "agregar dato", "fuentes": [1, 2]}]},
                   nueva_p2])
        r = lec.actualizar_leccion(ctx, self.tid, U, {})
        self.assertFalse(r["sin_cambios"])
        d = self.fila()
        self.assertIn(PARTE1, d["contenido"])                              # la parte 1 intacta
        self.assertIn("Dato reciente [3]", d["contenido"])
        self.assertIn("## 🧩 Cómo encaja todo\nCierre.", d["contenido"])
        self.assertIn("- [3] C nueva — https://c.org", d["contenido"])
        f = json.loads(d["fuentes"])
        webs = [x for x in f if x.get("tipo") != "paper"]
        self.assertEqual([x["url"] for x in webs], ["https://a.org", "https://b.org", "https://c.org"])   # [3] = 3.ª web
        self.assertEqual([x.get("n") for x in f if x.get("tipo") == "paper"], ["P1", "P2"])
        self.assertEqual(d["modelo"], "claude-opus-5-5")                   # el autor no cambia
        self.assertEqual(d["ejercicios"], '{"quiz":[1],"tarjetas":[]}')    # ejercicios conservados
        self.assertEqual(fila("SELECT COUNT(*) n FROM leccion_anterior WHERE usuario=? AND tema=?", (U, self.tid))["n"], 1)
        c = lec.comparacion_leccion(U, self.tid)
        self.assertEqual([p["parte"] for p in c["partes"]], [2])

    def test_reescritura_recortada_se_descarta(self):
        self.web = [{"titulo": "C", "url": "https://c.org", "texto": "dato"}]
        ctx = Ctx([{"resumen": "x", "cambios": [{"parte": 1, "que": "y", "fuentes": [1]}]}, "## Parte 1 · Base\ncorto"])
        r = lec.actualizar_leccion(ctx, self.tid, U, {})
        self.assertTrue(r["sin_cambios"])
        self.assertEqual(self.fila()["contenido"], CONTENIDO)

    def test_importada_con_numeracion_unica(self):
        fuentes = [{"titulo": "Paper", "url": "https://doi.org/10.1/a", "tipo": "paper"}, {"titulo": "Norma", "url": "https://n.org"}]
        contenido = "## 🎯 Objetivos\n1. x\n\n## Parte 1 · Uno\nTexto largo de la parte uno con cita [1] y [2].\n\n## 📚 Fuentes y lecturas\n- [1] Paper\n"
        ejecutar("UPDATE leccion SET contenido=?, fuentes=? WHERE usuario=? AND tema=?",
                 (contenido, json.dumps(fuentes), U, self.tid))
        self.web = [{"titulo": "Web nueva", "url": "https://w.org", "texto": "t"}]
        nueva = "## Parte 1 · Uno\nTexto largo de la parte uno con cita [1] y [2]. Más [3].\n"
        ctx = Ctx([{"resumen": "r", "cambios": [{"parte": 1, "que": "q", "fuentes": [1]}]}, nueva])
        lec.actualizar_leccion(ctx, self.tid, U, {})
        self.assertIn("[3] Web nueva", ctx.llamadas[1][-1]["content"])    # numerada tras las 2 existentes
        self.assertEqual(json.loads(self.fila()["fuentes"])[-1]["url"], "https://w.org")


class ActualizarLeccionControles(ActualizarLeccion):
    """Casos de borde: numeración cuando se rechaza una parte, citas perdidas y fuentes marcadas «agregada»."""
    def test_parte_rechazada_no_deja_huecos_en_la_numeracion(self):
        self.web = [{"titulo": "W1", "url": "https://w1.org", "texto": "a"}, {"titulo": "W2", "url": "https://w2.org", "texto": "b"}]
        p2 = "## Parte 2 · Avance\n### 📘 Desarrollo\nTexto dos con cita [2] y [P1]. Nuevo dato [3].\n"
        ctx = Ctx([{"resumen": "r", "cambios": [{"parte": 1, "que": "a", "fuentes": [1]},
                                                {"parte": 2, "que": "b", "fuentes": [2]}]},
                   "## Parte 1 · Base\nx",          # la 1.ª sale recortada: se rechaza y devuelve su número
                   p2])
        r = lec.actualizar_leccion(ctx, self.tid, U, {})
        self.assertIn("[3] W2", ctx.llamadas[2][-1]["content"])   # W2 toma el 3, que W1 soltó
        self.assertEqual([p["parte"] for p in r["comparacion"]["partes"]], [2])
        webs = [x for x in json.loads(self.fila()["fuentes"]) if x.get("tipo") != "paper"]
        self.assertEqual([x["url"] for x in webs], ["https://a.org", "https://b.org", "https://w2.org"])
        self.assertTrue(webs[-1]["agregada"])

    def test_reescritura_que_pierde_citas_se_descarta(self):
        self.web = [{"titulo": "W", "url": "https://w.org", "texto": "a"}]
        sin_cita = "## Parte 2 · Avance\n### 📘 Desarrollo\nTexto dos sin las citas de antes pero largo [3] y más texto.\n"
        ctx = Ctx([{"resumen": "r", "cambios": [{"parte": 2, "que": "a", "fuentes": [1]}]}, sin_cita])
        self.assertTrue(lec.actualizar_leccion(ctx, self.tid, U, {})["sin_cambios"])
        self.assertEqual(self.fila()["contenido"], CONTENIDO)
        self.assertEqual(fila("SELECT COUNT(*) n FROM leccion_anterior WHERE usuario=? AND tema=?", (U, self.tid))["n"], 0)

    def test_titulos_extra_se_bajan_de_nivel_y_se_marca_para_reverificar(self):
        self.web = [{"titulo": "W", "url": "https://w.org", "texto": "a"}]
        con_h2 = ("## Parte 2 · Avance\n### 📘 Desarrollo\nTexto dos con cita [2] y [P1]. Nuevo [3].\n"
                  "## Un título que no debía\nmás\n")
        ctx = Ctx([{"resumen": "r", "cambios": [{"parte": 2, "que": "a", "fuentes": [1]}]}, con_h2])
        lec.actualizar_leccion(ctx, self.tid, U, {})
        self.assertIn("### Un título que no debía", self.fila()["contenido"])
        self.assertEqual(len(lec._secciones(self.fila()["contenido"])), len(lec._secciones(CONTENIDO)))
        self.assertTrue(lec.actualizada_por_ia_local(U, self.tid) or str(lec.ia.MODELO).startswith(("claude-", "gemini-")))

    def test_recomendaciones_verificadas_excluyen_lo_agregado(self):
        import recomendaciones as reco
        fuentes = FUENTES + [{"titulo": "Nueva", "url": "https://nueva.org", "agregada": {"fecha": 1, "modelo": "gemma"}}]
        ejecutar("UPDATE leccion SET fuentes=? WHERE usuario=? AND tema=?", (json.dumps(fuentes), U, self.tid))
        urls = [f["url"] for f in reco._fuentes_de(U, [self.tid], solo_verificadas=True)]
        self.assertIn("https://a.org", urls)
        self.assertNotIn("https://nueva.org", urls)


class ForzarYComparar(unittest.TestCase):
    def test_forzar_reemplaza_una_comparacion_en_espera(self):
        import ia
        import servidor
        tid, _ = tema_real()
        ia.cola.vaciar(lambda t: True, fallidos=True)
        orig = ia.nuevo
        creados = []

        def nuevo(tipo, fn, prioridad=0, usuario=None, etiqueta=""):
            t = ia.Trabajo(tipo, fn, prioridad, usuario, etiqueta)
            ia.cola.trabajos[t.id] = t
            import heapq
            heapq.heappush(ia.cola._h, (prioridad, t.creado, t))
            creados.append(t)
            return t
        ia.nuevo = nuevo
        try:
            servidor.r_leccion(U, {}, {"tema": tid, "comparar": True}, None)
            self.assertEqual(creados[0].modo, "comparar")
            servidor.r_leccion(U, {}, {"tema": tid, "forzar": True}, None)
            self.assertEqual(len(creados), 2)
            self.assertEqual(creados[1].modo, "forzar")
            self.assertNotIn(creados[0].id, ia.cola.trabajos)
        finally:
            ia.nuevo = orig
            ia.cola.vaciar(lambda t: True, fallidos=True)


if __name__ == "__main__":
    r = unittest.main(exit=False, verbosity=2).result
    sys.exit(0 if r.wasSuccessful() else 1)
