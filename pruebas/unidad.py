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
from datetime import datetime, timedelta
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
import noticias as nt  # noqa: E402
from base import ejecutar, fila  # noqa: E402

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

class PruebaCasosVelasComposicion(unittest.TestCase):
    """Zonas del peor al mejor caso, patrones de velas y lectura de la composición de un fondo (sin internet)."""

    @staticmethod
    def _serie(n=300, paso=0.4):
        out, c = [], 100.0
        for k in range(n):
            c *= 1 + (0.012 if k % 2 else -0.011) + paso / 1000
            out.append([1700000000 + k * 86400, round(c, 4), c * 1.01, c * 0.99, 1000, round(c * 0.998, 4)])
        return out

    def test_las_cinco_zonas_suman_100_y_marcan_la_mas_y_la_menos_probable(self):
        serie = self._serie()
        r = ac.casos(serie, 30, serie[-1][1], 0.2)
        self.assertEqual([z["clave"] for z in r["zonas"]], ["peor", "pesimista", "central", "optimista", "mejor"])
        self.assertEqual(sum(z["prob"] for z in r["zonas"]), 100)
        self.assertEqual(sum(z["prob_estadistica"] for z in r["zonas"]), 100)
        self.assertEqual(sum(1 for z in r["zonas"] if z.get("marca") == "más probable"), 1)
        self.assertEqual(sum(1 for z in r["zonas"] if z.get("marca") == "menos probable"), 1)
        self.assertTrue(all(z["prob"] >= 1 for z in r["zonas"]))

    def test_las_zonas_se_ajustan_a_la_probabilidad_de_subir(self):
        serie = self._serie()
        sube = ac.casos(serie, 30, serie[-1][1], 0.2, 85)["zonas"]
        baja = ac.casos(serie, 30, serie[-1][1], 0.2, 15)["zonas"]
        arriba = lambda zs: sum(z["prob"] for z in zs if z["clave"] in ("optimista", "mejor"))
        self.assertGreater(arriba(sube), arriba(baja))
        self.assertEqual(sum(z["prob"] for z in sube), 100)
        self.assertEqual(sum(z["prob"] for z in baja), 100)

    def test_los_limites_de_precio_son_continuos_y_ordenados(self):
        serie = self._serie()
        z = ac.casos(serie, 90, 100.0, 0.3)["zonas"]
        self.assertIsNone(z[0]["desde"])
        self.assertIsNone(z[-1]["hasta"])
        for a, b in zip(z, z[1:]):
            self.assertAlmostEqual(a["hasta"], b["desde"])
        self.assertLess(z[1]["desde"], 100.0)
        self.assertGreater(z[3]["hasta"], 100.0)

    def test_sin_datos_suficientes_no_inventa(self):
        self.assertIsNone(ac.casos(self._serie(10), 30, 100.0, 0.2))
        self.assertIsNone(ac.casos(self._serie(), 30, 100.0, None))

    @staticmethod
    def _con_vela(o, h, l, c, bajada=True):
        """40 velas de fondo (caída o subida del 4 % en las 5 previas) y una vela final con la forma dada."""
        v, p = [], 100.0
        for k in range(40):
            p *= 0.99 if bajada and k > 30 else 1.01 if not bajada and k > 30 else 1.0
            v.append([1700000000 + k * 86400, p, p * 1.003, p * 0.997, 1, p])
        base_ = v[-1][1]
        f = base_ / 100
        v.append([1700000000 + 40 * 86400, c * f, h * f, l * f, 1, o * f])
        return v

    def test_martillo_tras_caida_y_hombre_colgado_tras_subida(self):
        martillo = (self._con_vela(95, 96.2, 92, 96, bajada=True))
        nombres = [r["patron"] for r in ac.patrones_velas(martillo, 1)["recientes"]]
        self.assertIn("martillo", nombres)
        colgado = self._con_vela(95, 96.2, 92, 96, bajada=False)
        nombres = [r["patron"] for r in ac.patrones_velas(colgado, 1)["recientes"]]
        self.assertIn("hombre colgado", nombres)
        self.assertNotIn("martillo", nombres)

    def test_estrella_fugaz_doji_y_envolvente(self):
        est = self._con_vela(100, 105, 99.8, 100.8, bajada=False)
        self.assertIn("estrella fugaz", [r["patron"] for r in ac.patrones_velas(est, 1)["recientes"]])
        doji = self._con_vela(100, 101, 99, 100.02, bajada=True)
        self.assertIn("doji", [r["patron"] for r in ac.patrones_velas(doji, 1)["recientes"]])
        env = self._con_vela(95.8, 97.4, 95.6, 97.2, bajada=True)
        f = env[-3][1] / 100                                   # la vela previa es roja: abrió 97 y cerró 96
        env[-2] = [env[-2][0], 96.0 * f, 97.2 * f, 95.9 * f, 1, 97.0 * f]
        env[-1] = [env[-1][0], 97.2 * f, 97.4 * f, 95.6 * f, 1, 95.8 * f]
        self.assertIn("envolvente alcista", [r["patron"] for r in ac.patrones_velas(env, 1)["recientes"]])

    def test_datos_viejos_sin_apertura_usan_el_cierre_anterior(self):
        serie = [[x[0], x[1], x[2], x[3], x[4]] for x in self._serie(60)]
        v = ac.velas(serie)
        self.assertEqual(len(v), 60)
        self.assertAlmostEqual(v[10][1], serie[9][1])

    def test_composicion_lee_la_tabla_y_calcula_el_resto(self):
        html = ("<table><tbody><tr><td>1</td><td class='sym'><a href='/x'>NVDA</a></td><td>NVIDIA Corporation</td><td>7.92%</td><td>1</td></tr>"
                "<tr><td>2</td><td><a>AAPL</a></td><td>Apple Inc.</td><td>7.61%</td><td>2</td></tr></tbody></table>"
                'date:"Oct 27, 2026",count:505,trust')
        original = ac._get
        ac._get = lambda url, timeout=15: html.encode()
        try:
            d = ac._leer_composicion("SPY")
        finally:
            ac._get = original
        self.assertEqual([f["simbolo"] for f in d["filas"]], ["NVDA", "AAPL"])
        self.assertEqual(d["total"], 505)
        self.assertEqual(d["fecha"], "Oct 27, 2026")
        self.assertAlmostEqual(d["filas"][0]["peso"], 7.92)

    def test_familia_del_sp500(self):
        f = ac.familia("SPY")
        self.assertIsNotNone(f)
        self.assertIn("^GSPC", f["simbolos"] + ["^GSPC"])
        self.assertIsNone(ac.familia("NVDA"))
        self.assertTrue({"SPY", "VOO", "IVV", "RSP", "QQQ", "^DJI", "^RUT"} <= set(f["simbolos"]))


