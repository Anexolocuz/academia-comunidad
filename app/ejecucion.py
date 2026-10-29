"""💻 Práctica de código: ejercicios de Python que se corrigen EJECUTANDO tu código contra casos de prueba.

Es verificación objetiva: no depende de que una IA «opine» sobre tu solución. Dos piezas:

1. Un **ejercicio** lo escribe la IA como datos (enunciado, nombre de la función, plantilla, solución de referencia y casos con
   argumentos y resultado esperado en JSON). Nunca se ejecuta código escrito por la IA fuera del entorno aislado, y antes de
   mostrarlo se comprueba (`validar`): solo sobreviven los casos donde el «esperado» de la IA y el resultado real de su solución
   coinciden (dos derivaciones independientes), deben quedar al menos 6 y la plantilla vacía debe fallar alguno.
2. Tu código corre en un **entorno aislado** (`correr`): bubblewrap sin red, sin tu carpeta personal ni `/etc`, sistema de
   archivos de solo lectura y un cgroup propio (systemd-run --user --scope) con tope de memoria, de procesos y de tiempo.
   **Si falta cualquiera de las piezas, la función se apaga: nunca ejecuta código sin aislar.**

Honestidad: el arnés y los casos viven dentro del mismo entorno que tu código, así que alguien decidido podría leerlos o
falsear el resultado. Sirve para practicar y para medir, no es una prueba de examen vigilada.
Se activa con `practica_codigo: true` en la configuración (apagada por defecto, también en lo que se publica).
"""
import json
import os
import re
import select
import shutil
import signal
import subprocess
import tempfile
import threading
import time

import config
from base import ejecutar, fila, filas

ejecutar("""CREATE TABLE IF NOT EXISTS codigo_ejercicio (
  id INTEGER PRIMARY KEY AUTOINCREMENT, usuario TEXT, tema TEXT, datos TEXT,   -- JSON: enunciado, función, plantilla, solución, casos
  creado REAL, vio_solucion INTEGER DEFAULT 0)""")
ejecutar("""CREATE TABLE IF NOT EXISTS codigo_intento (
  id INTEGER PRIMARY KEY AUTOINCREMENT, usuario TEXT, ejercicio INTEGER, codigo TEXT, aprobados INTEGER, total INTEGER,
  aprobado INTEGER, vio_solucion INTEGER DEFAULT 0, fecha REAL)""")
ejecutar("CREATE INDEX IF NOT EXISTS codigo_ejercicio_u ON codigo_ejercicio(usuario, tema)")
ejecutar("CREATE INDEX IF NOT EXISTS codigo_intento_u ON codigo_intento(usuario, ejercicio)")

TIEMPO_TOTAL = 8          # s: tope de toda una corrida (todos los casos)
MEMORIA = "192M"          # tope del cgroup (incluye lo que el código escriba en su /tmp)
TAREAS = 24               # procesos e hilos máximos
SALIDA_MAX = 24000        # bytes que se leen de la salida del proceso; lo demás lo mata
CODIGO_MAX = 20000        # caracteres de código
CASOS_VISIBLES = 3
NOMBRE_FUNCION = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,40}$")
FD_RESULTADO = 3
_AUTOPRUEBA = {"hasta": 0.0, "ok": False, "motivo": ""}
_global = threading.BoundedSemaphore(2)
_usuarios = {}
_candado = threading.Lock()

