"""Pruebas de la fase F0 (salud, diario de la cola, línea base y vigía). Se corren aparte de `unidad.py` para no
tocar el mismo archivo que otras ventanas de trabajo: `python3 pruebas/unidad_salud.py`. Usan una carpeta temporal."""
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace

RAIZ = Path(__file__).resolve().parent.parent
_TMP = tempfile.TemporaryDirectory()
os.environ["ACADEMIA_DATOS"] = _TMP.name
sys.path.insert(0, str(RAIZ / "app"))

import base  # noqa: E402
base.iniciar()
import salud  # noqa: E402
import vigia  # noqa: E402
from base import ejecutar, kv_get  # noqa: E402

salud.iniciar_tabla()
U = "persona@prueba"
H = 3600


def tarea(id_, tipo="leccion", usuario=U, etiqueta="tema.1", prioridad=1):
    return SimpleNamespace(id=id_, tipo=tipo, usuario=usuario, etiqueta=etiqueta, prioridad=prioridad, creado=time.time())


class Evaluar(unittest.TestCase):
    def test_foto_sana_no_da_problemas(self):
        ahora = time.time()
        f = {"ahora": ahora, "diaria": {"programada": ahora - H, "ultima": ahora - H + 5},
             "cola": salud.resumen_cola([], ahora), "sistema": {"gpu": {"temp": 60}}, "disco_libre_gb": 200}
        self.assertEqual(salud.evaluar(f), [])
        self.assertEqual(salud.evaluar({}), [])                      # lo que no se mide no se inventa

    def test_rutina_diaria_atrasada_y_con_fallo(self):
        ahora = time.time()
        f = {"ahora": ahora, "diaria": {"programada": ahora - 5 * H, "ultima": ahora - 30 * H}}
        self.assertEqual([p["id"] for p in salud.evaluar(f)], ["diaria_atrasada"])
        f["inicio_servicio"] = ahora - 30                                   # recién arrancado: la diaria empieza sola
        self.assertEqual(salud.evaluar(f), [])
        f["inicio_servicio"] = ahora - 600
        self.assertEqual([p["id"] for p in salud.evaluar(f)], ["diaria_atrasada"])
        f["diaria"] = {"programada": ahora - 1 * H, "ultima": ahora - 30 * H}   # dentro de la gracia de 3 h
        self.assertEqual(salud.evaluar(f), [])
        f["diaria"] = {"programada": ahora - H, "ultima": ahora - H, "error": "ValueError: x"}
        self.assertEqual(salud.evaluar(f)[0]["id"], "diaria_fallo")

    def test_cola_gpu_ia_y_disco(self):
        ahora = time.time()
        trabajos = [{"tipo": "leccion", "estado": "corriendo", "creado": ahora - 5 * H, "inicio": ahora - 4 * H},
                    {"tipo": "sintesis", "estado": "cola", "creado": ahora - H},
                    {"tipo": "ruta", "estado": "cola", "creado": ahora - 2 * H}]
        trabajos += [{"tipo": "x", "estado": "error", "terminado": ahora - H, "creado": ahora - 2 * H}] * 5
        c = salud.resumen_cola(trabajos, ahora, perdidos=2)
        self.assertEqual((c["en_cola"], c["corriendo"], c["fallidos_24h"]), (2, 1, 5))
        self.assertEqual(c["pendientes_por_tipo"], {"leccion": 1, "sintesis": 1, "ruta": 1})
        ids = {p["id"]: p["gravedad"] for p in salud.evaluar({
            "ahora": ahora, "cola": c, "sistema": {"gpu": {"temp": 86}}, "disco_libre_gb": 2,
            "ia": {"alcanzable": False}})}
        self.assertEqual(ids, {"cola_colgada": "alta", "cola_fallos": "media", "cola_perdidos": "media",
                               "gpu_temp": "alta", "disco": "alta", "ia_caida": "alta"})
        orden = [p["gravedad"] for p in salud.evaluar({"ahora": ahora, "cola": c, "disco_libre_gb": 2})]
        self.assertEqual(orden, sorted(orden, key=["alta", "media", "baja"].index))   # lo grave primero