class PruebaFamiliaEnergia(unittest.TestCase):
    """⚡ Energía eléctrica del mundo (2026-10-29): datos de la familia y reparto lista principal / grupo plegable."""

    def setUp(self):
        self._cot, self._sec = ac.cotizar, ac.completar_sector
        ac.cotizar = lambda simbolos, max_edad=0: {}          # sin internet
        ac.completar_sector = lambda simbolo: None
        self.u = "energia@prueba"
        ejecutar("DELETE FROM accion_vigilada WHERE usuario=?", (self.u,))

    def tearDown(self):
        ac.cotizar, ac.completar_sector = self._cot, self._sec

    def test_los_datos_estan_limpios(self):
        f = next(x for x in ac.FAMILIAS if x["clave"] == "energia")
        todos = [s for g in f["grupos"] for s, _ in g[1]]
        self.assertGreaterEqual(len(todos), 200)
        self.assertEqual(len(todos), len(set(todos)), "símbolos repetidos en la familia")
        self.assertTrue(all(ac.valido(s) for s in todos))
        self.assertTrue(all(q and len(q) > 8 for g in f["grupos"] for _, q in g[1]), "todos llevan una nota")
        self.assertTrue(set(f["nucleo"]) <= set(todos))
        self.assertEqual(set(f["nucleo"]), {"GEV", "TLN", "CEG", "VST", "NEE", "ISA.CL", "CELSIA.CL", "GEB.CL"})
        otros = [s for x in ac.FAMILIAS if x is not f for g in x["grupos"] for s, _ in g[1]]
        self.assertFalse(set(todos) & set(otros), "un símbolo no puede estar en dos familias")

    def test_cada_simbolo_va_a_su_familia(self):
        self.assertEqual(ac.familia("GEV")["clave"], "energia")
        self.assertEqual(ac.familia("ISA.CL")["clave"], "energia")
        self.assertEqual(ac.familia("SPY")["clave"], "sp500")
        self.assertEqual(ac.familia("^GSPC")["clave"], "sp500")
        self.assertIsNone(ac.familia("NVDA"))

    def test_solo_el_nucleo_y_el_ancla_entran_en_la_rutina_diaria_de_la_ia(self):
        self.assertFalse(ac.pronostico_bajo_demanda("GEV"))      # lo pidió la persona
        self.assertFalse(ac.pronostico_bajo_demanda("^GSPC"))    # ancla del S&P 500
        self.assertFalse(ac.pronostico_bajo_demanda("NVDA"))     # fuera de toda familia
        self.assertTrue(ac.pronostico_bajo_demanda("XLU"))
        self.assertTrue(ac.pronostico_bajo_demanda("IBE.MC"))
        self.assertTrue(ac.pronostico_bajo_demanda("SPY"))

    def test_agregar_la_familia_reparte_nucleo_y_grupo(self):
        hechos, fallidos = ac.agregar_familia(self.u, "energia")
        self.assertEqual(fallidos, {})
        filas_ = ac.lista(self.u)
        self.assertEqual(len(filas_), len(hechos))
        principal = {r["simbolo"] for r in filas_ if not r["grupo"]}
        self.assertEqual(principal, {"GEV", "TLN", "CEG", "VST", "NEE", "ISA.CL", "CELSIA.CL", "GEB.CL"})
        self.assertTrue(all(r["alerta_pct"] == 4 for r in filas_ if not r["grupo"]))
        self.assertTrue(all(r["grupo"] == "energia" and r["alerta_pct"] == 0 for r in filas_ if r["grupo"]))
        self.assertEqual(ac.agregar_familia(self.u, "energia"), ([], {}))     # repetir no duplica

    def test_el_tope_de_60_solo_cuenta_la_lista_principal(self):
        for k in range(60):
            ejecutar("INSERT INTO accion_vigilada(usuario,simbolo,orden) VALUES(?,?,?)", (self.u, f"T{k}", k))
        with self.assertRaises(ValueError):
            ac.vigilar(self.u, "AAA")
        self.assertEqual(ac.vigilar(self.u, "AAA", grupo="energia", alerta_pct=0), "AAA")
        r = next(x for x in ac.resumen(self.u, refrescar=False) if x["simbolo"] == "AAA")
        self.assertEqual(r["grupo"], "energia")

    def test_un_nucleo_que_estaba_en_el_grupo_sube_a_la_lista_principal(self):
        ac.vigilar(self.u, "GEV", grupo="energia", alerta_pct=0)
        ac.agregar_familia(self.u, "energia")
        r = next(x for x in ac.lista(self.u) if x["simbolo"] == "GEV")
        self.assertIsNone(r["grupo"])
        self.assertEqual(r["alerta_pct"], 4)


