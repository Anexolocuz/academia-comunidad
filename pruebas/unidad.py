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


class Citas(unittest.TestCase):
    def test_quita_citas_a_fuentes_inexistentes(self):
        import lecciones as lc
        txt = "Dato [1] y otro [3], artículo [P1] y [P2]. Índice x[3] y a[1]; rango [1, 2]."
        sal = lc.limpiar_citas(txt, 2, 1)
        self.assertEqual(sal, "Dato [1] y otro , artículo [P1] y . Índice x[3] y a[1]; rango [1, 2].")

    def test_sin_fuentes_quita_todas_las_citas(self):
        import lecciones as lc
        self.assertEqual(lc.limpiar_citas("Algo [1][P1] más.", 0, 0), "Algo  más.")


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


# ------------------------------------------------------------------ API de IA opcional, avisos y modo corto
import http.server  # noqa: E402
import threading  # noqa: E402
import config  # noqa: E402
import nube  # noqa: E402
import avisos  # noqa: E402
import ia  # noqa: E402
import secretos  # noqa: E402


class _Falso(http.server.BaseHTTPRequestHandler):
    """Servicio falso: «estricto» rechaza temperature y max_tokens (como los modelos de razonamiento) y todos
    rechazan json_schema; así se prueba que la Academia se reajusta sola. Guarda lo último que recibió."""
    visto = []

    def log_message(self, *a):
        pass

    def do_POST(self):
        cuerpo = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        _Falso.visto.append({"ruta": self.path, "cab": {k.lower(): v for k, v in self.headers.items()}, "cuerpo": cuerpo})
        if self.path.endswith("/v1/messages"):                      # estilo Anthropic
            return self._sse([{"type": "message_start", "message": {"usage": {"input_tokens": 11}}},
                              {"type": "content_block_delta", "delta": {"text": "hola "}},
                              {"type": "content_block_delta", "delta": {"text": "mundo"}},
                              {"type": "message_delta", "usage": {"output_tokens": 5}}])
        def mal503():
            self.send_response(503); self.end_headers(); self.wfile.write(b'{"error":{"message":"high demand"}}')
        def mal(msg):
            self.send_response(400); self.end_headers(); self.wfile.write(json.dumps({"error": {"message": msg}}).encode())
        if cuerpo["model"] == "limite":
            self.send_response(429); self.end_headers()
            return self.wfile.write(b'{"error":{"code":429,"message":"You exceeded your current quota","status":"RESOURCE_EXHAUSTED"}}')
        if cuerpo["model"] == "mensual":
            self.send_response(429); self.end_headers()
            return self.wfile.write(b'{"error":{"message":"you have reached your monthly usage limit"}}')
        if cuerpo["model"] == "saturado":
            return mal503()
        if "temperature" in cuerpo and cuerpo["model"] == "estricto":
            return mal("Unsupported value: 'temperature' does not support 0.6 with this model")
        if "max_tokens" in cuerpo and cuerpo["model"] == "estricto":
            return mal("Unsupported parameter: 'max_tokens'. Use 'max_completion_tokens' instead.")
        if "response_format" in cuerpo and cuerpo["response_format"]["type"] == "json_schema":
            return mal("response_format json_schema is not supported")
        texto = '{"a": 1}' if "response_format" in cuerpo else "respuesta"
        self._sse([{"choices": [{"delta": {"content": texto}}]}, {"choices": [], "usage": {"prompt_tokens": 100, "completion_tokens": 50}}], fin=True)

    def _sse(self, eventos, fin=False):
        self.send_response(200); self.send_header("Content-Type", "text/event-stream"); self.end_headers()
        for e in eventos:
            self.wfile.write(b"data: " + json.dumps(e).encode() + b"\n\n")
        if fin:
            self.wfile.write(b"data: [DONE]\n\n")


class _Ctx:
    class t:
        texto = ""
        tipo = "leccion"
        usuario = U
        etiqueta = ""
        fase = ""
    def fase(self, x):
        pass


