#!/usr/bin/env python3
"""Pruebas del Índice y el Reto (`app/indice.py`): el modelo de puntaje, el banco de preguntas, que la respuesta
correcta nunca salga antes de responder, el tiempo, que no se repitan preguntas y que cada perfil vea solo lo suyo.
Biblioteca estándar, sin internet ni IA, con una carpeta de datos temporal.
Uso: python3 pruebas/unidad_indice.py   (sale con código 1 si algo falla)"""
import json
import os
import random
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
import indice as idx  # noqa: E402
from base import ejecutar, fila, filas  # noqa: E402
idx.iniciar()

A, B = "a@prueba", "b@prueba"


def temas_reales(n):
    """Temas del currículo base, de módulos de distintos niveles, para que el banco tenga dificultades variadas."""
    out = []
    for area in cur.areas().values():
        for m in area["modulos"]:
            for k in range(len(m["temas_obj"])):
                out.append(f'{area["id"]}.{m["id"]}.{k}')
    random.Random(1).shuffle(out)
    return out[:n]


def leccion(usuario, tema, preguntas):
    quiz = [{"tipo": "opcion", "pregunta": f"{tema} pregunta {k}", "opciones": ["uno", "dos", "tres", "cuatro"],
             "correcta": 0, "explicacion": f"porque sí {k}"} for k in range(preguntas)]
    quiz.append({"tipo": "abierta", "pregunta": "explica", "explicacion": "x"})                 # no entra
    quiz.append({"tipo": "opcion", "pregunta": "mala", "opciones": ["a", "b"], "correcta": 5})  # correcta fuera de rango
    ejecutar("INSERT OR REPLACE INTO leccion(usuario, tema, contenido, ejercicios, creado) VALUES(?,?,?,?,?)",
             (usuario, tema, "contenido", json.dumps({"quiz": quiz}), time.time()))


class Modelo(unittest.TestCase):
    def test_probabilidad(self):
        self.assertAlmostEqual(idx.p_acierto(100, 100, 4), 0.25 + 0.75 / 2)
        self.assertGreater(idx.p_acierto(140, 100, 4), 0.9)
        self.assertLess(idx.p_acierto(60, 145, 4), 0.27)
        self.assertAlmostEqual(idx.p_acierto(-1e3, 100, 2), 0.5, places=3)   # adivinar entre 2

    def test_acertar_dificil_sube_mas_que_facil(self):
        dificil = idx.calcular([{"dificultad": 145, "opciones": 4, "acierto": 1, "ts": 1}])["indice"]
        facil = idx.calcular([{"dificultad": 85, "opciones": 4, "acierto": 1, "ts": 1}])["indice"]
        self.assertGreater(dificil, facil)
        self.assertGreater(facil, idx.BASE)
        fallo_facil = idx.calcular([{"dificultad": 85, "opciones": 4, "acierto": 0, "ts": 1}])["indice"]
        fallo_dificil = idx.calcular([{"dificultad": 145, "opciones": 4, "acierto": 0, "ts": 1}])["indice"]
        self.assertLess(fallo_facil, fallo_dificil)

    def test_converge_al_nivel_real(self):
        """Una persona simulada de Índice real 120 debe quedar cerca de 120 tras 150 respuestas."""
        rng = random.Random(7)
        rs = []
        for k in range(150):
            dif = rng.choice(list(idx.DIF_NIVEL.values()))
            rs.append({"dificultad": dif, "opciones": 4, "ts": k,
                       "acierto": int(rng.random() < idx.p_acierto(120, dif, 4))})
        x = idx.calcular(rs, ahora=150)
        self.assertLess(abs(x["indice"] - 120), 12, x)
        self.assertFalse(x["provisional"])
        self.assertLess(x["mas_menos"], 10)

    def test_adivinar_no_hunde_el_indice_sin_fin(self):
        """Responder al azar (o peor) deja el Índice en el piso de la escala, no en cifras sin sentido."""
        rs = [{"dificultad": 115, "opciones": 4, "acierto": 0, "ts": k} for k in range(60)]
        self.assertEqual(idx.calcular(rs)["indice"], idx.PISO)
        rs = [{"dificultad": 85, "opciones": 4, "acierto": 1, "ts": k} for k in range(300)]
        self.assertLessEqual(idx.calcular(rs)["indice"], idx.TECHO)   # acertar fáciles acerca al techo sin pasarlo

    def test_no_baja_por_no_entrar_pero_crece_la_incertidumbre(self):
        rs = [{"dificultad": 115, "opciones": 4, "acierto": k % 2, "ts": k} for k in range(40)]
        hoy, luego = idx.calcular(rs, ahora=40), idx.calcular(rs, ahora=40 + 90 * 86400)
        self.assertEqual(hoy["indice"], luego["indice"])
        self.assertGreater(luego["mas_menos"], hoy["mas_menos"])

    def test_niveles(self):
        self.assertEqual(idx.nombre_nivel(100), "Intermedio")
        self.assertEqual(idx.nombre_nivel(123), "Experto")
        self.assertEqual(idx.siguiente_nivel(110), {"nombre": "Experto", "faltan": 13})
        self.assertIsNone(idx.siguiente_nivel(150))

    def test_barajar_conserva_la_respuesta(self):
        c = {"opciones": ["a", "b", "c", "d"], "correcta": 2}
        for s in range(20):
            x = idx.barajar(c, random.Random(s))
            self.assertEqual(x["opciones"][x["correcta"]], "c")