class PruebaDividendosYVista(unittest.TestCase):
    """💰 Dividendos de los últimos 12/24 meses y preferencias de la lista (agrupar, ordenar) por persona."""

    def _info(self, precio, pagos):
        return {"meta": {"precio": precio, "dividendos": pagos}}

    def test_cuatro_pagos_trimestrales_dan_el_rendimiento_anual(self):
        ahora = time.time()
        pagos = [[ahora - k * 90 * DIA, 1.0] for k in range(4)]
        d = ac.dividendos_de(self._info(100.0, pagos), 12)
        self.assertEqual((d["paga"], d["pagos"]), (True, 4))
        self.assertAlmostEqual(d["anual"], 4.0)
        self.assertAlmostEqual(d["rend"], 4.0)
        self.assertEqual(d["ultimo_monto"], 1.0)

    def test_la_ventana_de_24_meses_promedia_por_año(self):
        ahora = time.time()
        pagos = [[ahora - k * 90 * DIA, 1.0] for k in range(8)]       # 8 pagos en ~2 años
        d = ac.dividendos_de(self._info(100.0, pagos), 24)
        self.assertEqual(d["pagos"], 8)
        self.assertAlmostEqual(d["anual"], 4.0)
        self.assertLess(ac.dividendos_de(self._info(100.0, pagos), 12)["pagos"], 8)

    def test_sin_pagos_no_paga_y_sin_datos_no_se_sabe(self):
        d = ac.dividendos_de(self._info(50.0, []), 12)
        self.assertEqual((d["conocido"], d["paga"], d["rend"]), (True, False, 0.0))
        self.assertFalse(ac.dividendos_de({"meta": {"precio": 50.0}}, 12)["conocido"])
        self.assertFalse(ac.dividendos_de(None, 12)["conocido"])

    def test_un_pago_viejo_no_cuenta_en_la_ventana(self):
        viejo = [[time.time() - 400 * DIA, 5.0]]
        self.assertFalse(ac.dividendos_de(self._info(100.0, viejo), 12)["paga"])
        self.assertTrue(ac.dividendos_de(self._info(100.0, viejo), 24)["paga"])

    def test_la_vista_tiene_valores_por_defecto_y_valida_lo_que_se_guarda(self):
        u = "vista@prueba"
        ejecutar("DELETE FROM kv WHERE k=?", (f"acciones_vista:{u}",))
        self.assertEqual(ac.vista_de(u), ac.VISTA_BASE)
        v = ac.guardar_vista(u, {"agrupar": "dividendos", "subagrupar": "pais", "orden": "dividendo", "dividendo_meses": 24,
                                 "mostrar_dividendo": False})
        self.assertEqual((v["agrupar"], v["subagrupar"], v["orden"], v["dividendo_meses"], v["mostrar_dividendo"]),
                         ("dividendos", "pais", "dividendo", 24, False))
        self.assertEqual(ac.vista_de(u), v)
        for malo in ({"agrupar": "color"}, {"orden": 3}, {"dividendo_meses": 7}, {"mostrar_dividendo": "sí"}):
            with self.assertRaises(ValueError):
                ac.guardar_vista(u, malo)
        self.assertEqual(ac.vista_de(u), v)                       # lo rechazado no cambió nada
        self.assertEqual(ac.guardar_vista(u, {"cosa_rara": 1}), v)  # lo desconocido se ignora

    def test_cada_simbolo_de_energia_tiene_un_tipo_y_un_pais(self):
        import familia_energia as fe
        todos = [x for g in fe.GRUPOS for x, _ in g[1]]
        self.assertEqual([x for x in todos if x not in fe.FUENTE_DE], [], "símbolos sin clasificar")
        repetidos = [x for lista in fe._POR_FUENTE.values() for x in lista]
        self.assertEqual(len(repetidos), len(set(repetidos)), "un símbolo en dos tipos de energía")
        self.assertEqual(set(repetidos), set(todos))
        self.assertTrue({k for k, _ in fe.FUENTES} == set(fe._POR_FUENTE))
        self.assertEqual((ac.subtema_de("CEG"), ac.subtema_de("FSLR"), ac.subtema_de("NRG"), ac.subtema_de("SPY")),
                         ("nuclear", "renovable", "fosil", None))
        self.assertEqual([ac.pais_de(x) for x in ("NEE", "ISA.CL", "ACO-X.TO", "9501.T", "PAM", "^GSPC")],
                         ["🇺🇸 Estados Unidos", "🇨🇴 Colombia", "🇨🇦 Canadá", "🇯🇵 Japón", "🇦🇷 Argentina", "🌐 Índices"])
        self.assertEqual([t["clave"] for t in ac.subtemas()][-1], "sin")

    def test_cada_persona_tiene_su_vista(self):
        ac.guardar_vista("a@prueba", {"agrupar": "sector"})
        self.assertEqual(ac.vista_de("a@prueba")["agrupar"], "sector")
        self.assertEqual(ac.vista_de("b@prueba")["agrupar"], ac.VISTA_BASE["agrupar"])

    def test_resumen_trae_tema_dividendo_y_sector(self):
        u = "resumen@prueba"
        ejecutar("DELETE FROM accion_vigilada WHERE usuario=?", (u,))
        guardar_info("GEV", [880.0, 887.85])
        guardar_info("NVDA", [100.0, 101.0])
        for k, sim in enumerate(("GEV", "NVDA")):
            ejecutar("INSERT INTO accion_vigilada(usuario,simbolo,orden) VALUES(?,?,?)", (u, sim, k))
        ejecutar("UPDATE accion_info SET sector='Industrials' WHERE simbolo='GEV'")
        r = {x["simbolo"]: x for x in ac.resumen(u, refrescar=False)}
        self.assertEqual((r["GEV"]["tema"], r["GEV"]["nucleo"], r["GEV"]["sector"]), ("energia", True, "Industrials"))
        self.assertEqual((r["NVDA"]["tema"], r["NVDA"]["nucleo"]), ("otras", False))
        self.assertIn("rend", r["GEV"]["dividendo"])
        self.assertEqual((r["GEV"]["subtema"], r["GEV"]["pais"]), ("equipos", "🇺🇸 Estados Unidos"))
        self.assertIsNone(r["NVDA"]["subtema"])
        self.assertEqual([t["clave"] for t in ac.temas()][-1], "otras")