class NubeYAvisos(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Falso)
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()
        cls.url = f"http://127.0.0.1:{cls.srv.server_address[1]}"
        nube.enlazar(lambda u: {"nombre": "Maria Perez", "situacion": "trabajo en un banco", "metas": "ser ingeniera"},
                     lambda: U)

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()

    def setUp(self):
        _Falso.visto.clear()
        nube._enfriar.clear()
        nube._caido.clear()
        nube._mensual.clear()
        nube._esquema_ok.clear()
        base.ejecutar("DELETE FROM kv WHERE k LIKE 'nube%'")
        config.C = config.guardar({"nube_activa": True, "nube_proveedor": "otro", "nube_url": self.url,
                                   "nube_modelo": "normal", "nube_precio_in": 1, "nube_precio_out": 2, "nube_plan_gratuito": False,
                                   "nube_tope_global_usd": 10})
        secretos.guardar("claves_ia", "clave-falsa-uno", "otro")
        nube.guardar_persona(U, {"usar": True, "tope_usd": 5})

    def test_apagada_por_defecto_y_nunca_lo_personal(self):
        base.kv_set(f"nube:{U}", None)
        self.assertIsNone(nube.aplicable("leccion", U)[0])                     # la persona no la activó
        nube.guardar_persona(U, {"usar": True})
        self.assertEqual(nube.aplicable("leccion", U)[0], U)
        for tipo in ("tutor", "apunte", "entrega", "corregir", "aporte", "pronostico", "reporte", "desconocido"):
            self.assertIsNone(nube.aplicable(tipo, U)[0], tipo)
        config.C = config.guardar({"nube_activa": False})
        self.assertIsNone(nube.aplicable("leccion", U)[0])

    def test_por_defecto_solo_lecciones_con_sus_fuentes_y_configurable(self):
        base.kv_set(f"nube:{U}", None)
        nube.guardar_persona(U, {"usar": True})
        self.assertEqual(nube.ajustes_persona(U)["grupos"], ["lecciones"])
        for tipo, et in (("leccion", "x"), ("rapida", "x"), ("reexplicar", "x"), ("ciencia", "x"), ("verificar", "tema:sistemas.redes.1")):
            self.assertEqual(nube.aplicable(tipo, U, et)[0], U, tipo)
        for tipo, et in (("verificar", "texto"), ("noticias", ""), ("a_fondo", "1"), ("objetivo", "x"), ("prueba", "x"), ("tutor", "x")):
            self.assertIsNone(nube.aplicable(tipo, U, et)[0], tipo)
        nube.guardar_persona(U, {"grupos": list(nube.GRUPOS)})                       # «que lo haga todo la API»
        for tipo in ("noticias", "objetivo", "prueba"):
            self.assertEqual(nube.aplicable(tipo, U)[0], U, tipo)
        self.assertIsNone(nube.aplicable("tutor", U)[0])                               # lo personal nunca

    def test_la_clave_no_sale_en_la_configuracion(self):
        pub = json.dumps(nube.config_admin()) + json.dumps(config.C)
        self.assertNotIn("clave-falsa-uno", pub)
        self.assertTrue(nube.config_admin()["tiene_clave"])
        self.assertEqual(oct(secretos.ARCHIVO.stat().st_mode & 0o777), "0o600")

    def test_privacidad_sin_nombre_ni_metas_por_defecto(self):
        m = [{"role": "system", "content": "Eres tutor. " + "[[PERFIL]]Estudiante: Maria Perez. Metas: ser ingeniera[[/PERFIL]]"},
             {"role": "user", "content": "Explica a Maria Perez la recursión"}]
        sal = json.dumps(nube.limpiar(m, U), ensure_ascii=False)
        self.assertNotIn("Maria", sal); self.assertNotIn("ingeniera", sal); self.assertNotIn("PERFIL", sal)
        self.assertIn("anónimo", sal)
        nube.guardar_persona(U, {"enviar_metas": True})
        sal = json.dumps(nube.limpiar(m, U), ensure_ascii=False)
        self.assertIn("ingeniera", sal); self.assertNotIn("Maria", sal); self.assertNotIn("banco" if False else "Perez", sal)
        # la IA local sí recibe el perfil completo, solo sin las marcas
        loc = nube.sin_marcas(m)[0]["content"]
        self.assertIn("Maria Perez", loc); self.assertNotIn("[[", loc)

    def test_openai_compatible_se_reajusta_y_cuenta_el_gasto(self):
        nube.guardar_admin({"modelo": "estricto"})
        ok, r = nube.intentar(_Ctx(), [{"role": "user", "content": "hola"}], 100, 0.6, None, False, 7)
        self.assertTrue(ok); self.assertEqual(r, "respuesta")
        ultimo = _Falso.visto[-1]["cuerpo"]
        self.assertNotIn("temperature", ultimo); self.assertNotIn("max_tokens", ultimo)
        self.assertEqual(ultimo["max_completion_tokens"], 100)
        self.assertEqual(_Falso.visto[-1]["cab"]["authorization"], "Bearer clave-falsa-uno")
        self.assertAlmostEqual(nube.gastado(U), 100 / 1e6 * 1 + 50 / 1e6 * 2, places=6)

    def test_json_schema_rechazado_baja_a_json_object_con_el_esquema_en_el_texto(self):
        esq = {"type": "object", "properties": {"a": {"type": "integer"}}}
        ok, r = nube.intentar(_Ctx(), [{"role": "user", "content": "dame a"}], 100, 0.2, esq, False, None)
        self.assertTrue(ok); self.assertEqual(r, {"a": 1})
        ultimo = _Falso.visto[-1]["cuerpo"]
        self.assertEqual(ultimo["response_format"]["type"], "json_object")
        self.assertIn("properties", json.dumps(ultimo["messages"]))

    def test_anthropic(self):
        nube.guardar_admin({"proveedor": "anthropic", "url": self.url, "modelo": "claude-prueba", "clave": "clave-falsa-anthropic"})
        ok, r = nube.intentar(_Ctx(), [{"role": "system", "content": "sé breve"}, {"role": "user", "content": "hola"}],
                              50, 0.5, None, False, None)
        self.assertEqual((ok, r), (True, "hola mundo"))
        v = _Falso.visto[-1]
        self.assertEqual(v["cab"]["x-api-key"], "clave-falsa-anthropic")
        self.assertEqual(v["cuerpo"]["system"], "sé breve")
        self.assertEqual(v["cuerpo"]["messages"], [{"role": "user", "content": "hola"}])
        self.assertEqual(nube.uso_mes()["usuarios"][U]["in"], 11)

    def test_gemini_razonamiento_sin_temperatura_y_con_margen(self):
        nube.guardar_admin({"proveedor": "google", "url": self.url, "modelo": "gemini-3.8-flash", "razonamiento": "medium",
                            "precio_in": 0, "precio_out": 0, "clave": "clave-falsa-google"})
        self.assertEqual(nube.precios(), ((0.75, 3.75), False))                 # precio de lanzamiento de 3.8 Flash
        ok, r = nube.intentar(_Ctx(), [{"role": "user", "content": "hola"}], 1000, 0.6, None, False, None)
        self.assertEqual((ok, r), (True, "respuesta"))
        cuerpo = _Falso.visto[-1]["cuerpo"]
        self.assertEqual(cuerpo["reasoning_effort"], "medium")
        self.assertNotIn("temperature", cuerpo)                                  # Gemini 3 no la admite
        self.assertEqual(cuerpo["max_tokens"], 7000)                             # +6000 para el razonamiento
        with self.assertRaises(ValueError):
            nube.guardar_admin({"razonamiento": "minimal"})                      # 3.8 Flash no tiene «minimal»

    def test_ipv4_primero_para_no_colgarse_con_ipv6_sin_ruta(self):
        import red
        import socket as so
        infos = [(so.AF_INET6, 1, 6, "", ("::1", 443)), (so.AF_INET, 1, 6, "", ("1.2.3.4", 443)),
                 (so.AF_INET6, 1, 6, "", ("::2", 443)), (so.AF_INET, 1, 6, "", ("5.6.7.8", 443))]
        self.assertEqual([i[4][0] for i in red.ordenar(infos)], ["1.2.3.4", "5.6.7.8", "::1", "::2"])
        ok, r = nube.intentar(_Ctx(), [{"role": "user", "content": "hola"}], 100, 0.5, None, False, None)   # sigue funcionando por http local
        self.assertTrue(ok)

    def test_modelo_saturado_pasa_al_de_respaldo(self):
        nube.ESPERAS_TRANSITORIAS = ()
        try:
            nube.guardar_admin({"modelo": "saturado", "modelo_respaldo": "normal"})
            ok, r = nube.intentar(_Ctx(), [{"role": "user", "content": "hola"}], 100, 0.5, None, False, None)
            self.assertEqual((ok, r), (True, "respuesta"))
            self.assertEqual([v["cuerpo"]["model"] for v in _Falso.visto], ["saturado", "normal"])
            nube.guardar_admin({"modelo_respaldo": "saturado"})                  # ambos caídos: pasa a la IA local
            ok, motivo = nube.intentar(_Ctx(), [{"role": "user", "content": "hola"}], 100, 0.5, None, False, None)
            self.assertFalse(ok)
        finally:
            nube.ESPERAS_TRANSITORIAS = (3, 10, 30)
            nube.guardar_admin({"modelo_respaldo": ""})

    def test_probar_funciona_tambien_con_el_respaldo(self):
        nube.ESPERAS_TRANSITORIAS = ()
        try:
            nube.guardar_admin({"modelo": "saturado", "modelo_respaldo": "normal"})
            r = nube.probar(U)
            self.assertEqual(r["respuesta"], "respuesta"); self.assertGreater(r["tokens_in"], 0)
        finally:
            nube.ESPERAS_TRANSITORIAS = (3, 10, 30)
            nube.guardar_admin({"modelo_respaldo": ""})

    def test_limite_de_uso_usa_el_respaldo_y_si_no_pasa_a_local_sin_insistir(self):
        nube._caido.clear()
        nube.guardar_admin({"modelo": "limite", "modelo_respaldo": "normal"})
        ok, r = nube.intentar(_Ctx(), [{"role": "user", "content": "hola"}], 100, 0.5, None, False, None)
        self.assertEqual((ok, r), (True, "respuesta"))                       # el respaldo tiene su propia cuota
        ok, r = nube.intentar(_Ctx(), [{"role": "user", "content": "hola"}], 100, 0.5, None, False, None)
        self.assertEqual([v["cuerpo"]["model"] for v in _Falso.visto], ["limite", "normal", "normal"])   # no insiste con el agotado
        _Falso.visto.clear()
        nube.guardar_admin({"modelo_respaldo": "limite"})                    # todo agotado
        nube._caido.clear()
        ok, motivo = nube.intentar(_Ctx(), [{"role": "user", "content": "hola"}], 100, 0.5, None, False, None)
        self.assertFalse(ok)                                                  # → la IA local
        ok2, motivo2 = nube.intentar(_Ctx(), [{"role": "user", "content": "hola"}], 100, 0.5, None, False, None)
        self.assertFalse(ok2); self.assertIn("llegó a su límite", motivo2)
        self.assertEqual(len(_Falso.visto), 1)                                # el segundo ni llamó a la API
        nube._enfriar.clear(); nube._caido.clear()
        nube.guardar_admin({"modelo_respaldo": ""})

    def test_limite_mensual_reintenta_cada_15_dias_o_lo_que_fije_cada_persona(self):
        nube.guardar_admin({"modelo": "mensual", "modelo_respaldo": ""})
        ok, _ = nube.intentar(_Ctx(), [{"role": "user", "content": "hola"}], 100, 0.5, None, False, None)
        self.assertFalse(ok)
        dias = (nube._hasta("otro", "mensual") - time.time()) / 86400
        self.assertAlmostEqual(dias, 15, delta=0.1)
        nube.guardar_persona(U, {"reintento_dias": 2})                           # esa persona reintenta antes
        self.assertAlmostEqual((nube._hasta("otro", "mensual", U) - time.time()) / 86400, 2, delta=0.1)
        nube.guardar_persona(U, {"reintento_dias": 0})
        self.assertEqual(len(nube.libres(U)), 0)
        self.assertIn("monthly", json.dumps(base.kv_get("nube_ultimo_error")).lower())
        self.assertTrue(base.kv_get("nube_pausas"))                              # sobrevive a un reinicio

    def test_api_de_reserva_y_ajuste_por_persona(self):
        secretos.guardar("claves_ia", "clave-falsa-dos", "groq")
        config.C = config.guardar({"nube_proveedor2": "groq", "nube_url2": self.url, "nube_modelo2": "normal",
                                   "nube_modelo2_respaldo": ""})
        nube.guardar_admin({"modelo": "limite", "modelo_respaldo": ""})
        ok, r = nube.intentar(_Ctx(), [{"role": "user", "content": "hola"}], 100, 0.5, None, False, None)
        self.assertEqual((ok, r), (True, "respuesta"))                           # la principal se agotó: pasó a la reserva
        self.assertEqual([v["cuerpo"]["model"] for v in _Falso.visto], ["limite", "normal"])
        self.assertEqual(_Falso.visto[-1]["cab"]["authorization"], "Bearer clave-falsa-dos")
        nube._caido.clear(); _Falso.visto.clear()
        nube.guardar_persona(U, {"usar_reserva": False})                         # esta persona no quiere la reserva
        ok, _ = nube.intentar(_Ctx(), [{"role": "user", "content": "hola"}], 100, 0.5, None, False, None)
        self.assertFalse(ok)
        self.assertEqual([v["cuerpo"]["model"] for v in _Falso.visto], ["limite"])
        config.C = config.guardar({"nube_proveedor2": "", "nube_url2": ""})

    def test_la_cola_no_espera_a_la_gpu_si_la_tarea_va_a_la_api(self):
        orig = (ia.otros_modelos, ia.pc_ocupado)
        ia.otros_modelos = lambda **k: ["otro-modelo"]          # otra app tiene la tarjeta
        ia.pc_ocupado = lambda: True                              # y además se está jugando
        try:
            t = ia.Trabajo("leccion", lambda ctx: "hecho", 1, U, "x")
            ia.cola._correr(t)
            self.assertEqual((t.estado, t.resultado), ("listo", "hecho"))     # fue por la API: no esperó
            t2 = ia.Trabajo("tutor", lambda ctx: "hecho", 1, U, "y")        # lo personal nunca va a la API: sí espera
            ia.cola._correr(t2)
            self.assertNotEqual(t2.estado, "listo")
            self.assertGreater(t2.no_antes, time.time())
        finally:
            ia.otros_modelos, ia.pc_ocupado = orig
            with ia.cola._cv:
                ia.cola._h[:] = [x for x in ia.cola._h if x[2] is not t2]

    def test_plan_gratuito_por_defecto_cuesta_cero_y_no_aplica_topes(self):
        self.assertTrue(config.DEFECTO["nube_plan_gratuito"])                    # viene encendido de fábrica
        config.C = config.guardar({"nube_plan_gratuito": True})
        self.assertEqual(nube.precios(), ((0.0, 0.0), False))
        nube.guardar_persona(U, {"tope_usd": 0})                                   # un tope en dinero no frena nada
        self.assertEqual(nube.aplicable("leccion", U)[0], U)
        ok, r = nube.intentar(_Ctx(), [{"role": "user", "content": "hola"}], 100, 0.5, None, False, None)
        self.assertTrue(ok)
        self.assertEqual(nube.gastado(U), 0)                                      # sin costo, pero sí cuenta las llamadas y tokens
        self.assertEqual(nube.resumen_persona(U)["llamadas"], 1)
        self.assertGreater(nube.resumen_persona(U)["tokens"], 0)
        nube.guardar_admin({"plan_gratuito": False})                              # con facturación, vuelve el tope
        self.assertIsNone(nube.aplicable("leccion", U)[0])

    def test_tope_y_fallo_devuelven_a_la_ia_local(self):
        nube.guardar_persona(U, {"tope_usd": 0.0001})
        nube.registrar_uso(U, 1_000_000, 0)
        ok, motivo = nube.intentar(_Ctx(), [{"role": "user", "content": "x"}], 10, 0, None, False, None)
        self.assertFalse(ok); self.assertIn("tope", motivo)
        nube.guardar_persona(U, {"tope_usd": 50})
        nube.guardar_admin({"url": "http://127.0.0.1:9", "tope_global_usd": 1000})       # nadie escucha: falla
        ok, motivo = nube.intentar(_Ctx(), [{"role": "user", "content": "x"}], 10, 0, None, False, None)
        self.assertFalse(ok)

    def test_avisos_apagados_validan_y_solo_mandan_si_hay_algo(self):
        a = avisos.ajustes(U)
        self.assertFalse(a["activo"])
        with self.assertRaises(ValueError):
            avisos.guardar(U, {"activo": True})                                  # sin canal ni destino
        with self.assertRaises(ValueError):
            avisos.guardar(U, {"canal": "webhook", "destino": "http://127.0.0.1:8092/x"})   # no pública
        with self.assertRaises(ValueError):
            avisos.guardar(U, {"canal": "ntfy", "destino": "corto"})
        t = avisos.nuevo_tema_ntfy()
        avisos.guardar(U, {"canal": "ntfy", "destino": t, "hora": "07:30"})
        self.assertEqual(avisos.texto_aviso({"minutos": 10, "vencidas": 0, "nuevas": 0, "lecciones": 0}, False), "")
        txt = avisos.texto_aviso({"minutos": 10, "vencidas": 8, "nuevas": 4, "lecciones": 1, "siguiente": "Recursión"}, True)
        self.assertIn("12 tarjetas", txt); self.assertIn("Recursión", txt)
        self.assertNotIn("Recursión", avisos.texto_aviso({"minutos": 10, "vencidas": 1, "nuevas": 0, "lecciones": 0, "siguiente": "Recursión"}, False))

    def test_envio_diario_una_vez_y_a_su_hora(self):
        enviados = []
        avisos._enviar_a = lambda a, texto, url="": enviados.append(texto)
        avisos.guardar(U, {"canal": "ntfy", "destino": avisos.nuevo_tema_ntfy(), "hora": "00:00", "activo": True})
        r = lambda u: {"minutos": 10, "vencidas": 3, "nuevas": 0, "lecciones": 0, "siguiente": ""}
        avisos.enviar_pendientes(r, [U]); avisos.enviar_pendientes(r, [U])
        self.assertEqual(len(enviados), 1)                                       # una vez al día
        avisos.guardar(U, {"hora": "23:59"})
        base.kv_set(f"avisos:{U}", {**avisos.ajustes(U), "ultimo": ""})
        enviados.clear()
        if time.localtime().tm_hour * 60 + time.localtime().tm_min < 23 * 60 + 59:
            avisos.enviar_pendientes(r, [U])
            self.assertEqual(enviados, [])                                       # aún no es su hora