class DiarioDeLaCola(unittest.TestCase):
    def setUp(self):
        ejecutar("DELETE FROM cola_diario")

    def test_anotar_y_cerrar(self):
        a, b = tarea("a"), tarea("b")
        salud.anotar(a); salud.anotar(b)
        self.assertEqual(base.fila("SELECT COUNT(*) n FROM cola_diario")["n"], 2)
        salud.cerrar(a)
        self.assertEqual([r["id"] for r in base.filas("SELECT id FROM cola_diario")], ["b"])

    def test_reinicio_recupera_y_reporta_lo_perdido(self):
        # antes de matar el servicio: dos de fondo (reconstruibles) y una pregunta del tutor que alguien esperaba
        for t in (tarea("1", "leccion", etiqueta="mat.1"), tarea("2", "sintesis", None, "dia"),
                  tarea("3", "tutor", U, "hilo-9", 0)):
            salud.anotar(t)
        self.assertEqual(salud.al_arrancar(), 3)                     # al arrancar se leen y se vacía el diario
        self.assertEqual(base.fila("SELECT COUNT(*) n FROM cola_diario")["n"], 0)
        # reanudar() logra volver a encolar las dos de fondo, no el tutor
        ahora = [{"tipo": "leccion", "usuario": U, "etiqueta": "mat.1", "estado": "cola"},
                 {"tipo": "sintesis", "usuario": None, "etiqueta": "dia", "estado": "corriendo"}]
        inf = salud.conciliar(ahora)
        self.assertEqual((inf["antes"], inf["recuperadas"], len(inf["perdidas"])), (3, 2, 1))
        self.assertEqual([x["tipo"] for x in salud.perdidos_visibles()], ["tutor"])
        self.assertEqual(salud.perdidos_visibles("otra@persona"), [])        # cada perfil ve solo lo suyo
        self.assertTrue(any(p["id"] == "cola_perdidos" for p in salud.evaluar(
            {"cola": salud.resumen_cola([], perdidos=len(salud.perdidos_visibles()))})))
        self.assertEqual(salud.conciliar([])["antes"], 0)            # solo se concilia una vez por arranque

    def test_gancho_de_ia(self):
        import ia
        vistos = []
        ia.ganchos.update(poner=lambda t: vistos.append(("poner", t.tipo)), fin=lambda t: vistos.append(("fin", t.tipo)))
        try:
            t = ia.Trabajo("prueba_f0", lambda ctx: 7, 0, U, "x")   # prioridad 0: no espera a otros modelos del equipo
            ia.cola.poner(t)                    # el trabajador de la cola (hilo de ia.py) la corre solo
            for _ in range(100):
                if t.terminado:
                    break
                time.sleep(0.05)
            self.assertEqual((vistos, t.resultado), ([("poner", "prueba_f0"), ("fin", "prueba_f0")], 7))
            self.assertIsNotNone(t.inicio)
        finally:
            ia.ganchos.update(poner=None, fin=None)


class RutinaDiaria(unittest.TestCase):
    def test_anota_inicio_fin_y_error(self):
        salud.correr_diaria(lambda: None)
        d = kv_get("salud_diaria")
        self.assertTrue(d["inicio"] and d["fin"] and d["error"] is None)
        with self.assertRaises(ZeroDivisionError):
            salud.correr_diaria(lambda: 1 / 0)
        d = kv_get("salud_diaria")
        self.assertIn("ZeroDivisionError", d["error"])
        self.assertTrue(any(p["id"] == "diaria_fallo" for p in salud.evaluar({"diaria": d})))