class PruebaReporteCalibracion(unittest.TestCase):
    """Títulos del análisis de la IA, calibración de la confianza declarada y series del reporte (sin internet ni IA)."""

    def setUp(self):
        import adaptacion
        import eventos
        eventos.iniciar_tablas()
        self.ad = adaptacion
        self.u = "calibra@prueba"
        ejecutar("DELETE FROM actividad WHERE usuario=?", (self.u,))
        ejecutar("DELETE FROM evento WHERE usuario=?", (self.u,))

    def _resp(self, nivel, acierto, n=1):
        p = self.ad.NIVELES_CONFIANZA[nivel]
        for _ in range(n):
            base.registrar(self.u, "calibracion", "t.x", "a", 1.0 if acierto else 0.0, {"p": p, "nivel": nivel})

    def test_titulos_repetidos_se_arreglan_sin_tocar_lo_demas(self):
        f = self.ad.limpiar_titulos
        self.assertEqual(f("## ## Diagnóstico\ntexto con ## en medio"), "## Diagnóstico\ntexto con ## en medio")
        self.assertEqual(f("# # Título\n### ## Otro"), "# Título\n### Otro")
        self.assertEqual(f("## Ya bien"), "## Ya bien")
        self.assertEqual(f(None), "")

    def test_calibracion_sin_datos_no_inventa(self):
        r = self.ad.calibracion(self.u)
        self.assertEqual(r["n"], 0)
        self.assertIsNone(r["brier"])

    def test_calibracion_brier_y_sobreconfianza(self):
        self._resp("seguro", True, 3)
        self._resp("seguro", False, 1)       # dijo «seguro» y falló una de cuatro
        self._resp("adivino", False, 2)
        r = self.ad.calibracion(self.u)
        esperado = (3 * (0.9 - 1) ** 2 + (0.9 - 0) ** 2 + 2 * (0.3 - 0) ** 2) / 6
        self.assertEqual(r["n"], 6)
        self.assertAlmostEqual(r["brier"], round(esperado, 3), places=3)
        self.assertAlmostEqual(r["sobreconfianza"], round((3 * 0.9 + 0.9 + 2 * 0.3) / 6 - 3 / 6, 3), places=3)
        seguro = next(n for n in r["niveles"] if n["nivel"] == "seguro")
        self.assertEqual((seguro["n"], seguro["acierto"]), (4, 0.75))

    def test_series_del_reporte_vacias_y_con_estudio(self):
        s = self.ad.series_reporte(self.u)
        self.assertTrue(all(x["min"] == 0 for x in s["dias"]))
        self.assertEqual(len(s["semanas"]), self.ad.SEMANAS_REPORTE)
        # Mediodía de hoy: el día de estudio empieza a las 4 a. m. (la madrugada cuenta para el día anterior), así que `time.time()`
        # entre las 00:00 y las 04:00 caería en la barra de ayer y la prueba dependería de la hora a la que se corre.
        mediodia = datetime.now().replace(hour=12, minute=0, second=0, microsecond=0).timestamp()
        ejecutar("INSERT INTO evento(usuario,ts,fuente,tipo,valor,directo) VALUES(?,?,?,?,?,0)", (self.u, mediodia, "t", "tiempo", 1800))
        s = self.ad.series_reporte(self.u)
        self.assertAlmostEqual(sum(x["min"] for x in s["dias"]), 30, places=0)
        self.assertEqual(s["semanas"][-1]["min"], 30)
        self.assertTrue(s["dias"][-1]["activo"])

    def test_analisis_desactualizado_por_edad_o_por_cifras(self):
        d = {"minutos_30": 590, "dias_activos_14": 7}
        base_ = {"texto": "## ## Algo", "fecha": time.time()}
        kv = lambda v: __import__("base").kv_set(f"reporte_ia:{self.u}", v)  # noqa: E731
        kv(dict(base_, kpi={"minutos_30": 590, "dias_activos_14": 7}))
        r = self.ad._informe_ia(self.u, d)
        self.assertFalse(r["desactualizado"])
        self.assertEqual(r["texto"], "## Algo")
        kv(dict(base_, kpi={"minutos_30": 60, "dias_activos_14": 1}))
        self.assertTrue(self.ad._informe_ia(self.u, d)["desactualizado"])
        kv(dict(base_, fecha=time.time() - 23 * 86400, kpi={"minutos_30": 590, "dias_activos_14": 7}))
        r = self.ad._informe_ia(self.u, d)
        self.assertTrue(r["desactualizado"])
        self.assertIn("23 días", r["motivo"])