class PruebaEsquemaNoAplicado(unittest.TestCase):
    """Servicios que aceptan response_format pero no lo aplican (Ollama Cloud): el JSON debe validarse."""

    def test_cumple_detecta_claves_ausentes(self):
        import nube
        esq = {"type": "object", "required": ["partes"], "properties": {"partes": {"type": "array", "items": {
            "type": "object", "required": ["titulo"], "properties": {"titulo": {"type": "string"}}}}}}
        self.assertFalse(nube._cumple({"partes": [{"title": "x"}]}, esq))
        self.assertFalse(nube._cumple({}, esq))
        self.assertTrue(nube._cumple({"partes": [{"titulo": "x"}]}, esq))


class PruebaCarrilNube(unittest.TestCase):
    """Con `trabajos_nube` la nube tiene su carril; lo que falte (API caída) pasa al local."""

    def _cola(self):
        import ia
        c = object.__new__(ia.Cola)
        c.actuales = []
        return ia, c

    def _t(self, tipo, n):
        class T:
            pass
        t = T()
        t.tipo, t.usuario, t.etiqueta = tipo, "u", f"e{n}"
        return (1, n, t)

    def test_reparto_de_carriles(self):
        import config
        ia, c = self._cola()
        con_nube = {"leccion"}
        antes = (ia.nube.aplicable, ia.nube.sana, dict(config.C))
        ia.nube.aplicable = lambda tipo, u, e="": ("u" if tipo in con_nube else None, None)
        ia.nube.sana = lambda: True
        config.C["trabajos_nube"] = 3
        try:
            lec, tut = self._t("leccion", 1), self._t("tutor", 2)
            self.assertIs(c._elegir([lec, tut], "nube"), lec)           # la nube solo toma lo que puede hacer
            self.assertIs(c._elegir([lec, tut], "local"), tut)          # lo local, primero lo que solo puede ser local
            self.assertIsNone(c._elegir([lec], "local"))                # la nube aún tiene sitio: no se le quita la lección
            lleno = [type("X", (), {"carril": "nube"})() for _ in range(3)]
            c.actuales = lleno
            self.assertIs(c._elegir([lec], "local"), lec)               # nube llena: lo que falta pasa al local
            c.actuales = []
            ia.nube.sana = lambda: False
            self.assertIsNone(c._elegir([lec], "nube"))                 # API caída: la nube no toma nada
            self.assertIs(c._elegir([lec], "local"), lec)               # y el local toma todo
            config.C["trabajos_nube"] = 0
            self.assertIs(c._elegir([lec, tut], "local"), lec)          # sin carril de nube: como siempre
        finally:
            ia.nube.aplicable, ia.nube.sana = antes[0], antes[1]
            config.C.clear()
            config.C.update(antes[2])