def banco_sintetico(n=600, sesgo=0.7, rng=None):
    """Un banco como el que escribe la IA: la correcta es la más larga el 70 % de las veces."""
    rng = rng or random.Random(5)
    out = []
    for k in range(n):
        largos = [rng.randint(20, 60) for _ in range(4)]
        c = rng.randrange(4)
        if rng.random() < sesgo:     # la IA alarga la correcta (a veces mucho, a veces apenas)
            largos[c] = int(max(l for j, l in enumerate(largos) if j != c) * rng.choice([1.02, 1.05, 1.08, 1.3, 1.6]))
        ops = ["x" * l for l in largos]
        out.append({"item": f"i{k}", "tema": f"t{k % 120}", "area": f"a{k % 5}", "dificultad": rng.choice([85, 100, 115]),
                    "opciones": ops, "correcta": c})
    return out


class SinSuerte(unittest.TestCase):
    def test_pista(self):
        self.assertGreater(idx.pista(["corta", "la opción correcta y larguísima", "otra", "más"], 1), 1.1)
        self.assertLess(idx.pista(["aaaa", "bb", "cccc", "dddd"], 1), 1)
        self.assertTrue(idx.corta(["aaaa", "bb", "cccc", "dddd"], 1))
        self.assertFalse(idx.corta(["bb", "bb", "cccc", "dddd"], 1))      # empate: no es «la más corta»

    def test_retos_neutrales_al_largo(self):
        """En 200 retos, «elige siempre la más larga» y «elige siempre la más corta» aciertan ~25 %, como al azar,
        aunque el banco tenga la correcta como la más larga el 70 % de las veces."""
        rng = random.Random(11)
        banco = banco_sintetico(rng=rng)
        larga = corta = total = 0
        for _ in range(200):
            for c in idx.elegir([dict(x) for x in banco], 100, {}, {}, rng=rng):
                self.assertLessEqual(c["pista"], idx.PISTA_MAX)
                L = [len(o) for o in c["opciones"]]
                m, mi = max(L), min(L)
                larga += (L[c["correcta"]] == m) / L.count(m)
                corta += (L[c["correcta"]] == mi) / L.count(mi)
                total += 1
        self.assertEqual(total, 2000)
        self.assertLess(abs(larga / total - 0.25), 0.05, larga / total)
        self.assertLess(abs(corta / total - 0.25), 0.07, corta / total)

    def test_pista_fuerte_vale_como_entre_dos(self):
        r = {"dificultad": 100, "opciones": 4, "acierto": 1, "ts": 1, "pista": 1.5}
        limpio = idx.calcular([dict(r, pista=0.9)])["indice"]
        con_pista = idx.calcular([r])["indice"]
        self.assertLess(con_pista, limpio)
        self.assertEqual(idx.azar(r), idx.AZAR_PISTA)

    def test_no_se_vale_lo_mismo_que_adivinar(self):
        """Sin saber nada, decir «no sé» y adivinar valen igual en promedio: decir la verdad no cuesta ni regala."""
        base = {"dificultad": 115, "opciones": 4, "ts": 1, "pista": 0.9}
        acierto = idx.calcular([dict(base, acierto=1)])["indice"] - idx.BASE
        fallo = idx.calcular([dict(base, acierto=0)])["indice"] - idx.BASE
        nose = idx.calcular([dict(base, acierto=0, seguridad="nose")])["indice"] - idx.BASE
        g = 0.25
        self.assertAlmostEqual(nose, g * acierto + (1 - g) * fallo, places=0)

    def test_decir_no_se_en_las_dificiles_no_protege_el_puntaje(self):
        """Estrategia tramposa: responder solo las fáciles y decir «no sé» en el resto. Con el mismo conocimiento,
        termina igual o más abajo que quien responde todo lo que medio sabe."""
        def simular(estrategia, semilla):
            rng = random.Random(semilla)
            rs = []
            for k in range(150):
                dif = rng.choice([85, 100, 115, 130, 145])
                p_real = idx.p_acierto(110, dif, 4)
                if estrategia == "tramposa" and dif > 110:
                    rs.append({"dificultad": dif, "opciones": 4, "ts": k, "acierto": 0, "seguridad": "nose", "pista": 0.9})
                else:
                    rs.append({"dificultad": dif, "opciones": 4, "ts": k, "acierto": int(rng.random() < p_real), "pista": 0.9})
            return idx.calcular(rs, ahora=150)["indice"]
        honesta = sum(simular("honesta", s_) for s_ in range(40)) / 40
        tramposa = sum(simular("tramposa", s_) for s_ in range(40)) / 40
        self.assertLessEqual(tramposa, honesta + 1, (honesta, tramposa))

    def test_calibracion(self):
        rs = [{"acierto": 1, "seguridad": "se"}, {"acierto": 0, "seguridad": "se"}, {"acierto": 1, "seguridad": "creo"},
              {"acierto": 0, "seguridad": "nose"}, {"acierto": 1, "seguridad": None}]
        c = idx.calibracion(rs)
        self.assertEqual((c["se"]["n"], c["se"]["pct"], c["falsa_seguridad"]), (2, 0.5, 1))
        self.assertEqual(c["nose"]["n"], 1)