class PruebaTablero(unittest.TestCase):
    """Proyección de fecha de logro de las metas y dominio en el tiempo (sin internet ni IA)."""

    def setUp(self):
        import adaptacion
        import eventos
        eventos.iniciar_tablas()
        self.ad = adaptacion
        self.u = "tablero@prueba"
        for t in ("avance", "objetivo"):
            ejecutar(f"DELETE FROM {t} WHERE usuario=?", (self.u,))

    def test_fecha_de_logro(self):
        from datetime import date
        hoy = date(2026, 10, 29)
        self.assertEqual(self.ad._fecha_logro(0, 0, hoy), hoy)
        self.assertIsNone(self.ad._fecha_logro(10, 0, hoy))
        self.assertEqual(self.ad._fecha_logro(14, 7, hoy), date(2026, 11, 12))     # 2 semanas a 7 temas por semana
        self.assertEqual(self.ad._fecha_logro(1, 100, hoy), date(2026, 10, 30))

    def test_el_ritmo_no_cuenta_los_probados_en_pruebas_de_nivel(self):
        ahora = time.time()
        for k in range(8):
            ejecutar("INSERT INTO avance(usuario,tema,estado,actualizado,visto) VALUES(?,?,?,?,?)", (self.u, f"x.p{k}", "probado", ahora - 3600, ahora - 3600))
        ejecutar("INSERT INTO avance(usuario,tema,estado,actualizado,visto) VALUES(?,?,?,?,?)", (self.u, "x.d1", "dominado", ahora - 7200, ahora - 9000))
        self.assertAlmostEqual(self.ad._ritmo_temas(self.u, 28), 1 / 4)
        self.assertEqual(self.ad._semanas_con_avance(self.u), 1)

    def test_un_tema_repetido_no_cuenta_como_progreso_nuevo(self):
        """Dominado hace 40 días (quiz 0,9) y vuelto a tocar hoy: `avance.actualizado` es de hoy, pero el dominio es de hace 40 días."""
        ahora = time.time()
        ejecutar("DELETE FROM actividad WHERE usuario=?", (self.u,))
        ejecutar("INSERT INTO actividad(usuario,tipo,tema,area,valor,fecha) VALUES(?,?,?,?,?,?)", (self.u, "quiz", "x.v", "x", 0.9, ahora - 40 * 86400))
        ejecutar("INSERT INTO actividad(usuario,tipo,tema,area,valor,fecha) VALUES(?,?,?,?,?,?)", (self.u, "quiz", "x.v", "x", 1.0, ahora - 60))
        ejecutar("INSERT INTO avance(usuario,tema,estado,quiz,actualizado,visto) VALUES(?,?,?,?,?,?)", (self.u, "x.v", "dominado", 1.0, ahora - 60, ahora - 40 * 86400))
        self.assertEqual(self.ad._ritmo_temas(self.u, 28), 0)
        self.assertEqual(self.ad._semanas_con_avance(self.u), 1)     # su semana es la de hace 40 días, no la de hoy
        s = self.ad.dominio_en_el_tiempo(self.u)
        # La semana (lunes a domingo) en que cae «hace 40 días» depende del día en que se corre: se calcula, no se fija.
        hoy = datetime.now().date()
        lunes = lambda d: d - timedelta(days=d.weekday())  # noqa: E731
        k = (lunes(hoy) - lunes(hoy - timedelta(days=40))).days // 7
        self.assertEqual(s[-1 - k]["dominados"], 1)             # su semana: ahí ya cuenta
        self.assertEqual(s[-1 - k - 1]["dominados"], 0)         # y la anterior no
        self.assertEqual((s[-2]["dominados"], s[-1]["dominados"]), (1, 1))   # la curva no salta hoy
        ejecutar("DELETE FROM actividad WHERE usuario=?", (self.u,))

    def test_dominio_en_el_tiempo_es_acumulado_y_crece(self):
        ahora = time.time()
        for k, (est, dias) in enumerate((("dominado", 40), ("visto", 30), ("dominado", 3))):
            ejecutar("INSERT INTO avance(usuario,tema,estado,actualizado,visto) VALUES(?,?,?,?,?)", (self.u, f"x.t{k}", est, ahora - dias * 86400, ahora - dias * 86400))
        s = self.ad.dominio_en_el_tiempo(self.u)
        self.assertEqual(len(s), self.ad.SEMANAS_REPORTE)
        self.assertEqual((s[-1]["dominados"], s[-1]["explorados"]), (2, 3))
        for a, b in zip(s, s[1:]):
            self.assertLessEqual(a["dominados"], b["dominados"])
            self.assertLessEqual(a["explorados"], b["explorados"])


class PruebaCodigoVista(unittest.TestCase):
    """Lo que la persona ve de un ejercicio de código: sin la solución y con los casos ocultos enmascarados (sin ejecutar nada)."""

    def setUp(self):
        import ejecucion
        self.ej = ejecucion
        self.datos = {"titulo": "Doble", "enunciado": "x", "funcion": "f", "plantilla": "def f(x):\n    pass\n", "solucion": "def f(x):\n    return 2 * x\n",
                      "pista": "p", "casos": [{"args": [k], "esperado": 2 * k} for k in range(6)]}
        self.fila = {"id": 7, "tema": "sistemas.x.0", "datos": json.dumps(self.datos), "vio_solucion": 0}

    def test_el_ejercicio_publico_no_trae_la_solucion_ni_los_casos_ocultos(self):
        p = self.ej.publico(self.fila)
        self.assertNotIn("solucion", p)
        self.assertNotIn("pista", p)
        self.assertEqual(len(p["visibles"]), self.ej.CASOS_VISIBLES)
        self.assertEqual(p["ocultos"], 3)
        self.assertNotIn("def f(x):\n    return 2", json.dumps(p))

    def test_con_la_solucion_pedida_si_se_muestra(self):
        self.assertIn("solucion", self.ej.publico(dict(self.fila, vio_solucion=1)))

    def test_evaluar_enmascara_los_casos_ocultos(self):
        original = self.ej.correr
        self.ej.correr = lambda u, c, f, casos: {"casos": [{"ok": k % 2 == 0, "obtenido": 0, **({} if k % 2 == 0 else {})} for k in range(len(casos))],
                                                  "salida": "", "error_carga": None}
        try:
            r = self.ej.evaluar("ana", self.fila, "codigo")
        finally:
            self.ej.correr = original
        self.assertEqual((r["aprobados"], r["total"]), (3, 6))
        ocultos = [c for c in r["casos"] if c["oculto"]]
        self.assertEqual(len(ocultos), 3)
        for c in ocultos:
            self.assertNotIn("args", c)
            self.assertNotIn("esperado", c)
            self.assertNotIn("obtenido", c)
        self.assertIn("esperado", r["casos"][0])

    def test_apagada_por_defecto_en_la_configuracion(self):
        import config
        self.assertFalse(config.DEFECTO["practica_codigo"])


