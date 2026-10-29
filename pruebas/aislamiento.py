#!/usr/bin/env python3
"""Pruebas del entorno aislado de la práctica con código (`app/ejecucion.py`): corren código HOSTIL de verdad dentro del
aislamiento y comprueban que el servidor sigue respondiendo, que la memoria queda acotada y que no sobrevive ningún proceso.

Necesitan bubblewrap, systemd-run y una sesión de usuario de systemd (como la del servicio): si no están, se omiten.
Uso: python3 pruebas/aislamiento.py   (como el usuario que corre la Academia, con XDG_RUNTIME_DIR definido)"""
import os
import subprocess
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
import config  # noqa: E402
import ejecucion as ej  # noqa: E402

config.C["practica_codigo"] = True
OK, MOTIVO = ej.disponible()


def correr(codigo, casos=None, funcion="f"):
    casos = casos or [{"args": [2], "esperado": 4}]
    t = time.time()
    r = ej._correr(codigo, funcion, casos)
    return r, time.time() - t


@unittest.skipUnless(OK, f"sin entorno aislado: {MOTIVO}")
class Aislamiento(unittest.TestCase):
    def test_una_solucion_correcta_pasa_y_una_incorrecta_no(self):
        r, _ = correr("def f(x):\n    return x * 2\n")
        self.assertTrue(r["casos"][0]["ok"])
        r, _ = correr("def f(x):\n    return x + 3\n")
        self.assertFalse(r["casos"][0]["ok"])
        self.assertEqual(r["casos"][0]["obtenido"], 5)

    def test_errores_del_codigo_se_explican_sin_tumbar_nada(self):
        r, _ = correr("def f(x:\n    return x\n")
        self.assertIn("SyntaxError", r["error_carga"])
        r, _ = correr("def g(x):\n    return x\n")
        self.assertIn("No se encontró la función", r["error_carga"])
        r, _ = correr("def f(x):\n    return 1 / 0\n")
        self.assertIn("ZeroDivisionError", r["casos"][0]["error"])

    def test_bucle_infinito_se_corta_por_caso(self):
        r, t = correr("def f(x):\n    while True:\n        pass\n", [{"args": [1], "esperado": 1}, {"args": [2], "esperado": 2}])
        self.assertTrue(all("2 segundos" in c["error"] for c in r["casos"]))
        self.assertLess(t, ej.TIEMPO_TOTAL + 3)

    def test_bucle_que_atrapa_la_alarma_se_mata_por_fuera(self):
        r, t = correr("def f(x):\n    while True:\n        try:\n            while True: pass\n        except BaseException:\n            pass\n")
        self.assertIn("error", r)
        self.assertLess(t, ej.TIEMPO_TOTAL + 4)

    def test_memoria_acotada(self):
        r, t = correr("def f(x):\n    a = bytearray(2 * 1024 ** 3)\n    return len(a)\n")
        self.assertTrue(r.get("error") or not r["casos"][0]["ok"], r)
        self.assertLess(t, ej.TIEMPO_TOTAL + 3)

    def test_bomba_de_procesos_acotada(self):
        codigo = ("import os\ndef f(x):\n    n = 0\n    try:\n        for _ in range(500):\n            if os.fork() == 0:\n"
                  "                import time; time.sleep(30); os._exit(0)\n            n += 1\n    except OSError:\n        pass\n    return n\n")
        r, t = correr(codigo)
        self.assertLess(t, ej.TIEMPO_TOTAL + 4)
        if r.get("casos"):
            self.assertLessEqual(r["casos"][0].get("obtenido", 0) or 0, ej.TAREAS)
        time.sleep(1)
        self.assertNotEqual(subprocess.run(["pgrep", "-f", "academia-codigo-"], capture_output=True).returncode, 0, "quedaron procesos")

    def test_llenar_tmp_no_toca_el_disco_del_servidor(self):
        codigo = ("def f(x):\n    try:\n        with open('/tmp/x', 'wb') as a:\n            for _ in range(2000):\n"
                  "                a.write(b'x' * 1024 * 1024)\n    except OSError as e:\n        return 'lleno'\n    return 'sin limite'\n")
        r, _ = correr(codigo, [{"args": [1], "esperado": "lleno"}])
        self.assertTrue(r["casos"][0]["ok"], r)

    def test_inundar_la_salida_la_corta(self):
        r, t = correr("import os\ndef f(x):\n    while True:\n        os.write(1, b'x' * 65536)\n")
        self.assertIn("demasiado", r.get("error", ""))
        self.assertLess(t, ej.TIEMPO_TOTAL)

    def test_imprimir_mucho_se_recorta(self):
        r, _ = correr("def f(x):\n    print('a' * 100000)\n    return x * 2\n")
        self.assertTrue(r["casos"][0]["ok"])
        self.assertLess(len(r["salida"]), 7000)

    def test_hijo_dormido_no_sobrevive(self):
        r, t = correr("import subprocess\ndef f(x):\n    subprocess.Popen(['sleep', '60'])\n    return x * 2\n")
        self.assertTrue(r["casos"][0]["ok"], r)
        self.assertLess(t, 6)
        time.sleep(1)
        self.assertNotEqual(subprocess.run(["pgrep", "-f", "sleep 60"], capture_output=True).returncode, 0, "sobrevivió el hijo")

    def test_sin_red_ni_archivos_del_usuario(self):
        codigo = ("import socket, os\ndef f(x):\n    out = []\n    try:\n        socket.create_connection(('1.1.1.1', 53), timeout=2); out.append('red')\n"
                  "    except Exception:\n        pass\n    for ruta in ('/etc/passwd', os.path.expanduser('~/.bashrc'), '/home'):\n"
                  "        try:\n            os.listdir(ruta) if ruta == '/home' else open(ruta).read(); out.append(ruta)\n        except Exception:\n            pass\n"
                  "    out += [k for k in os.environ if k in ('HOME', 'USER', 'XDG_RUNTIME_DIR', 'DBUS_SESSION_BUS_ADDRESS')]\n    return out\n")
        r, _ = correr(codigo, [{"args": [1], "esperado": []}])
        self.assertTrue(r["casos"][0]["ok"], r)

    def test_un_eq_propio_no_hace_pasar_los_casos(self):
        codigo = "class Trampa:\n    def __eq__(self, o): return True\ndef f(x):\n    return Trampa()\n"
        r, _ = correr(codigo)
        self.assertFalse(r["casos"][0]["ok"])

    def test_comparacion_distingue_tipos(self):
        r, _ = correr("def f(x):\n    return True\n", [{"args": [1], "esperado": 1}])
        self.assertFalse(r["casos"][0]["ok"])                       # True no es 1
        r, _ = correr("def f(x):\n    return 0.1 + 0.2\n", [{"args": [1], "esperado": 0.3}])
        self.assertTrue(r["casos"][0]["ok"])                        # los decimales se comparan con tolerancia
        r, _ = correr("def f(x):\n    return [3, 1, 2]\n", [{"args": [1], "esperado": [1, 2, 3], "ordenar": True}])
        self.assertTrue(r["casos"][0]["ok"])

    def test_la_validacion_descarta_ejercicios_malos(self):
        def bueno():
            return {"funcion": "f", "plantilla": "def f(x):\n    pass\n", "solucion": "def f(x):\n    return x * 2\n",
                    "casos": [{"args": [k], "esperado": k * 2} for k in range(1, 9)]}
        ej_ok = bueno()
        self.assertEqual(ej.validar(ej_ok), (True, ""))
        self.assertEqual(len(ej_ok["casos"]), 8)
        mala_solucion = dict(bueno(), solucion="def f(x):\n    return x\n")
        self.assertIn("solo coincide", ej.validar(mala_solucion)[1])
        plantilla_resuelta = dict(bueno(), plantilla=bueno()["solucion"])
        self.assertIn("no pide nada", ej.validar(plantilla_resuelta)[1])
        self.assertFalse(ej.validar(dict(bueno(), casos=bueno()["casos"][:3]))[0])
        self.assertFalse(ej.validar(dict(bueno(), solucion="def f(x:\n"))[0])

    def test_un_caso_con_esperado_equivocado_se_descarta_y_el_resto_se_conserva(self):
        e = {"funcion": "f", "plantilla": "def f(x):\n    pass\n", "solucion": "def f(x):\n    return x * 2\n",
             "casos": [{"args": [k], "esperado": k * 2} for k in range(1, 9)]}
        e["casos"][3]["esperado"] = 999          # la IA se equivocó en uno: dos derivaciones no coinciden
        self.assertEqual(ej.validar(e), (True, ""))
        self.assertEqual(len(e["casos"]), 7)
        self.assertNotIn(999, [c["esperado"] for c in e["casos"]])
        e2 = {"funcion": "f", "plantilla": "def f(x):\n    pass\n", "solucion": "def f(x):\n    return x * 2\n",
              "casos": [{"args": [k], "esperado": k * 2 if k < 4 else -1} for k in range(1, 9)]}
        self.assertFalse(ej.validar(e2)[0])      # demasiados desacuerdos: no se fía de ninguno

    def test_dos_corridas_de_la_misma_persona_no_se_pisan(self):
        import threading
        res = []
        h = threading.Thread(target=lambda: res.append(ej.correr("ana", "def f(x):\n    import time; time.sleep(1.5)\n    return x * 2\n", "f", [{"args": [2], "esperado": 4}])))
        h.start()
        time.sleep(0.4)
        otra = ej.correr("ana", "def f(x):\n    return x * 2\n", "f", [{"args": [2], "esperado": 4}])
        h.join()
        self.assertIn("en curso", otra.get("error", ""))
        self.assertTrue(res[0]["casos"][0]["ok"])
        self.assertTrue(ej.correr("beto", "def f(x):\n    return x * 2\n", "f", [{"args": [2], "esperado": 4}])["casos"][0]["ok"])

    def test_apagada_por_configuracion_no_ejecuta_nada(self):
        config.C["practica_codigo"] = False
        try:
            r = ej.correr("ana", "def f(x):\n    return x\n", "f", [{"args": [1], "esperado": 1}])
            self.assertTrue(r.get("apagada"))
        finally:
            config.C["practica_codigo"] = True

    def test_sin_bwrap_no_cae_a_ejecutar_sin_aislar(self):
        original = ej._herramientas
        ej._herramientas = lambda: (None, "/usr/bin/systemd-run", "/usr/bin/python3")
        ej._AUTOPRUEBA["hasta"] = 0
        try:
            ok, motivo = ej.disponible()
            self.assertFalse(ok)
            self.assertIn("bubblewrap", motivo)
            self.assertTrue(ej.correr("ana", "def f(x):\n    return x\n", "f", [{"args": [1], "esperado": 1}]).get("apagada"))
        finally:
            ej._herramientas = original
            ej._AUTOPRUEBA["hasta"] = 0


if __name__ == "__main__":
    r = unittest.main(exit=False, verbosity=2).result
    sys.exit(0 if r.wasSuccessful() else 1)
