"""Pruebas de la validación de salidas JSON de la IA (`ia.errores_esquema`): `python3 pruebas/unidad_esquema.py`.

Regresión 2026-11-18: una prueba de nivel de Ciberseguridad llegó con la clave «opplicaciones» en vez de
«opciones» (el esquema solo viajaba en el texto del mensaje) y el navegador mostraba
«Cannot read properties of undefined (reading 'map')»."""
import os
import sys
import tempfile
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
_TMP = tempfile.TemporaryDirectory()
os.environ["ACADEMIA_DATOS"] = _TMP.name
sys.path.insert(0, str(RAIZ / "app"))

import base  # noqa: E402
base.iniciar()
import ia  # noqa: E402
from lecciones import esquema_prueba  # noqa: E402


def pregunta(**kw):
    p = {"tema": 0, "pregunta": "¿?", "opciones": ["a", "b", "c", "d"], "correcta": 1, "explicacion": "x"}
    p.update(kw)
    return p


class Esquema(unittest.TestCase):
    def test_salida_correcta_no_tiene_errores(self):
        self.assertEqual(ia.errores_esquema({"preguntas": [pregunta(), pregunta()]}, esquema_prueba(1)), [])

    def test_clave_mal_escrita_se_detecta(self):
        mala = pregunta()
        mala["opplicaciones"] = mala.pop("opciones")
        err = ia.errores_esquema({"preguntas": [pregunta(), mala]}, esquema_prueba(1))
        self.assertTrue(any("opciones" in e for e in err), err)

    def test_tipos_rangos_y_cantidades(self):
        e = esquema_prueba(1)
        self.assertTrue(ia.errores_esquema({"preguntas": [pregunta()]}, e))                       # faltan preguntas
        self.assertTrue(ia.errores_esquema({"preguntas": [pregunta(), pregunta(correcta=7)]}, e))   # fuera de rango
        self.assertTrue(ia.errores_esquema({"preguntas": [pregunta(), pregunta(opciones=["a"])]}, e))
        self.assertTrue(ia.errores_esquema({"preguntas": [pregunta(), pregunta(correcta="1")]}, e))
        self.assertTrue(ia.errores_esquema([], e))

    def test_reintenta_si_no_cumple_y_falla_claro(self):
        llamadas = []

        def _chat(self, mensajes, *a, **k):
            llamadas.append(1)
            return {"preguntas": []}
        ctx = object.__new__(type("C", (), {"chat": ia.Contexto.chat, "_chat": _chat,
                                            "fase": lambda self, x: None, "t": type("T", (), {"fase": ""})()}))
        with self.assertRaises(ValueError):
            ctx.chat([{"role": "user", "content": "x"}], esquema=esquema_prueba(1))
        self.assertEqual(len(llamadas), 2)


class Latex(unittest.TestCase):
    def test_escapes_latex_fuera_de_la_lista(self):
        # tal como lo escribe el modelo: una sola barra delante de cada comando de LaTeX
        crudo = '{"a":"$' + chr(92) + 'alpha$ ' + chr(92) + '_ ' + chr(92) + '{x' + chr(92) + '} 5' + chr(92) + '% $' + chr(92) + 'hbar$ $' + chr(92) + 'uparrow$"}'
        esperado = "$" + chr(92) + "alpha$ " + chr(92) + "_ " + chr(92) + "{x" + chr(92) + "} 5" + chr(92) + "% $" + chr(92) + "hbar$ $" + chr(92) + "uparrow$"
        self.assertEqual(ia.parsear_json(crudo)["a"], esperado)

    def test_escapes_json_validos_se_respetan(self):
        self.assertEqual(ia.parsear_json('{"a":"l\\nb \\"c\\" \\u00e9"}')["a"], 'l\nb "c" é')

    def test_texto_alrededor_y_basura(self):
        self.assertEqual(ia.parsear_json('Aquí va: {"a": 1} listo'), {"a": 1})
        with self.assertRaises(ValueError):
            ia.parsear_json("sin json")


if __name__ == "__main__":
    r = unittest.main(exit=False, verbosity=2).result
    sys.exit(0 if r.wasSuccessful() else 1)