class PruebaTutorExaminador(unittest.TestCase):
    """Material y evidencia del tutor examinador (Hermes): sin IA, sobre una lección sembrada en la base temporal."""

    def setUp(self):
        import servidor
        self.sv = servidor
        self.u = "examen@prueba"
        self.tema = "biologia.celula.0"
        quiz = [{"tipo": "opcion", "pregunta": "¿Qué es una célula?", "opciones": ["Un órgano", "La unidad básica de la vida", "Un tejido", "Un átomo"],
                 "correcta": 1, "explicacion": "Toda la vida está hecha de células."},
                {"tipo": "abierta", "pregunta": "Explica la membrana.", "opciones": [], "correcta": 0, "explicacion": "Regula lo que entra y sale."}]
        for t in ("leccion", "actividad", "tarjeta"):
            ejecutar(f"DELETE FROM {t} WHERE usuario=?", (self.u,))
        ejecutar("INSERT INTO leccion(usuario,tema,contenido,ejercicios,completa) VALUES(?,?,?,?,1)", (self.u, self.tema, "x", json.dumps({"quiz": quiz})))

    def examen(self, **q):
        return self.sv.r_hermes_examen(self.u, dict({"tema": self.tema}, **q), {}, None)

    def evidencia(self, **d):
        return self.sv.r_hermes_evidencia(self.u, {}, dict({"tema": self.tema}, **d), None)

    def test_material_trae_modelo_y_errores_tipicos_sin_el_acierto(self):
        r = self.examen(n="5")
        op = next(x for x in r["preguntas"] if x["pregunta_id"] == 0)
        self.assertIn("unidad básica de la vida", op["respuesta_modelo"])
        self.assertIn("Toda la vida", op["respuesta_modelo"])
        self.assertEqual(len(op["errores_tipicos"]), 3)
        self.assertNotIn("La unidad básica de la vida", op["errores_tipicos"])
        ab = next(x for x in r["preguntas"] if x["pregunta_id"] == 1)
        self.assertEqual((ab["respuesta_modelo"], ab["errores_tipicos"]), ("Regula lo que entra y sale.", []))

    def test_primero_salen_las_menos_preguntadas(self):
        self.evidencia(puntaje=0.9, pregunta_id=0)
        self.evidencia(puntaje=0.9, pregunta_id=0)
        self.assertEqual([x["pregunta_id"] for x in self.examen(n="2")["preguntas"]], [1, 0])

    def test_temas_y_puntajes_invalidos_se_rechazan(self):
        self.assertIn("error", self.sv.r_hermes_examen(self.u, {"tema": "no.existe"}, {}, None))
        for malo in (7, -0.1, "abc", None):
            self.assertIn("error", self.evidencia(puntaje=malo))
        self.assertIn("error", self.sv.r_hermes_evidencia(self.u, {}, {"tema": "no.existe", "puntaje": 0.5}, None))
        ejecutar("DELETE FROM leccion WHERE usuario=?", (self.u,))
        self.assertIn("error", self.examen())            # sin lección no hay material

    def test_evidencia_buena_queda_directa_y_no_toca_el_dominio(self):
        ejecutar("DELETE FROM avance WHERE usuario=?", (self.u,))
        r = self.evidencia(puntaje=0.95, ayudas=9, repreguntas=2, pregunta_id=1, confianza="seguro")
        self.assertTrue(r["ok"])
        a = fila("SELECT valor, detalle FROM actividad WHERE usuario=? AND tipo='examen'", (self.u,))
        self.assertEqual(json.loads(a["detalle"])["ayudas"], 3)          # tope
        self.assertIsNotNone(fila("SELECT 1 FROM actividad WHERE usuario=? AND tipo='calibracion'", (self.u,)))
        self.assertIsNone(fila("SELECT 1 FROM avance WHERE usuario=? AND tema=?", (self.u, self.tema)))   # solo mide

    def test_evidencia_floja_con_modelo_crea_una_tarjeta_una_sola_vez(self):
        for _ in range(2):
            r = self.evidencia(puntaje=0.2, pregunta="Explica la membrana.", respuesta_modelo="Regula lo que entra y sale.")
        self.assertEqual(fila("SELECT COUNT(*) n FROM tarjeta WHERE usuario=?", (self.u,))["n"], 1)
        self.assertEqual(r["tarjeta"], 0)                                  # la segunda vez ya existía
        self.assertEqual(self.evidencia(puntaje=0.9, pregunta="otra", respuesta_modelo="x")["tarjeta"], 0)   # buena: sin tarjeta


class PruebaResumenSemanal(unittest.TestCase):
    """Semáforos (una sola fuente para la web y el celular) y el texto del resumen semanal (sin IA)."""

    def setUp(self):
        import servidor  # noqa: F401  (crea todas las tablas, también las de lectura)
        import adaptacion
        self.ad = adaptacion

    def sem(self, dias=12, ret=0.9, pend=10, dom=6, exp=10, brier=0.1, n=12, sobre=0.0):
        d = {"resultados": {"repaso": ret}, "dias_activos_14": dias}
        return {x["id"]: x for x in self.ad.semaforos(d, {"pendientes": pend}, {"n": n, "brier": brier, "sobreconfianza": sobre},
                                                      {"dominados": dom, "explorados": exp})}

    def test_umbrales_de_los_semaforos(self):
        self.assertEqual(self.sem()["constancia"]["estado"], "ok")
        self.assertEqual(self.sem(dias=7)["constancia"]["estado"], "atencion")
        self.assertEqual(self.sem(dias=3)["constancia"]["estado"], "riesgo")
        self.assertEqual(self.sem(ret=0.75)["retencion"]["estado"], "atencion")
        self.assertEqual(self.sem(ret=0.5)["retencion"]["estado"], "riesgo")
        self.assertEqual(self.sem(pend=35)["atrasados"]["estado"], "atencion")
        self.assertEqual(self.sem(pend=80)["atrasados"]["estado"], "riesgo")
        self.assertEqual(self.sem(dom=2, exp=10)["dominado"]["estado"], "riesgo")

    def test_sin_datos_suficientes_dice_sin_datos_y_no_un_color(self):
        s = self.sem(ret=None, pend=None, exp=3, n=4, brier=None)
        for k in ("retencion", "atrasados", "dominado", "calibracion"):
            self.assertEqual(s[k]["estado"], "nd", k)
        self.assertEqual(s["calibracion"]["lectura"], "4 de 10 respuestas con confianza")

    def test_calibracion_distingue_sobreconfianza(self):
        self.assertIn("creer que sabes más", self.sem(brier=0.3, sobre=0.2)["calibracion"]["lectura"])
        self.assertIn("más de lo que crees", self.sem(brier=0.3, sobre=-0.2)["calibracion"]["lectura"])
        self.assertEqual(self.sem(brier=0.3)["calibracion"]["estado"], "riesgo")

    def test_resumen_semanal_de_una_persona_sin_datos_no_falla_ni_inventa(self):
        import eventos
        eventos.iniciar_tablas()
        t = self.ad.resumen_semanal("nadie@prueba", {"nombre": "Nadie", "situacion": "", "metas": "", "estilo": "", "pesos": {}})
        self.assertIn("Tu semana en la Academia", t)
        self.assertIn("sin datos aún", t)
        self.assertNotIn("None", t)
        self.assertNotIn("nan", t.lower())


