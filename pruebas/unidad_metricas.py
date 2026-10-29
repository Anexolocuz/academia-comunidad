"""Pruebas de la fase F1 (eventos y métricas). Aparte de `unidad.py` para no tocar el mismo archivo que otras ventanas:
`python3 pruebas/unidad_metricas.py`. Usan una carpeta temporal y datos inventados."""
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
import eventos  # noqa: E402
import metricas  # noqa: E402
from base import ejecutar, fila, filas, kv_get  # noqa: E402

metricas.init()
A, B = "ana@prueba", "beto@prueba"
DIA = 86400
AHORA = 1_800_000_000.0     # momento fijo; las pruebas pasan `ahora` y no dependen del reloj


def act(u, tipo, tema=None, area=None, valor=None, detalle=None, t=AHORA):
    import json
    ejecutar("INSERT INTO actividad(usuario,tipo,tema,area,valor,detalle,fecha) VALUES(?,?,?,?,?,?,?)",
             (u, tipo, tema, area, valor, json.dumps(detalle) if detalle else None, t))


def tarjeta(u, tema="mat.alg.0", **kw):
    cols = dict(usuario=u, tema=tema, area="mat", frente="f", reverso="r", estabilidad=10.0, dificultad=5.0, vence=AHORA - DIA,
                ultimo=AHORA - 20 * DIA, repasos=3, fallos=0, suspendida=0, creada=AHORA - 30 * DIA)
    cols.update(kw)
    return ejecutar(f"INSERT INTO tarjeta({','.join(cols)}) VALUES({','.join('?' * len(cols))})", tuple(cols.values())).lastrowid


def repaso(u, tid, nota, dias, t, segundos=10.0):
    ejecutar("INSERT INTO repaso(usuario,tarjeta,nota,fecha,segundos,retenibilidad,dias,origen) VALUES(?,?,?,?,?,?,?,?)",
             (u, tid, nota, t, segundos, 0.9, dias, "repaso"))


def m(u, id_, ahora=AHORA):
    return next(x for x in metricas.calcular(u, ahora) if x["id"] == id_)


def limpiar():
    for t in ("actividad", "repaso", "tarjeta", "lectura", "avance", "evento", "reexplicacion", "parte_estado", "metrica_ajuste",
              "metrica_valor", "entrega", "objetivo", "leccion", "verificacion", "trabajo_hecho"):
        ejecutar(f"DELETE FROM {t}")
    ejecutar("DELETE FROM kv WHERE k LIKE 'evento_marca:%' OR k LIKE 'metricas_off:%'")


class Catalogo(unittest.TestCase):
    def test_hay_al_menos_40_metricas_y_cada_una_se_explica(self):
        self.assertGreaterEqual(len(metricas.CATALOGO), 40)
        for k, x in metricas.CATALOGO.items():
            self.assertIn(x["origen"], ("D", "I"), k)
            self.assertIn(x["familia"], metricas.FAMILIAS, k)
            for campo in ("nombre", "formula", "ventana", "decide"):
                self.assertTrue(len(x[campo]) >= 3, f"{k}: falta {campo}")   # «mes» es una ventana válida
            self.assertGreaterEqual(len(x["formula"]), 25, f"{k}: la fórmula no explica nada")
            self.assertGreaterEqual(x["n_min"], 1, k)

    def test_todas_se_calculan_sin_error_ni_datos(self):
        limpiar()
        for x in metricas.calcular(A, AHORA):
            self.assertIsNone(x["error"], x["id"])
            self.assertEqual(x["confianza"], "sin datos", x["id"])
            self.assertFalse(x["usable"], x["id"])

    def test_confianza(self):
        self.assertEqual([metricas.confianza(n, 5) for n in (0, 1, 4, 5, 14, 15, 99)],
                         ["sin datos", "baja", "baja", "media", "media", "alta", "alta"])


