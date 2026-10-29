"""Claves y fichas secretas de esta instalación (API de IA, bot de Telegram).

Viven en datos/secretos.json, aparte de la configuración, con permiso 600, y NUNCA se devuelven por la API ni se
escriben en el registro: la interfaz solo sabe si hay una y cómo termina («…a1b2»).
"""
import json
import threading

import config

ARCHIVO = config.DATOS / "secretos.json"
_candado = threading.Lock()


def _leer():
    try:
        return json.loads(ARCHIVO.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def obtener(grupo, nombre=""):
    """Valor guardado (cadena vacía si no hay). `grupo` p. ej. «claves_ia»; `nombre` p. ej. el proveedor."""
    v = _leer().get(grupo, "")
    if isinstance(v, dict):
        return v.get(nombre, "")
    return v or ""


def guardar(grupo, valor, nombre=""):
    with _candado:
        d = _leer()
        if nombre:
            d.setdefault(grupo, {})
            if not isinstance(d[grupo], dict):
                d[grupo] = {}
            if valor:
                d[grupo][nombre] = valor
            else:
                d[grupo].pop(nombre, None)
        elif valor:
            d[grupo] = valor
        else:
            d.pop(grupo, None)
        ARCHIVO.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
        config.privado(ARCHIVO)


def pista(valor):
    """«…a1b2» para mostrar que hay una clave sin revelarla."""
    return ("…" + valor[-4:]) if valor and len(valor) >= 8 else ("…" if valor else "")