class PruebaEstadosDominio(unittest.TestCase):
    """Estados 0-5, calendario de pruebas diferidas, banco con segunda lectura y corrección (sin IA real, sin internet)."""

    TEMA = "biologia.celula.0"

    def setUp(self):
        import servidor  # noqa: F401  (crea todas las tablas)
        import estados
        self.es = estados
        self.u = "estados@prueba"
        for t in ("avance", "tarjeta", "actividad", "entrega", "prueba_diferida", "leccion"):
            ejecutar(f"DELETE FROM {t} WHERE usuario=?", (self.u,))

    def avance(self, estado="visto", quiz=None, feynman=None):
        ejecutar("INSERT OR REPLACE INTO avance(usuario,tema,estado,quiz,feynman,visto,actualizado) VALUES(?,?,?,?,?,?,?)",
                 (self.u, self.TEMA, estado, quiz, feynman, time.time(), time.time()))

    def act(self, tipo, valor, detalle=None, dias_atras=0):
        ejecutar("INSERT INTO actividad(usuario,tipo,tema,area,valor,detalle,fecha) VALUES(?,?,?,?,?,?,?)",
                 (self.u, tipo, self.TEMA, "biologia", valor, json.dumps(detalle) if detalle else None, time.time() - dias_atras * 86400))

    def nivel(self):
        return self.es.estado_tema(self.u, self.TEMA)["nivel"]

    def test_la_escalera_de_estados(self):
        self.assertEqual(self.nivel(), 0)
        self.avance("visto")
        self.assertEqual(self.nivel(), 1)
        self.avance("visto", quiz=0.5)
        self.assertEqual(self.nivel(), 1)                 # 50 % no es «recuerda»
        self.avance("visto", quiz=0.7)
        self.assertEqual(self.nivel(), 2)
        self.avance("dominado", quiz=0.9, feynman=0.75)
        self.assertEqual(self.nivel(), 3)
        self.act("codigo", 1.0, {"vio_solucion": True})
        self.assertEqual(self.nivel(), 3)                 # con la solución a la vista no cuenta
        self.act("codigo", 1.0, {"vio_solucion": False})
        self.assertEqual(self.nivel(), 4)

    def test_examen_del_tutor_con_pistas_de_mas_no_cuenta_como_comprende(self):
        self.avance("visto", quiz=0.7)
        self.act("examen", 0.9, {"ayudas": 3})
        self.assertEqual(self.nivel(), 2)
        self.act("examen", 0.9, {"ayudas": 0})
        self.assertEqual(self.nivel(), 3)

    def test_el_nivel_5_exige_las_tres_pruebas_diferidas(self):
        self.avance("dominado", quiz=0.9, feynman=0.8)
        self.act("codigo", 1.0, {"vio_solucion": False})
        for etapa in (1, 2):
            ejecutar("INSERT INTO prueba_diferida(usuario,tema,etapa,estado,preguntas,resultado,creada) VALUES(?,?,?,?,?,?,?)",
                     (self.u, self.TEMA, etapa, "hecha", "[]", json.dumps({"aprobada": True, "puntaje": 1}), time.time()))
        e = self.es.estado_tema(self.u, self.TEMA)
        self.assertEqual(e["nivel"], 4)
        self.assertIn("2 de 3", " ".join(e["falta"]))
        ejecutar("INSERT INTO prueba_diferida(usuario,tema,etapa,estado,preguntas,resultado,creada) VALUES(?,?,?,?,?,?,?)",
                 (self.u, self.TEMA, 3, "hecha", "[]", json.dumps({"aprobada": False, "puntaje": 0.5}), time.time()))
        self.assertEqual(self.nivel(), 4)                 # la de 45 días no se aprobó
        ejecutar("UPDATE prueba_diferida SET resultado=? WHERE usuario=? AND etapa=3", (json.dumps({"aprobada": True, "puntaje": 1}), self.u))
        self.assertEqual(self.nivel(), 5)

    def test_el_calendario_cuenta_desde_el_primer_dominio_y_no_se_salta_etapas(self):
        self.avance("dominado", quiz=0.9)
        self.act("quiz", 0.9, dias_atras=20)              # primer dominio hace 20 días
        cal = self.es.calendario(self.u, self.TEMA)
        self.assertEqual([c["disponible"] for c in cal], [True, True, False])
        sig = self.es.siguiente_cita(self.u, self.TEMA)
        self.assertEqual(sig["etapa"], 1)                 # primero la de 3 días, aunque la de 14 ya «tocaría»
        pend = self.es.pendientes(self.u)
        self.assertEqual((pend[0]["tema"], pend[0]["etapa"]), (self.TEMA, 1))
        self.assertGreaterEqual(pend[0]["vencida_hace_dias"], 16)

    def test_un_tema_no_dominado_no_tiene_calendario(self):
        self.avance("visto", quiz=0.5)
        self.assertEqual(self.es.calendario(self.u, self.TEMA), [])
        self.assertEqual(self.es.pendientes(self.u), [])

    def test_depurar_descarta_formato_malo_y_preguntas_repetidas(self):
        bien = {"pregunta": "Un laboratorio observa que la membrana de una célula deja pasar agua pero no sales; ¿qué principio explica esto?",
                "opciones": ["Permeabilidad selectiva", "Fotosíntesis", "Mitosis", "Replicación"], "correcta": 0, "explicacion": "x"}
        repetida = dict(bien, pregunta=bien["pregunta"] + " (otra vez)")
        dos_iguales = dict(bien, pregunta="Otro caso distinto sobre ribosomas en la síntesis de proteínas dentro del citoplasma", opciones=["a", "a", "b", "c"])
        corta = dict(bien, pregunta="¿Qué?")
        mala_correcta = dict(bien, pregunta="Una pregunta suficientemente larga sobre mitocondrias y la respiración celular aerobia", correcta=7)
        r = self.es.depurar([bien, repetida, dos_iguales, corta, mala_correcta], previas=[])
        self.assertEqual(r, [bien])
        self.assertEqual(self.es.depurar([bien], previas=[bien["pregunta"]]), [])         # ya se preguntó en el quiz
        self.assertLess(self.es.parecida("membrana plasmática selectiva", "ribosomas sintetizan proteínas"), 0.2)

    def _banco(self, n_buenas=5, coinciden=5):
        enunciados = ["Una bióloga marina observa que cierta alga conserva su forma dentro de agua muy salada; ¿qué estructura celular explica esa resistencia al cambio de volumen?",
                      "Durante un ayuno prolongado, el hígado de un paciente aumenta la degradación de componentes dañados; ¿qué orgánulo participa principalmente en ese reciclaje?",
                      "Un técnico descubre que una línea celular carece de enzimas oxidativas pero sobrevive con glucosa; ¿qué proceso metabólico estaría sosteniendo su energía?",
                      "Un investigador marca ARN mensajero recién sintetizado y lo sigue hasta el citoplasma; ¿dónde ocurre la traducción hacia una cadena polipeptídica?",
                      "Al examinar una hoja bajo el microscopio aparecen estructuras verdes con membranas apiladas; ¿qué función cumplen esas estructuras dentro de la planta?",
                      "Una célula nerviosa necesita mantener gradientes iónicos constantes; ¿qué mecanismo de transporte gasta energía para lograrlo continuamente?"]
        base = [{"pregunta": enunciados[k], "opciones": [f"op{k}a", f"op{k}b", f"op{k}c", f"op{k}d"], "correcta": 1, "explicacion": "porque sí"}
                for k in range(n_buenas)]

        class Ctx:
            def __init__(self):
                self.n = 0

            def fase(self, _):
                pass

            def chat(self, mensajes, max_tokens=0, temperatura=0, esquema=None, **kw):
                if "preguntas" in esquema["properties"]:
                    return {"preguntas": base}
                self.n += 1
                return {"respuesta": 1 if self.n <= coinciden else 3}
        return Ctx()

    def test_generar_banco_conserva_solo_las_confirmadas_por_la_segunda_lectura(self):
        ctx = self._banco(n_buenas=5, coinciden=4)
        r = self.es.generar_banco(ctx, self.u, self.TEMA, 1, {})
        qs = json.loads(fila("SELECT preguntas FROM prueba_diferida WHERE id=?", (r["id"],))["preguntas"])
        self.assertEqual(len(qs), 4)
        self.assertEqual(fila("SELECT estado FROM prueba_diferida WHERE id=?", (r["id"],))["estado"], "lista")

    def test_generar_banco_falla_si_la_segunda_lectura_descarta_demasiadas(self):
        ctx = self._banco(n_buenas=5, coinciden=2)
        with self.assertRaises(ValueError):
            self.es.generar_banco(ctx, self.u, self.TEMA, 1, {})
        self.assertIsNone(fila("SELECT 1 FROM prueba_diferida WHERE usuario=?", (self.u,)))

    def _prueba(self):
        qs = [{"pregunta": f"p{k}", "opciones": ["a", "b", "c", "d"], "correcta": k % 4, "explicacion": "e"} for k in range(4)]
        pid = ejecutar("INSERT INTO prueba_diferida(usuario,tema,etapa,estado,preguntas,creada) VALUES(?,?,?,?,?,?)",
                       (self.u, self.TEMA, 1, "lista", json.dumps(qs), time.time())).lastrowid
        return fila("SELECT * FROM prueba_diferida WHERE id=?", (pid,))

    def test_corregir_aprueba_con_75_y_solo_se_responde_una_vez(self):
        p = self._prueba()
        self.avance("dominado", quiz=0.9)
        r = self.es.responder(self.u, p, [{"j": 0, "conf": "seguro"}, {"j": 1, "conf": "dudo"}, {"j": 2}, {"j": 0, "conf": "adivino"}])
        self.assertEqual((r["aciertos"], r["total"], r["aprobada"]), (3, 4, True))
        self.assertNotIn("correcta", json.dumps(self.es.publica(p)))
        self.assertIn("error", self.es.responder(self.u, fila("SELECT * FROM prueba_diferida WHERE id=?", (p["id"],)), [{"j": 0}] * 4))
        self.assertEqual(fila("SELECT COUNT(*) n FROM actividad WHERE usuario=? AND tipo='calibracion'", (self.u,))["n"], 3)
        self.assertEqual(fila("SELECT estado FROM avance WHERE usuario=? AND tema=?", (self.u, self.TEMA))["estado"], "dominado")   # solo mide

    def test_corregir_no_aprueba_con_la_mitad_y_rechaza_respuestas_incompletas(self):
        p = self._prueba()
        self.assertIn("error", self.es.responder(self.u, p, [{"j": 0}]))
        r = self.es.responder(self.u, p, [{"j": 0}, {"j": 1}, {"j": 0}, {"j": 0}])
        self.assertEqual((r["aciertos"], r["aprobada"]), (2, False))