# ---------------------------------------------------------------------------- arnés (corre DENTRO del entorno aislado)
ARNES = r'''
import copy, importlib.util, io, json, math, os, signal, sys, traceback

MAX = 6000


class Tope(io.TextIOBase):
    def __init__(self):
        self.partes, self.n = [], 0

    def write(self, s):
        if self.n < MAX:
            self.partes.append(s[:MAX - self.n])
        self.n += len(s)
        return len(s)

    def texto(self):
        return "".join(self.partes) + ("\n… (salida recortada)" if self.n > MAX else "")


class Tiempo(Exception):
    pass


def alarma(*_):
    raise Tiempo()


def plano(x):
    # a tipos JSON puros: un __eq__ propio del objeto devuelto no puede hacer pasar un caso
    return json.loads(json.dumps(x, default=lambda o: "<%s>" % type(o).__name__))


def igual(a, b):
    if isinstance(a, bool) or isinstance(b, bool):
        return type(a) is type(b) and a == b
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return math.isclose(a, b, rel_tol=1e-6, abs_tol=1e-9)
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(igual(x, y) for x, y in zip(a, b))
    if isinstance(a, dict) and isinstance(b, dict):
        return a.keys() == b.keys() and all(igual(a[k], b[k]) for k in a)
    return type(a) is type(b) and a == b


def corto(x):
    s = json.dumps(x, ensure_ascii=False)
    return x if len(s) <= 300 else s[:300] + "…"


def error_de(e):
    marcos = [f for f in traceback.extract_tb(e.__traceback__) if f.filename.endswith("solucion.py")]
    donde = f" (línea {marcos[-1].lineno})" if marcos else ""
    return f"{type(e).__name__}: {str(e)[:200]}{donde}"


def main():
    datos = json.load(open("/work/casos.json"))
    salida = Tope()
    sys.stdout = sys.stderr = salida
    signal.signal(signal.SIGALRM, alarma)
    res = {"casos": [], "error_carga": None}
    try:
        signal.setitimer(signal.ITIMER_REAL, 2)
        spec = importlib.util.spec_from_file_location("solucion", "/work/solucion.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        fn = getattr(mod, datos["funcion"])
        signal.setitimer(signal.ITIMER_REAL, 0)
    except BaseException as e:
        signal.setitimer(signal.ITIMER_REAL, 0)
        res["error_carga"] = ("No se encontró la función «%s»." % datos["funcion"]) if isinstance(e, AttributeError) else error_de(e)
        fn = None
    if fn:
        for c in datos["casos"]:
            try:
                signal.setitimer(signal.ITIMER_REAL, 2)
                r = fn(*copy.deepcopy(c["args"]))
                signal.setitimer(signal.ITIMER_REAL, 0)
                obtenido, esperado = plano(r), c["esperado"]
                if c.get("ordenar") and isinstance(obtenido, list) and isinstance(esperado, list):
                    try:
                        obtenido, esperado = sorted(obtenido), sorted(esperado)
                    except TypeError:
                        pass
                res["casos"].append({"ok": bool(igual(obtenido, esperado)), "obtenido": corto(obtenido)})
            except Tiempo:
                res["casos"].append({"ok": False, "error": "Tardó más de 2 segundos (¿bucle infinito?)"})
            except BaseException as e:
                signal.setitimer(signal.ITIMER_REAL, 0)
                res["casos"].append({"ok": False, "error": error_de(e)})
    res["salida"] = salida.texto()
    os.write(__FD__, json.dumps(res).encode())


main()
'''.replace('__FD__', str(FD_RESULTADO))


# ---------------------------------------------------------------------------- disponibilidad
def _herramientas():
    return shutil.which("bwrap"), shutil.which("systemd-run"), shutil.which("python3")


def _orden(carpeta, memoria=MEMORIA):
    """La orden completa: cgroup (memoria, procesos, tiempo) → bubblewrap (sin red, sin disco del usuario) → arnés."""
    bwrap, scope, _py = _herramientas()
    return [scope, "--user", "--scope", "--quiet", "-p", f"MemoryMax={memoria}", "-p", "MemorySwapMax=0", "-p", f"TasksMax={TAREAS}",
            "-p", "CPUQuota=100%", "-p", f"RuntimeMaxSec={TIEMPO_TOTAL + 4}", "--",
            bwrap, "--unshare-all", "--die-with-parent", "--new-session", "--clearenv", "--setenv", "PATH", "/usr/bin",
            "--setenv", "LANG", "C.UTF-8", "--setenv", "PYTHONDONTWRITEBYTECODE", "1", "--cap-drop", "ALL",
            "--ro-bind", "/usr", "/usr", "--symlink", "usr/bin", "/bin", "--symlink", "usr/lib", "/lib",
            "--symlink", "usr/lib", "/lib64", "--proc", "/proc", "--dev", "/dev", "--size", "33554432", "--tmpfs", "/tmp",
            "--ro-bind", carpeta, "/work", "--chdir", "/work", "/usr/bin/python3", "-I", "-B", "/work/arnes.py"]