class SincronizarEventos(unittest.TestCase):
    def setUp(self):
        limpiar()

    def test_proyecta_sin_duplicar_y_marca_directos(self):
        t = tarjeta(A)
        repaso(A, t, 3, 7, AHORA - 100)
        act(A, "repaso", "mat.alg.0", valor=3, t=AHORA - 100)          # el repaso se registra también en actividad: no se cuenta dos veces
        act(A, "tiempo", valor=30, t=AHORA - 50)
        act(A, "quiz", "mat.alg.0", "mat", 0.8, t=AHORA - 40)
        ejecutar("INSERT INTO reexplicacion(usuario,tema,parte,estilo,duda,texto,fecha) VALUES(?,?,?,?,?,?,?)", (A, "mat.alg.0", 1, "ejemplo", "?", "x", AHORA - 30))
        n1 = eventos.sincronizar()
        tipos = {r["tipo"]: r for r in filas("SELECT tipo, directo, COUNT(*) n FROM evento GROUP BY tipo")}
        self.assertEqual({k: v["n"] for k, v in tipos.items()}, {"repaso": 1, "tiempo": 1, "quiz": 1, "reexplicacion": 1})
        self.assertEqual((tipos["repaso"]["directo"], tipos["quiz"]["directo"], tipos["tiempo"]["directo"]), (1, 1, 0))
        self.assertGreaterEqual(n1, 4)
        eventos.sincronizar(); eventos.sincronizar()                     # idempotente
        self.assertEqual(fila("SELECT COUNT(*) n FROM evento")["n"], 4)

    def test_incremental_y_sesion_de_lectura_que_crece_es_un_evento(self):
        lectura.guardar(A, {"id": "s1", "tema": "t.1", "area": "t", "metodo": "leccion", "idioma": "es", "segundos": 60, "avance": 0.2,
                            "palabras": 100})
        eventos.sincronizar()
        lectura.guardar(A, {"id": "s1", "tema": "t.1", "area": "t", "metodo": "leccion", "idioma": "es", "segundos": 300, "avance": 0.9,
                            "palabras": 600})
        act(A, "tiempo", valor=10, t=time.time())
        eventos.sincronizar()
        ls = eventos.de_persona(A, "lectura")
        self.assertEqual(len(ls), 1)
        self.assertEqual((ls[0]["valor"], ls[0]["contexto"]["avance"]), (300, 0.9))
        self.assertEqual(fila("SELECT COUNT(*) n FROM evento WHERE tipo='tiempo'")["n"], 1)

    def test_perfiles_independientes(self):
        act(A, "tiempo", valor=60, t=AHORA - 10)
        act(B, "tiempo", valor=90, t=AHORA - 10)
        eventos.sincronizar()
        self.assertEqual([e["valor"] for e in eventos.de_persona(A)], [60])
        self.assertEqual([e["valor"] for e in eventos.de_persona(B)], [90])
        self.assertEqual(eventos.resumen(A)["total"], 1)

    def test_eventos_de_la_interfaz_solo_lista_blanca_y_acotados(self):
        n = eventos.registrar_cliente(A, [
            {"tipo": "vista", "objeto": "hoy", "valor": 12},
            {"tipo": "navega", "objeto": "tema/x.y.0", "valor": 12, "contexto": {"desde": "hoy", "otro": {"a": 1}}},
            {"tipo": "borrar_todo", "objeto": "x", "valor": 1},                    # tipo no permitido
            {"tipo": "vista", "objeto": "x" * 500, "valor": 99999},                 # se recorta
            {"tipo": "vista", "objeto": "hoy", "valor": "no es número"},            # inválido
            "basura"])
        self.assertEqual(n, 3)
        ev = eventos.de_persona(A)
        self.assertEqual(max(e["valor"] for e in ev), 3600)
        self.assertLessEqual(max(len(e["objeto"]) for e in ev), 60)
        self.assertEqual(ev[1]["contexto"], {"desde": "hoy"})                       # los valores anidados no entran
        self.assertEqual(eventos.registrar_cliente(A, [{"tipo": "vista", "objeto": "hoy", "valor": 1}] * 200), 50)   # tope por llamada

    def test_apagar_decision_deja_de_guardar_y_sugerencia_no_se_infla(self):
        eventos.sugerencia(A, "tema/a.b.0", "Tema", AHORA); eventos.sugerencia(A, "tema/a.b.0", "Tema", AHORA + 60)
        self.assertEqual(len(eventos.de_persona(A, "sugerencia")), 1)               # recargar no cuenta dos veces
        metricas.apagar_familia(A, "decision")
        self.assertEqual(eventos.registrar_cliente(A, [{"tipo": "vista", "objeto": "hoy", "valor": 5}]), 0)
        self.assertEqual(eventos.sugerencia(A, "repasar", "x", AHORA + 4 * 3600), 0)
        self.assertEqual(eventos.registrar_cliente(B, [{"tipo": "vista", "objeto": "hoy", "valor": 5}]), 1)   # otro perfil no se ve afectado


