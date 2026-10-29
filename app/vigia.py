"""Vigía de la Academia: un proceso APARTE del servicio que avisa cuando algo falla.

Tiene que vivir fuera del servicio: si el servicio se cae, él mismo no podría avisar. Se ejecuta cada pocos minutos
(un temporizador de systemd, un cron o a mano), consulta `/api/salud` y, si hay un problema nuevo, lo manda por el
canal que se le indique. Sin dependencias.

    python3 vigia.py                   una comprobación (lo normal, desde el temporizador)
    python3 vigia.py --probar          manda un mensaje de prueba por el canal y termina
    python3 vigia.py --pausar [motivo] silencia la alarma de «servicio caído» (parada a propósito)
    python3 vigia.py --reanudar        quita la pausa

Canal de aviso: la variable `ACADEMIA_ALARMA_CMD` es un programa que recibe el texto por la entrada estándar
(p. ej. un script que lo mande por Telegram, ntfy o correo). Sin ella, el aviso solo queda en el registro y el
código de salida es 2 mientras haya un problema, de modo que cualquier supervisor externo también lo puede leer.

Reglas para no molestar de más:
* «servicio caído» solo se avisa tras 2 comprobaciones seguidas fallidas (un reinicio normal tarda segundos);
* cada problema se avisa una vez, se recuerda cada 6 h si sigue y se avisa cuando se recupera;
* si la pausa está puesta, no se avisa de la caída, y se quita sola en cuanto el servicio responde.
"""
import json
import os
import shlex
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
DATOS = Path(os.environ.get("ACADEMIA_DATOS") or RAIZ / "datos")
URL = os.environ.get("ACADEMIA_URL_VIGIA") or f"http://127.0.0.1:{os.environ.get('ACADEMIA_PUERTO', '8092')}"
ESTADO = DATOS / "vigia.json"
PAUSA = DATOS / "vigia_pausa"
FALLOS_PARA_ALARMA = 2
RECORDAR_CADA = 6 * 3600


def leer_estado():
    try:
        return json.loads(ESTADO.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"fallos": 0, "avisados": {}}


def guardar_estado(e):
    ESTADO.parent.mkdir(parents=True, exist_ok=True)
    tmp = ESTADO.with_suffix(".tmp")
    tmp.write_text(json.dumps(e, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, ESTADO)


def consultar(url=None, timeout=15):
    """(foto, error): la respuesta de `/api/salud` o por qué no se pudo obtener."""
    try:
        with urllib.request.urlopen((url or URL) + "/api/salud", timeout=timeout) as r:
            return json.loads(r.read()), None
    except urllib.error.HTTPError as e:
        return None, f"HTTP {e.code}"
    except Exception as e:  # noqa: BLE001 - sin conexión, tiempo agotado, JSON roto: todo cuenta como «no responde»
        return None, f"{type(e).__name__}: {e}"[:160]


def decidir(estado, foto, error, ahora, pausado=False):
    """Núcleo sin efectos (se prueba aparte). Devuelve (estado_nuevo, mensajes) con los mensajes a enviar ahora."""
    e = {"fallos": estado.get("fallos", 0), "avisados": dict(estado.get("avisados", {}))}
    msgs = []
    if foto is None:
        e["fallos"] += 1
        activos = {}
        if e["fallos"] >= FALLOS_PARA_ALARMA and not pausado:
            activos["servicio_caido"] = ("alta", f"La Academia no responde desde hace {e['fallos']} comprobaciones ({error}).")
    else:
        e["fallos"] = 0
        activos = {p["id"]: (p["gravedad"], p["texto"]) for p in foto.get("problemas", [])}
    for id_, (grav, texto) in activos.items():
        previo = e["avisados"].get(id_)
        if previo is None or (grav == "alta" and ahora - previo["cuando"] >= RECORDAR_CADA):
            msgs.append(f"{'🔴' if grav == 'alta' else '🟠'} Academia: {texto}"
                        + ("" if previo is None else " (sigue sin resolverse)"))
            e["avisados"][id_] = {"cuando": ahora, "gravedad": grav, "texto": texto}
    # En una caída no se puede saber si los demás problemas siguen: no se declaran recuperados.
    if foto is not None:
        for id_ in [k for k in e["avisados"] if k not in activos]:
            msgs.append(f"✅ Academia: se resolvió — {e['avisados'][id_]['texto']}")
            del e["avisados"][id_]
    elif pausado:
        e["avisados"].pop("servicio_caido", None)
    return e, msgs


def enviar(texto):
    """Entrega el aviso por el canal configurado. Devuelve True si se entregó."""
    cmd = os.environ.get("ACADEMIA_ALARMA_CMD", "").strip()
    print(texto, flush=True)
    if not cmd:
        return False
    try:
        r = subprocess.run(shlex.split(cmd), input=texto, text=True, capture_output=True, timeout=60)
    except (OSError, subprocess.TimeoutExpired) as ex:
        print(f"no se pudo entregar el aviso: {ex}", file=sys.stderr)
        return False
    if r.returncode != 0:
        print(f"el canal de aviso devolvió {r.returncode}: {r.stderr.strip()[:200]}", file=sys.stderr)
    return r.returncode == 0


def comprobar(ahora=None):
    ahora = ahora or time.time()
    foto, error = consultar()
    pausado = PAUSA.exists()
    if foto is not None and pausado:
        PAUSA.unlink(missing_ok=True)      # el servicio volvió: la pausa ya cumplió su función
        pausado = False
    estado, msgs = decidir(leer_estado(), foto, error, ahora, pausado)
    sin_entregar = []
    for m in msgs:
        if not enviar(m):
            sin_entregar.append(m)
    if sin_entregar and os.environ.get("ACADEMIA_ALARMA_CMD"):
        # el canal falló: no damos el aviso por hecho, se reintenta en la próxima comprobación
        for id_, v in list(estado["avisados"].items()):
            if any(v["texto"] in m for m in sin_entregar):
                del estado["avisados"][id_]
    guardar_estado(estado)
    return 2 if estado["avisados"] else 0


def main(argv):
    if "--pausar" in argv:
        i = argv.index("--pausar")
        motivo = " ".join(argv[i + 1:]) or "parada a propósito"
        PAUSA.parent.mkdir(parents=True, exist_ok=True)
        PAUSA.write_text(f"{motivo}\n{time.strftime('%Y-%m-%d %H:%M')}\n", encoding="utf-8")
        print(f"Pausa puesta: {motivo}. Se quita sola cuando el servicio responda.")
        return 0
    if "--reanudar" in argv:
        PAUSA.unlink(missing_ok=True)
        print("Pausa quitada.")
        return 0
    if "--probar" in argv:
        return 0 if enviar("✅ Academia: mensaje de prueba del vigía. Si lo lees, la alarma funciona.") else 1
    return comprobar()


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