def disponible():
    """(bool, motivo). Apagada por defecto; activa solo si están todas las piezas del aislamiento y una corrida de prueba
    sale bien (se repite cada 10 minutos). Nunca cae a ejecutar sin aislar."""
    if not config.C.get("practica_codigo"):
        return False, "La práctica con código está apagada en esta instalación (configuración «practica_codigo»)."
    if time.time() < _AUTOPRUEBA["hasta"]:
        return _AUTOPRUEBA["ok"], _AUTOPRUEBA["motivo"]
    faltan = [n for n, p in zip(("bubblewrap (bwrap)", "systemd-run", "python3"), _herramientas()) if not p]
    if faltan:
        ok, motivo = False, "Falta " + " y ".join(faltan) + ": sin aislamiento no se ejecuta código."
    else:
        try:
            r = _correr("def f(x):\n    return x + 1\n", "f", [{"args": [1], "esperado": 2}])
            ok = bool(r.get("casos")) and r["casos"][0]["ok"] and not r.get("error_carga")
            motivo = "" if ok else "La prueba del entorno aislado falló: " + str(r.get("error") or r)[:160]
        except Exception as e:  # noqa: BLE001
            ok, motivo = False, f"El entorno aislado no arranca ({type(e).__name__}: {str(e)[:120]})."
    _AUTOPRUEBA.update(hasta=time.time() + 600, ok=ok, motivo=motivo)
    return ok, motivo