class Valores(unittest.TestCase):
    def setUp(self):
        limpiar()

    def test_retencion_lapsos_y_confianza(self):
        t = tarjeta(A)
        for k in range(10):                     # 10 repasos a ~7 días: 8 bien, 2 mal; el resto lejos de esa ventana
            repaso(A, t, 1 if k < 2 else 3, 7, AHORA - k * 3600)
        repaso(A, t, 3, 1, AHORA - 10)
        eventos.sincronizar()
        r7 = m(A, "retencion_7d")
        self.assertEqual((r7["valor"], r7["n"], r7["confianza"], r7["usable"]), (0.8, 10, "media", True))
        self.assertEqual(m(A, "retencion_1d")["confianza"], "baja")                 # 1 sola muestra
        self.assertFalse(m(A, "retencion_1d")["usable"])
        self.assertEqual(m(A, "tasa_lapsos")["valor"], round(2 / 11, 3))

    def test_habito_dias_racha_y_cobertura(self):
        base_dia = AHORA - 4 * 3600 + 4 * 3600      # mediodía lógico
        for k in (0, 1, 2, 5, 6):                   # activo hoy, ayer, antes de ayer, y hace 5 y 6 días
            act(A, "tiempo", valor=600, t=AHORA - k * DIA - 100)
        eventos.sincronizar()
        self.assertEqual(m(A, "dias_activos_7d")["valor"], 5)
        self.assertEqual(m(A, "racha_actual")["valor"], 3)
        self.assertEqual(m(A, "racha_maxima")["valor"], 3)
        self.assertEqual(m(A, "minutos_7d")["valor"], 50.0)
        c = m(A, "dias_activos_7d")
        self.assertEqual(c["n"], 7)                                              # muestra = días de historia, no número de eventos
        self.assertEqual(m(A, "minutos_por_dia_activo")["valor"], 10.0)

    def test_poca_historia_no_infla_la_confianza(self):
        for k in range(40):                         # 40 eventos el mismo día: un solo día de historia
            act(A, "tiempo", valor=30, t=AHORA - k * 60)
        eventos.sincronizar()
        d = m(A, "dias_activos_30d")
        self.assertEqual((d["valor"], d["n"], d["confianza"], d["usable"]), (1, 1, "baja", False))

    def test_dominio_y_minutos_por_tema_unica_formula(self):
        for tema, est in (("a.1", "dominado"), ("a.2", "probado"), ("a.3", "visto")):
            ejecutar("INSERT INTO avance(usuario,tema,estado) VALUES(?,?,?)", (A, tema, est))
        act(A, "tiempo", valor=3600, t=AHORA - 10)
        eventos.sincronizar()
        self.assertEqual(m(A, "temas_dominados")["valor"], 2)
        self.assertEqual(m(A, "temas_expuestos")["valor"], 1)
        self.assertEqual(m(A, "minutos_por_tema_dominado")["valor"], 30)         # 60 min / 2 temas

    def test_tarjetas_olvido_y_errores(self):
        tarjeta(A, fallos=3, ultimo=AHORA - 40 * DIA)    # 40 días con estabilidad 10: retención ≈ 72 %, por debajo del 80 %
        tarjeta(A, ultimo=AHORA - 1 * DIA, estabilidad=50.0, vence=AHORA + 10 * DIA)
        self.assertEqual(m(A, "errores_repetidos")["valor"], 1)
        self.assertEqual(m(A, "tarjetas_vencidas")["valor"], 1)
        self.assertEqual(m(A, "olvido_estimado")["valor"], 0.5)                  # la de 40 días baja de 80 %; la reciente no

    def test_lectura_abandono_y_relecturas(self):
        for i, av in enumerate((0.1, 0.2, 0.95, 0.95, 0.3)):
            lectura.guardar(A, {"id": f"s{i}", "tema": "t.1" if i < 2 else f"t.{i}", "area": "t", "metodo": "leccion", "idioma": "es",
                                "segundos": 100, "avance": av, "palabras": 500 + i, "audio": 1 if i == 0 else 0})
        ejecutar("UPDATE lectura SET fin=?", (AHORA - 100,))
        eventos.sincronizar()
        self.assertEqual(m(A, "abandono_lectura")["valor"], 0.6)
        self.assertEqual(m(A, "lectura_completa")["valor"], 0.4)
        self.assertEqual(m(A, "uso_audio")["valor"], 0.2)
        self.assertEqual(m(A, "relecturas")["valor"], round(1 / 4, 3))            # t.1 tiene 2 sesiones de 4 temas
        self.assertEqual(m(A, "metodo_mas_tiempo")["valor"], "leccion")

    def test_decision_acuerdo_con_la_sugerencia(self):
        for k, (sug, fue) in enumerate((("tema/a.0", "tema/a.0"), ("repasar", "repasar"), ("tema/b.0", "objetivos"),
                                        ("pulso", "repasar"), ("tema/c.0", "tema/c.0"))):
            t0 = AHORA - 10 * DIA + k * 3600
            eventos._guardar([(A, t0, "hoy", "sugerencia", sug, None, None, False, f"s{k}"),
                              (A, t0 + 40, "cliente", "navega", fue, 40.0, {"desde": "hoy"}, False, None),
                              (A, t0 + 40, "cliente", "vista", "hoy", 40.0, None, False, None)])
        r = m(A, "acuerdo_sugerencia")
        self.assertEqual((r["valor"], r["n"]), (0.6, 5))
        self.assertEqual(m(A, "tiempo_en_decidir")["valor"], 40.0)
        self.assertEqual(m(A, "sugerencias_14d")["valor"], 5)