class LineaBase(unittest.TestCase):
    def test_foto_y_base_fija(self):
        ahora = time.time()
        for k in range(3):   # 3 días con 30 min de estudio
            ejecutar("INSERT INTO actividad(usuario,tipo,valor,fecha) VALUES(?,?,?,?)", (U, "tiempo", 1800, ahora - k * 86400))
        ejecutar("INSERT INTO avance(usuario,tema,estado) VALUES(?,?,?)", (U, "t.1", "dominado"))
        ejecutar("INSERT INTO avance(usuario,tema,estado) VALUES(?,?,?)", (U, "t.2", "visto"))
        f = salud.foto_uso(U, ahora)
        self.assertEqual(f["minutos_14d"]["valor"], 90)
        self.assertEqual(f["dias_activos_14d"]["valor"], 3)
        self.assertEqual(f["minutos_por_dia_activo_14d"]["valor"], 30.0)
        self.assertEqual(f["temas_dominados"]["valor"], 1)
        self.assertEqual(f["minutos_por_tema_dominado"]["valor"], 90)
        self.assertTrue(all("origen" in v for k, v in f.items() if k != "fecha"))      # toda métrica dice de dónde sale
        b1 = salud.linea_base(U)["base"]
        ejecutar("INSERT INTO actividad(usuario,tipo,valor,fecha) VALUES(?,?,?,?)", (U, "tiempo", 6000, ahora))
        r = salud.linea_base(U)
        self.assertEqual(r["base"], b1)                                              # la base no se mueve
        self.assertGreater(r["ahora"]["minutos_14d"]["valor"], b1["minutos_14d"]["valor"])
        self.assertIsNone(salud.linea_base("nadie@x", crear=False)["base"])            # crear=False no escribe
        self.assertIsNone(kv_get("linea_base:nadie@x"))
        otra = salud.linea_base("otra@persona")["base"]
        self.assertEqual(otra["minutos_14d"]["valor"], 0)                              # perfiles independientes


class Vigia(unittest.TestCase):
    def test_caida_avisa_a_la_segunda_comprobacion_una_sola_vez(self):
        e, m = vigia.decidir({}, None, "refused", 1000)
        self.assertEqual(m, [])                                      # una sola falla: puede ser un reinicio normal
        e, m = vigia.decidir(e, None, "refused", 1120)
        self.assertEqual(len(m), 1)
        self.assertIn("no responde", m[0])
        e, m = vigia.decidir(e, None, "refused", 1240)
        self.assertEqual(m, [])                                      # no repite
        e, m = vigia.decidir(e, None, "refused", 1240 + 7 * H)
        self.assertEqual(len(m), 1)                                  # recordatorio a las 6 h
        self.assertIn("sigue sin resolverse", m[0])
        e, m = vigia.decidir(e, {"problemas": []}, None, 1240 + 8 * H)
        self.assertEqual(len(m), 1)
        self.assertIn("se resolvió", m[0])
        self.assertEqual(e["avisados"], {})

    def test_pausa_silencia_la_caida_y_problemas_nuevos_se_avisan(self):
        e, m = vigia.decidir({"fallos": 5}, None, "refused", 10, pausado=True)
        self.assertEqual(m, [])
        foto = {"problemas": [{"id": "gpu_temp", "gravedad": "media", "texto": "La GPU está a 81 °C."}]}
        e, m = vigia.decidir(e, foto, None, 20)
        self.assertEqual(len(m), 1)
        self.assertIn("81", m[0])
        e, m = vigia.decidir(e, foto, None, 30)
        self.assertEqual(m, [])                                      # media no se recuerda cada 6 h

    def test_caida_no_declara_recuperado_lo_que_no_puede_ver(self):
        e, _ = vigia.decidir({}, {"problemas": [{"id": "disco", "gravedad": "alta", "texto": "poco disco"}]}, None, 5)
        e, m = vigia.decidir(e, None, "refused", 10)
        e, m = vigia.decidir(e, None, "refused", 20)
        self.assertTrue(all("se resolvió" not in x for x in m))
        self.assertIn("disco", e["avisados"])

    def test_consultar_sin_servicio_devuelve_error(self):
        foto, err = vigia.consultar("http://127.0.0.1:9", timeout=2)
        self.assertIsNone(foto)
        self.assertTrue(err)


if __name__ == "__main__":
    r = unittest.main(exit=False, verbosity=2).result
    sys.exit(0 if r.wasSuccessful() else 1)