class PruebaRelevanciaFuentes(unittest.TestCase):
    def test_descarta_lo_que_comparte_una_sola_palabra_y_las_portadas(self):
        import verificacion as vf
        crudo = [
            {"titulo": "Zero trust architecture", "url": "https://csrc.nist.gov/pubs/sp/800/207/final", "texto": "NIST zero trust"},
            {"titulo": "Qué es Zero Trust", "url": "https://axity.com/blog/zero-trust", "texto": "modelo de seguridad zero trust"},
            {"titulo": "Cambio de paradigma", "url": "https://es.wikipedia.org/wiki/Cambio_de_paradigma", "texto": "Kuhn ciencia"},
            {"titulo": "Lakers coaches", "url": "https://en.wikipedia.org/wiki/List_of_Lakers_coaches", "texto": "coaches"},
            {"titulo": "Wikipedia", "url": "https://www.wikipedia.org/", "texto": ""},
            {"titulo": "Zero Trust y NIST", "url": "https://www.cisa.gov/zero-trust", "texto": "zero trust architecture"},
        ]
        orig = vf.ia.buscar_web
        vf.ia.buscar_web = lambda q, n, idioma: list(crudo)
        try:
            r = vf.buscar_fuentes(["zero trust cambio de paradigma"], ["zero trust architecture NIST"], n=10,
                                  academicas=False, leer=False)
        finally:
            vf.ia.buscar_web = orig
        urls = {x["url"] for x in r}
        self.assertIn("https://csrc.nist.gov/pubs/sp/800/207/final", urls)
        self.assertNotIn("https://es.wikipedia.org/wiki/Cambio_de_paradigma", urls)
        self.assertNotIn("https://en.wikipedia.org/wiki/List_of_Lakers_coaches", urls)
        self.assertNotIn("https://www.wikipedia.org/", urls)