# ---------------------------------------------------------------------------- ejecución aislada
def _correr(codigo, funcion, casos):
    """Ejecuta `codigo` contra `casos` [{args, esperado, ordenar?}]. Devuelve {casos, salida, error_carga} o {error}."""
    if len(codigo) > CODIGO_MAX:
        return {"error": f"El código es demasiado largo (máximo {CODIGO_MAX} caracteres)."}
    if not NOMBRE_FUNCION.match(funcion or ""):
        return {"error": "Nombre de función no válido."}
    carpeta = tempfile.mkdtemp(prefix="academia-codigo-")        # 0700: solo este usuario
    os.chmod(carpeta, 0o755)                                      # el entorno aislado entra con otro «usuario» (userns)
    try:
        with open(os.path.join(carpeta, "solucion.py"), "w", encoding="utf-8") as f:
            f.write(codigo)
        with open(os.path.join(carpeta, "casos.json"), "w", encoding="utf-8") as f:
            json.dump({"funcion": funcion, "casos": casos}, f)
        with open(os.path.join(carpeta, "arnes.py"), "w", encoding="utf-8") as f:
            f.write(ARNES)
        for n in ("solucion.py", "casos.json", "arnes.py"):
            os.chmod(os.path.join(carpeta, n), 0o644)
        leer, escribir = os.pipe()

        def preparar():
            os.dup2(escribir, FD_RESULTADO)
            os.set_inheritable(FD_RESULTADO, True)
        p = subprocess.Popen(_orden(carpeta), stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                             preexec_fn=preparar, pass_fds=(FD_RESULTADO,), start_new_session=True, close_fds=True)
        os.close(escribir)
        inicio, salida, resultado, cortado = time.time(), 0, b"", None
        fds = {p.stdout.fileno(): "s", leer: "r"}
        try:
            while fds:
                restante = TIEMPO_TOTAL - (time.time() - inicio)
                if restante <= 0:
                    cortado = "Se agotó el tiempo (%d s)." % TIEMPO_TOTAL
                    break
                listos, _, _ = select.select(list(fds), [], [], min(restante, 0.5))
                for fd in listos:
                    dato = os.read(fd, 65536)
                    if not dato:
                        fds.pop(fd)
                    elif fds[fd] == "s":
                        salida += len(dato)
                        if salida > SALIDA_MAX:
                            cortado = "El programa escribió demasiado en la salida y se detuvo."
                            fds.clear()
                            break
                    else:
                        resultado += dato
                        if len(resultado) > 200000:
                            cortado = "Resultado demasiado grande."
                            fds.clear()
                            break
        finally:
            try:
                os.killpg(p.pid, signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                pass
            try:
                p.wait(timeout=3)
            except subprocess.TimeoutExpired:
                pass
            os.close(leer)
            p.stdout.close()
        if cortado:
            return {"error": cortado}
        try:
            r = json.loads(resultado.decode("utf-8", "replace"))
            if not isinstance(r, dict) or not isinstance(r.get("casos"), list):
                raise ValueError
        except ValueError:
            codigo_salida = p.returncode
            return {"error": "El programa terminó sin entregar resultado" + (
                " (se quedó sin memoria o lo detuvo el sistema)." if codigo_salida in (-9, 137) else ".")}
        return r
    finally:
        shutil.rmtree(carpeta, ignore_errors=True)


def correr(usuario, codigo, funcion, casos):
    """Entrada pública: una corrida por persona a la vez y como mucho dos en total en el servidor."""
    ok, motivo = disponible()
    if not ok:
        return {"error": motivo, "apagada": True}
    with _candado:
        lock = _usuarios.setdefault(usuario, threading.Lock())
    if not lock.acquire(blocking=False):
        return {"error": "Ya hay una ejecución tuya en curso: espera a que termine."}
    try:
        if not _global.acquire(timeout=5):
            return {"error": "El servidor está ocupado ejecutando código de otras personas: inténtalo en un momento."}
        try:
            return _correr(codigo, funcion, casos)
        finally:
            _global.release()
    finally:
        lock.release()


# ---------------------------------------------------------------------------- ejercicios (los escribe la IA, se validan antes)
AREAS_CODIGO = {"sistemas", "ciberseguridad", "tecnologia", "mecatronica", "matematicas"}   # donde la práctica con código tiene sentido

ESQUEMA_EJERCICIO = {"type": "object", "properties": {
    "titulo": {"type": "string"}, "enunciado": {"type": "string"},
    "funcion": {"type": "string"}, "plantilla": {"type": "string"}, "solucion": {"type": "string"},
    "pista": {"type": "string"},
    "casos": {"type": "array", "minItems": 8, "maxItems": 10, "items": {"type": "object", "properties": {
        "args": {"type": "array"}, "esperado": {}, "ordenar": {"type": "boolean"}}, "required": ["args", "esperado"]}}},
    "required": ["titulo", "enunciado", "funcion", "plantilla", "solucion", "pista", "casos"]}


MIN_CASOS = 6


def validar(ej):
    """Un ejercicio solo se muestra con casos que DOS derivaciones independientes confirman: el resultado que la IA escribió
    como «esperado» y lo que devuelve su solución de referencia al ejecutarla. Los casos donde no coinciden se descartan (no se
    sabe cuál de los dos erró); si quedan menos de 6, o la solución no corre, o la plantilla sin tocar ya los pasa todos, el
    ejercicio se descarta. Si es válido, deja en `ej["casos"]` solo los confirmados. Todo corre en el entorno aislado.
    Devuelve (ok, motivo)."""
    if not NOMBRE_FUNCION.match(str(ej.get("funcion") or "")):
        return False, "nombre de función no válido"
    casos = [c for c in (ej.get("casos") or []) if isinstance(c, dict) and isinstance(c.get("args"), list) and "esperado" in c]
    if len(casos) < MIN_CASOS:
        return False, f"menos de {MIN_CASOS} casos bien formados"
    r = _correr(ej["solucion"], ej["funcion"], casos)
    if r.get("error") or r.get("error_carga"):
        return False, "la solución de referencia no corre: " + str(r.get("error") or r.get("error_carga"))
    confirmados = [c for c, x in zip(casos, r["casos"]) if x["ok"]]
    if len(confirmados) < MIN_CASOS:
        return False, f"la solución de referencia solo coincide con {len(confirmados)} de {len(casos)} casos"
    v = _correr(ej["plantilla"], ej["funcion"], confirmados)
    if not v.get("error") and not v.get("error_carga") and all(x["ok"] for x in v["casos"]):
        return False, "la plantilla ya pasa todos los casos (el ejercicio no pide nada)"
    ej["casos"] = confirmados[:10]
    return True, ""


def generar(ctx, usuario, tid, perfil, lecciones):
    """Trabajo de la cola: pide un ejercicio a la IA sobre el tema, lo valida y lo guarda. Reintenta una vez."""
    import curriculo as cur
    t = cur.tema(tid, usuario)
    if not t:
        raise ValueError("tema desconocido")
    ok, motivo = disponible()
    if not ok:
        raise ValueError(motivo)
    previos = [json.loads(r["datos"]).get("titulo") for r in filas(
        "SELECT datos FROM codigo_ejercicio WHERE usuario=? AND tema=? ORDER BY id DESC LIMIT 5", (usuario, tid))]
    leccion = fila("SELECT contenido FROM leccion WHERE usuario=? AND tema=?", (usuario, tid)) or {}
    base = (f"Tema: «{t['t']}» (nivel {t.get('nivel', '?')}).\n"
            + (f"Extracto de la lección:\n{(leccion.get('contenido') or '')[:2500]}\n\n" if leccion.get("contenido") else "")
            + (f"Ya hiciste estos ejercicios (NO repitas): {'; '.join(x for x in previos if x)}.\n" if previos else "")
            + "Escribe UN ejercicio de programación en Python 3 (solo biblioteca estándar) que practique este tema, "
              "resoluble escribiendo UNA función pura (sin leer archivos ni la red, sin entrada del teclado).\n"
              "- enunciado: claro, con un ejemplo, en español; di exactamente qué recibe y qué devuelve la función.\n"
              "- funcion: el nombre de la función (letras, números y guion bajo).\n"
              "- plantilla: el `def` con su docstring y `pass` en el cuerpo (nada resuelto).\n"
              "- solucion: una solución de referencia correcta y completa de esa misma función.\n"
              "- pista: una pista que oriente sin dar la solución.\n"
              "- casos: de 8 a 10, con «args» (lista de los argumentos posicionales, en JSON) y «esperado» (el resultado en JSON: "
              "números, textos, booleanos, listas o diccionarios con claves de texto; NADA que JSON no pueda representar). "
              "Incluye casos límite (vacío, uno solo, negativos, repetidos). «ordenar»: true solo si el orden del resultado no importa.\n"
              "Debe ser difícil de adivinar pero de dificultad adecuada al nivel del tema; la solución debe tardar menos de 1 segundo.")
    ultimo = ""
    for intento in range(2):
        ctx.fase("Escribiendo el ejercicio" if not intento else "Corrigiendo el ejercicio (reintento)")
        extra = f"\n\nTu intento anterior se descartó porque: {ultimo}. Corrígelo." if ultimo else ""
        ej = ctx.chat([{"role": "system", "content": "Eres un profesor de programación riguroso. Respondes en español."},
                       {"role": "user", "content": base + extra}], max_tokens=3000, temperatura=0.5, esquema=ESQUEMA_EJERCICIO)
        ctx.fase("Comprobando el ejercicio en el entorno aislado")
        ok, ultimo = validar(ej)
        if ok:
            break
    else:
        raise ValueError("La IA no logró un ejercicio válido (" + ultimo + "). Inténtalo de nuevo.")
    eid = ejecutar("INSERT INTO codigo_ejercicio(usuario,tema,datos,creado) VALUES(?,?,?,?)",
                   (usuario, tid, json.dumps(ej, ensure_ascii=False), time.time())).lastrowid
    return {"id": eid, "tema": tid}


# ---------------------------------------------------------------------------- lo que ve la persona
def publico(fila_ej, vio_solucion=False):
    """El ejercicio SIN la solución (salvo que ya la haya pedido) y con solo los primeros casos a la vista."""
    ej = json.loads(fila_ej["datos"])
    vis = ej["casos"][:CASOS_VISIBLES]
    out = {"id": fila_ej["id"], "tema": fila_ej["tema"], "titulo": ej["titulo"], "enunciado": ej["enunciado"],
           "funcion": ej["funcion"], "plantilla": ej["plantilla"], "visibles": vis, "ocultos": max(0, len(ej["casos"]) - len(vis)),
           "vio_solucion": bool(fila_ej.get("vio_solucion"))}
    if vio_solucion or fila_ej.get("vio_solucion"):
        out["solucion"] = ej["solucion"]
    return out


def evaluar(usuario, fila_ej, codigo):
    """Corre el código de la persona contra todos los casos y arma la respuesta para la pantalla: los casos visibles con su
    entrada, lo esperado y lo obtenido; los ocultos, solo si pasaron."""
    ej = json.loads(fila_ej["datos"])
    r = correr(usuario, codigo, ej["funcion"], ej["casos"])
    if r.get("error"):
        return {"error": r["error"], "apagada": r.get("apagada", False)}
    casos = []
    for k, (c, x) in enumerate(zip(ej["casos"], r["casos"])):
        item = {"ok": x["ok"], "oculto": k >= CASOS_VISIBLES}
        if k < CASOS_VISIBLES:
            item.update(args=c["args"], esperado=c["esperado"], obtenido=x.get("obtenido"), error=x.get("error"))
        elif x.get("error"):
            item["error"] = x["error"]
        casos.append(item)
    return {"casos": casos, "aprobados": sum(1 for x in r["casos"] if x["ok"]), "total": len(ej["casos"]),
            "error_carga": r.get("error_carga"), "salida": r.get("salida", "")}