class CadaMetrica(unittest.TestCase):
    """Criterio de la fase F1: cada métrica del catálogo tiene prueba. Se siembran datos de TODAS las fuentes y cada una debe dar valor."""
    SIN_FIXTURE = {"gasto_api"}      # depende de la API opcional (nube.py), que se prueba en su propio módulo

    def test_todas_dan_valor_con_datos_de_todas_las_fuentes(self):
        import json
        limpiar()
        for tema, est, fey in (("a.1", "dominado", 0.8), ("a.2", "probado", None), ("a.3", "visto", None)):
            ejecutar("INSERT INTO avance(usuario,tema,estado,feynman,visto) VALUES(?,?,?,?,?)", (A, tema, est, fey, AHORA - DIA))
        t1 = tarjeta(A, fallos=3); t2 = tarjeta(A, estabilidad=30.0, ultimo=AHORA - 3 * DIA)
        for dias, nota in ((1, 3), (7, 3), (7, 1), (30, 3), (90, 3)):
            for k in range(10):
                repaso(A, t1 if k % 2 else t2, nota, dias, AHORA - (k + 1) * 3 * 3600 - dias * 60)
        for k in range(30):
            for sesion in range(2):     # dos bloques por día separados por más de 30 min
                act(A, "tiempo", valor=600, t=AHORA - k * DIA - sesion * 7200 - 100)
        for k in range(4):          # pruebas diferidas: 3 aprobadas y una no
            act(A, "diferida", f"a.{k % 3 + 1}", "a", [1.0, 0.75, 0.9, 0.5][k], {"etapa": 1, "aprobada": k < 3}, t=AHORA - k * 900)
        for k in range(6):          # tutor examinador: 4 buenas sin pistas, una con pistas y una floja
            act(A, "examen", f"a.{k % 3 + 1}", "a", [0.9, 1.0, 0.8, 0.85, 0.9, 0.3][k], {"ayudas": 1 if k == 4 else 0, "repreguntas": 1}, t=AHORA - k * 800)
        for k in range(4):          # práctica con código: 3 resueltos sin ver la solución y uno con la solución a la vista
            act(A, "codigo", f"a.{k % 3 + 1}", "a", 1.0, {"ejercicio": k, "vio_solucion": k == 3}, t=AHORA - k * 700)
        for k in range(10):         # confianza declarada: «seguro» (0,9) con 7 aciertos de 10
            act(A, "calibracion", f"a.{k % 3 + 1}", "a", 1.0 if k < 7 else 0.0, {"p": 0.9}, t=AHORA - k * 600)
        for tipo, v in (("quiz", 0.8), ("prueba", 0.7), ("practica", 0.9), ("apunte", None)):
            for k in range(6):
                act(A, tipo, f"a.{k % 3 + 1}", "a", v, t=AHORA - k * 600)
        for i in range(8):
            lectura.guardar(A, {"id": f"r{i}", "tema": f"a.{i % 4 + 1}", "area": "a", "metodo": "leccion" if i % 2 else "noticias",
                                "idioma": "es", "segundos": 400, "avance": 0.95 if i % 2 else 0.2, "palabras": 800, "audio": i % 3 == 0,
                                "cats": {"es": {"seg": 400, "palabras": 800, "formulas": 0}}})
        ejecutar("UPDATE lectura SET fin=?, inicio=?", (AHORA - 200, AHORA - 600))
        for k, est in enumerate(("sabido", "no", "dudoso", "no", "sabido", "sabido")):
            ejecutar("INSERT INTO parte_estado(usuario,tema,parte,estado,segundos,fecha) VALUES(?,?,?,?,?,?)", (A, "a.1", k, est, 30, AHORA - 100 - k))
        ejecutar("INSERT INTO reexplicacion(usuario,tema,parte,estilo,duda,texto,fecha) VALUES(?,?,?,?,?,?,?)", (A, "a.1", 1, "x", "?", "t", AHORA - 99))
        for k in range(4):
            ejecutar("INSERT INTO entrega(usuario,tema,area,ejercicio,version,tipo,texto,puntaje,creado,corregido) VALUES(?,?,?,?,?,?,?,?,?,?)",
                     (A, "a.1", "a", f"e{k}", 1, "texto", "x", 70 + k, AHORA - 500, AHORA - 400))
        ejecutar("INSERT INTO objetivo(usuario,titulo,descripcion,plan,estado,creado) VALUES(?,?,?,?,?,?)", (A, "meta", "", "{}", "activo", AHORA - DIA))
        ejecutar("INSERT INTO leccion(usuario,tema,contenido,completa) VALUES(?,?,?,?)", (A, "a.1", "x", 1))
        ejecutar("INSERT INTO verificacion(usuario,clave,titulo,datos,creada) VALUES(?,?,?,?,?)", (A, "tema:a.1", "t", "{}", AHORA - 10))
        ejecutar("INSERT INTO trabajo_hecho(id,usuario,tipo,etiqueta,estado,terminado) VALUES(?,?,?,?,?,?)", ("j1", A, "leccion", "x", "listo", AHORA - 50))
        # lo que ve la interfaz y «Hoy»
        for k in range(8):
            t0 = AHORA - 5 * DIA + k * 3600
            eventos._guardar([(A, t0, "hoy", "sugerencia", "repasar", None, None, False, f"sg{k}"),
                              (A, t0 + 20, "cliente", "navega", "repasar" if k % 2 else "objetivos", 20.0, {"desde": "hoy"}, False, None),
                              (A, t0 + 20, "cliente", "vista", "hoy", 20.0, None, False, None)])
        eventos.sincronizar()
        # la velocidad de lectura en español necesita 5 min leídos; las 8 sesiones de 400 s ya los dan
        rs = {x["id"]: x for x in metricas.calcular(A, AHORA)}
        self.assertEqual(len(rs), len(metricas.CATALOGO))
        sin_valor = [k for k, x in rs.items() if x["valor"] is None and k not in self.SIN_FIXTURE]
        self.assertEqual(sin_valor, [], "métricas sin valor con datos de todas las fuentes")
        con_error = [k for k, x in rs.items() if x["error"]]
        self.assertEqual(con_error, [])
        sin_confianza = [k for k, x in rs.items() if x["confianza"] in ("sin datos",) and k not in self.SIN_FIXTURE]
        self.assertEqual(sin_confianza, [])