class Reto(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temas = temas_reales(8)
        for t in cls.temas:
            leccion(A, t, 4)
        leccion(B, cls.temas[0], 2)     # B casi no tiene lecciones

    def setUp(self):
        ejecutar("DELETE FROM reto")
        ejecutar("DELETE FROM reto_respuesta")

    def test_banco_solo_valido_y_propio(self):
        b = idx.banco(A)
        self.assertEqual(len(b), 32)
        self.assertTrue(all(c["dificultad"] in idx.DIF_NIVEL.values() for c in b))
        self.assertEqual(len(idx.banco(B)), 2)

    def test_banco_corto_no_abre_reto(self):
        r = idx.nuevo(B)
        self.assertEqual(r["error"], "banco_corto")

    def test_la_correcta_nunca_sale_antes_de_responder(self):
        r = idx.nuevo(A)
        txt = json.dumps(r)
        self.assertNotIn("correcta", txt)
        self.assertNotIn("porque sí", txt)
        self.assertNotIn("correcta", json.dumps(idx.actual(A, r["id"])))

    def test_flujo_completo_tarjetas_y_cierre(self):
        r = idx.nuevo(A, rng=random.Random(3))
        self.assertEqual(r["total"], idx.PREGUNTAS_RETO)
        temas = set()
        while True:
            items = json.loads(fila("SELECT items FROM reto WHERE id=?", (r["id"],))["items"])
            c = items[r["i"]]
            temas.add(c["tema"])
            elegida = c["correcta"] if r["i"] % 2 == 0 else (c["correcta"] + 1) % 4
            res = idx.responder(A, r["id"], r["i"], elegida)
            self.assertEqual(res["acierto"], r["i"] % 2 == 0)
            if "fin" in res:
                break
            self.assertNotIn("correcta", json.dumps(res["siguiente"]))
            r = res["siguiente"]
        fin = res["fin"]
        self.assertEqual((fin["aciertos"], fin["total"]), (5, 10))
        self.assertEqual(len(fin["fallos"]), 5)
        self.assertLessEqual(len(fin["debiles"]), 3)
        self.assertEqual(len(temas), 8, "debe variar los temas antes de repetir uno")
        self.assertIn("error", idx.responder(A, r["id"], 9, 0))     # ya terminó

    def test_doble_respuesta_y_tiempo(self):
        r = idx.nuevo(A)
        ahora = time.time()
        items = json.loads(fila("SELECT items FROM reto WHERE id=?", (r["id"],))["items"])
        tarde = idx.responder(A, r["id"], 0, items[0]["correcta"], ahora=ahora + idx.SEGUNDOS + idx.GRACIA + 5)
        self.assertFalse(tarde["acierto"])        # correcta pero fuera de tiempo: no cuenta
        self.assertFalse(tarde["a_tiempo"])
        self.assertIn("error", idx.responder(A, r["id"], 0, 0))      # la misma otra vez
        self.assertFalse(idx.responder(A, r["id"], 1, None)["acierto"])   # se acabó el tiempo en el navegador

    def test_no_se_y_falsa_seguridad(self):
        r = idx.nuevo(A)
        items = json.loads(fila("SELECT items FROM reto WHERE id=?", (r["id"],))["items"])
        x = idx.responder(A, r["id"], 0, items[0]["correcta"], seguridad="nose")
        self.assertFalse(x["acierto"])                    # con «no sé» no se elige: no hay acierto de suerte
        self.assertEqual(x["seguridad"], "nose")
        self.assertIn("correcta", x)                      # pero se muestra la respuesta para aprenderla
        fila_ = fila("SELECT elegida, seguridad, pista FROM reto_respuesta WHERE reto=? ORDER BY id", (r["id"],))
        self.assertEqual((fila_["elegida"], fila_["seguridad"]), (None, "nose"))
        self.assertIsNotNone(fila_["pista"])
        mala = (items[1]["correcta"] + 1) % len(items[1]["opciones"])
        y = idx.responder(A, r["id"], 1, mala, seguridad="se")
        self.assertTrue(y["falsa_seguridad"])
        self.assertEqual(idx.resumen(A)["calibracion"]["falsa_seguridad"], 1)

    def test_retoma_el_reto_abierto(self):
        r1 = idx.nuevo(A)
        idx.responder(A, r1["id"], 0, 0)
        r2 = idx.nuevo(A)
        self.assertEqual((r2["id"], r2["i"]), (r1["id"], 1))

    def test_no_repite_preguntas_recientes(self):
        vistos = set()
        for _ in range(3):
            r = idx.nuevo(A)
            while True:
                items = json.loads(fila("SELECT items FROM reto WHERE id=?", (r["id"],))["items"])
                vistos_ahora = items[r["i"]]["item"]
                self.assertNotIn(vistos_ahora, vistos)
                vistos.add(vistos_ahora)
                res = idx.responder(A, r["id"], r["i"], 0)
                if "fin" in res:
                    break
                r = res["siguiente"]
        self.assertEqual(len(vistos), 30)

    def test_perfiles_independientes(self):
        r = idx.nuevo(A)
        self.assertEqual(idx.actual(B, r["id"]), {"error": "reto desconocido"})
        self.assertEqual(idx.responder(B, r["id"], 0, 0), {"error": "reto desconocido"})
        idx.responder(A, r["id"], 0, 0)
        self.assertEqual(idx.resumen(B)["global"]["n"], 0)
        self.assertIsNone(idx.resumen(B)["abierto"])
        self.assertEqual(idx.resumen(A)["global"]["n"], 1)

    def test_resumen(self):
        x = idx.resumen(A)
        self.assertEqual(x["global"]["indice"], idx.BASE)
        self.assertTrue(x["global"]["provisional"])
        self.assertEqual(x["banco"]["total"], 32)


class PruebaNivelSinSuerte(unittest.TestCase):
    """La prueba de nivel marca temas como dominados: un acierto adivinando o con la correcta delatada por su largo
    no puede contar como evidencia."""

    @classmethod
    def setUpClass(cls):
        import servidor
        cls.sv = servidor
        cls.ref = next(f'{a["id"]}.{m["id"]}' for a in cur.areas().values() for m in a["modulos"] if len(m["temas_obj"]) >= 3)

    def prueba(self, respuestas):
        """respuestas: lista por tema de [(acierta, conf, delatada), (…)] — 2 preguntas por tema."""
        pregs, resp = [], {}
        limpia = ["Opción uno bien", "Opción dos bien", "Opción tres ok", "Opción cuatro x"]
        delat = ["Esta es la opción correcta, larga y llena de matices", "Corta", "Breve", "Otra"]
        for t, lista in enumerate(respuestas):
            for acierta, conf, delatada in lista:
                i = len(pregs)
                pregs.append({"tema": t, "pregunta": f"p{i}", "opciones": delat if delatada else limpia, "correcta": 0, "explicacion": ""})
                resp[str(i)] = {"j": 0 if acierta else 1, "ok": acierta, "tema": t, "conf": conf}
        datos = {"preguntas": pregs, "temas": [], "aprobar": 0.95}
        ejecutar("DELETE FROM kv WHERE k LIKE ?", (f"prueba_temas:{A}:%",))
        ejecutar("DELETE FROM avance WHERE usuario=?", (A,))
        c = ejecutar("INSERT INTO prueba_nivel(usuario, ref, datos, respuestas, estado, creada) VALUES(?,?,?,?, 'lista', ?)",
                     (A, self.ref, json.dumps(datos), json.dumps(resp), time.time()))
        return self.sv.r_prueba_res(A, {}, {"id": c.lastrowid}, None)

    def test_tema_con_aciertos_delatados_no_queda_sabido(self):
        r = self.prueba([[(True, "seguro", True), (True, "seguro", True)],      # 2/2 pero las dos con pista
                         [(True, "seguro", False), (True, "dudo", False)],     # 2/2 firmes
                         [(True, "adivino", False), (True, "seguro", False)]])  # una adivinada
        self.assertEqual([p["id"].rsplit(".", 1)[1] for p in r["pasados"]], ["1"])
        self.assertFalse(r["aprobado"])
        self.assertEqual((r["firmes"], r["con_pista"], r["adivinadas"]), (3, 2, 1))

    def test_modulo_se_aprueba_con_aciertos_firmes(self):
        r = self.prueba([[(True, "seguro", False), (True, "seguro", False)]] * 3)
        self.assertTrue(r["aprobado"])
        r = self.prueba([[(True, "seguro", True), (True, "seguro", True)]] * 3)   # todo acertado, pero todo con pista
        self.assertFalse(r["aprobado"])


if __name__ == "__main__":
    r = unittest.main(exit=False, verbosity=1).result
    sys.exit(0 if r.wasSuccessful() else 1)