class PruebaFuentesAportadas(unittest.TestCase):
    def test_guardar_limites_y_entrar_primero_a_la_leccion(self):
        import aportadas
        base.kv_set(f"aportadas:{U}", None)
        with self.assertRaises(ValueError):
            aportadas.guardar(U, "t.1", "x", "", "muy corto")
        with self.assertRaises(ValueError):
            aportadas.guardar(U, "t.1", "x", "javascript:alert(1)", "a" * 300)
        ident = aportadas.guardar(U, "t.1", "Mi artículo", "https://www.nist.gov/x", "Zero trust. " * 40)
        aportadas.guardar(U, "t.2", "Otro", "", "texto " * 60)
        fs = aportadas.fuentes_de(U, "t.1")
        self.assertEqual(len(fs), 1)
        self.assertTrue(fs[0]["titulo"].startswith("📎"))
        self.assertEqual(fs[0]["fiabilidad"]["nivel"], 4)            # nist.gov: se juzga por el sitio de origen
        self.assertEqual(len(aportadas.lista(U)), 2)
        self.assertNotIn("texto", aportadas.publico(aportadas.obtener(U, ident)))
        aportadas.borrar(U, ident)
        self.assertEqual(aportadas.fuentes_de(U, "t.1"), [])
        self.assertIsNone(nube.aplicable("aportada", U)[0])           # el análisis nunca sale a la API
        base.kv_set(f"aportadas:{U}", None)