class Ajustes(unittest.TestCase):
    def setUp(self):
        limpiar()

    def test_ignorar_y_apagar_quitan_el_poder_de_decidir(self):
        for k in range(30):
            act(A, "quiz", "a.1", "a", 0.9, t=AHORA - k * 60)
        eventos.sincronizar()
        self.assertTrue(m(A, "acierto_quiz")["usable"])
        metricas.ajustar(A, "acierto_quiz", "mal", "no fue así", AHORA)
        x = m(A, "acierto_quiz")
        self.assertFalse(x["usable"])
        self.assertEqual(x["ajuste"]["estado"], "mal")
        self.assertTrue(m(B, "acierto_quiz")["ajuste"] is None)                  # el ajuste es de cada persona
        metricas.ajustar(A, "acierto_quiz", "ok")
        self.assertTrue(m(A, "acierto_quiz")["usable"])
        metricas.apagar_familia(A, "memoria")
        self.assertFalse(m(A, "acierto_quiz")["usable"])
        self.assertFalse(m(B, "acierto_quiz")["familia_apagada"])
        metricas.apagar_familia(A, "memoria", False)
        self.assertTrue(m(A, "acierto_quiz")["usable"])
        with self.assertRaises(ValueError):
            metricas.ajustar(A, "no_existe", "mal")
        with self.assertRaises(ValueError):
            metricas.ajustar(A, "acierto_quiz", "borrar")
        with self.assertRaises(ValueError):
            metricas.apagar_familia(A, "no_existe")

    def test_foto_diaria_historial_y_aislamiento(self):
        act(A, "tiempo", valor=600, t=AHORA - 10)
        eventos.sincronizar()
        n = metricas.guardar_foto(A, AHORA)
        self.assertGreater(n, 5)
        self.assertEqual(metricas.guardar_foto(A, AHORA + 60), n)                # mismo día: se reemplaza, no se duplica
        self.assertEqual(fila("SELECT COUNT(*) n FROM metrica_valor WHERE usuario=? AND id='minutos_7d'", (A,))["n"], 1)
        metricas.guardar_foto(A, AHORA + DIA)
        self.assertEqual(len(metricas.tendencia(A, "minutos_7d")), 2)
        self.assertEqual(metricas.tendencia(B, "minutos_7d"), [])

    def test_una_metrica_que_falla_no_tira_a_las_demas(self):
        metricas.CATALOGO["_rota"] = dict(metricas.CATALOGO["minutos_7d"], id="_rota", fn=lambda c: 1 / 0)
        try:
            rs = metricas.calcular(A, AHORA)
            rota = next(x for x in rs if x["id"] == "_rota")
            self.assertIn("ZeroDivisionError", rota["error"])
            self.assertFalse(rota["usable"])
            self.assertGreater(len(rs), 40)
        finally:
            del metricas.CATALOGO["_rota"]