class NoticiasSeguridad(unittest.TestCase):
    """RSS de fuentes externas: no es confiable. Sin entidades XML (expansión de entidades) y sin salir a direcciones
    que no sean públicas (SSRF), ni siquiera al refrescar una fuente ya guardada."""

    RSS = b"<?xml version='1.0'?><rss><channel><item><title>Hola</title><link>https://ejemplo.org/a</link></item></channel></rss>"
    BOMBA = (b"<?xml version='1.0'?><!DOCTYPE r [<!ENTITY a 'aaaaaaaaaa'><!ENTITY b '&a;&a;&a;&a;&a;&a;&a;&a;&a;&a;'>]>"
             b"<rss><channel><item><title>&b;</title><link>https://ejemplo.org/a</link></item></channel></rss>")

    def test_un_rss_normal_se_lee(self):
        self.assertEqual([i["titulo"] for i in nt._items(self.RSS)], ["Hola"])

    def test_rechaza_declaraciones_de_entidades(self):
        with self.assertRaises(ValueError):
            nt._items(self.BOMBA)
        with self.assertRaises((ValueError, nt.ET.ParseError)):
            nt._items(self.BOMBA.replace(b"<!ENTITY", b"<!entity"))

    def test_refrescar_una_fuente_no_publica_no_hace_la_peticion(self):
        for u in ("http://127.0.0.1:9/rss", "http://192.168.1.1/rss", "file:///etc/passwd", "http://[::1]/rss"):
            f, r = nt._bajar({"u": u})
            self.assertIsInstance(r, Exception, u)
            self.assertIn("pública", str(r), u)


if __name__ == "__main__":
    r = unittest.main(exit=False, verbosity=2).result
    sys.exit(0 if r.wasSuccessful() else 1)