class PruebaCrossrefRespaldo(unittest.TestCase):
    def setUp(self):
        base.ejecutar("DELETE FROM kv WHERE k LIKE 'papers:%'")
        import ciencia
        self.ciencia, self.orig = ciencia, (ciencia._consultar, ciencia._crossref)

    def tearDown(self):
        self.ciencia._consultar, self.ciencia._crossref = self.orig
        base.ejecutar("DELETE FROM kv WHERE k LIKE 'papers:%'")

    def _cr(self, titulo, doi):
        return {"titulo": titulo, "autores": "A", "anio": 2024, "revista": "R", "citas": 30, "tipo": "article",
                "doi": doi, "url": doi, "abierto": None, "resumen": "resumen"}

    def test_si_openalex_cae_responde_crossref(self):
        def cae(params):
            raise OSError("sin red")
        self.ciencia._consultar = cae
        self.ciencia._crossref = lambda q, n: [self._cr("Zero trust a", "https://doi.org/1")]
        r = self.ciencia.buscar("zero trust consulta uno", 3)
        self.assertEqual([x["titulo"] for x in r], ["Zero trust a"])

    def test_si_openalex_trae_pocos_crossref_completa_sin_repetir(self):
        w = {"id": "W1", "title": "Zero trust architecture review", "type": "review", "relevance_score": 10,
             "cited_by_count": 500, "publication_year": 2022, "doi": "https://doi.org/1",
             "abstract_inverted_index": {"zero": [0], "trust": [1], "architecture": [2]}, "authorships": [],
             "primary_location": {}, "open_access": {}}
        self.ciencia._consultar = lambda params: [w]
        self.ciencia._crossref = lambda q, n: [self._cr("Zero trust architecture review", "https://doi.org/1"),
                                               self._cr("Otro trabajo", "https://doi.org/2")]
        r = self.ciencia.buscar("zero trust architecture consulta dos", 4)
        self.assertEqual(sorted(x["doi"] for x in r), ["https://doi.org/1", "https://doi.org/2"])


class PruebaDuracionLimite(unittest.TestCase):
    def test_periodos(self):
        class E(Exception):
            def __init__(self, m, code=429):
                super().__init__(m)
                self.code = code
        d = nube.duracion_limite
        self.assertEqual(d(E("you have reached your monthly usage limit, add usage credits")), 15 * 86400)
        self.assertEqual(d(E("model not included", 402)), 15 * 86400)
        self.assertEqual(d(E("You exceeded your current quota, please check your plan and billing details. RESOURCE_EXHAUSTED")), 3 * 3600)
        self.assertEqual(d(E("GenerateRequestsPerDayPerProjectPerModel-FreeTier")), 3 * 3600)
        self.assertEqual(d(E("rate limit")), 900)

if __name__ == "__main__":
    r = unittest.main(exit=False, verbosity=2).result
    sys.exit(0 if r.wasSuccessful() else 1)