class Calibracion(unittest.TestCase):
    """Confianza declarada («seguro», «dudo», «adivino») antes de ver el resultado: Brier y sobreconfianza."""

    def _resp(self, u, p, acierto, n=1, t=AHORA - DIA):
        for _ in range(n):
            act(u, "calibracion", "mat.alg.0", "mat", 1.0 if acierto else 0.0, {"p": p}, t)

    def test_con_pocas_respuestas_se_muestra_pero_no_decide(self):
        limpiar()
        self._resp(A, 0.9, True, 4)
        eventos.sincronizar()
        r = m(A, "calibracion_brier")
        self.assertEqual(r["n"], 4)
        self.assertAlmostEqual(r["valor"], 0.01, places=3)
        self.assertFalse(r["usable"])

    def test_con_muestra_suficiente_decide_y_distingue_sobreconfianza(self):
        limpiar()
        self._resp(A, 0.9, True, 6)
        self._resp(A, 0.9, False, 4)        # «seguro» pero acierta 6 de 10
        eventos.sincronizar()
        b, s = m(A, "calibracion_brier"), m(A, "sobreconfianza")
        self.assertTrue(b["usable"])
        self.assertAlmostEqual(b["valor"], round((6 * 0.01 + 4 * 0.81) / 10, 3), places=3)
        self.assertAlmostEqual(s["valor"], 0.3, places=3)        # 0,9 de seguridad − 0,6 de acierto
        self.assertEqual(m(B, "calibracion_brier")["confianza"], "sin datos")   # nada de otra persona

    def test_es_una_metrica_directa(self):
        limpiar()
        self._resp(A, 0.6, True)
        eventos.sincronizar()
        self.assertEqual(fila("SELECT directo FROM evento WHERE usuario=? AND tipo='calibracion'", (A,))["directo"], 1)


if __name__ == "__main__":
    r = unittest.main(exit=False, verbosity=2).result
    sys.exit(0 if r.wasSuccessful() else 1)
