"""Salud de la Academia: qué está pasando por dentro, qué falla y de dónde partimos (fase F0 del plan de mejoras).

Cuatro piezas, todas sin dependencias y casi todas funciones puras para poder probarlas:

* `evaluar(foto)`: convierte una foto del estado en una lista de problemas con gravedad (el tablero y el vigía
  externo `vigia.py` usan la misma lista, así que la pantalla y la alarma nunca se contradicen).
* `correr_diaria(fn)`: envuelve la rutina diaria y deja anotado cuándo empezó, cuándo terminó y si falló.
* Diario de la cola de IA (`anotar`, `cerrar`, `al_arrancar`, `conciliar`): lo pendiente se anota en la base al
  encolarse y se borra al terminar; al reiniciar se compara lo que había con lo que `reanudar()` logró volver a
  encolar, y lo que no se pudo reconstruir (p. ej. una pregunta al tutor que alguien estaba esperando) queda a la
  vista en vez de desaparecer en silencio.
* Línea base (`foto_uso`, `linea_base`): cómo se usa la Academia hoy, guardada una vez por persona para poder
  decir después, con números, si algo mejoró.

Privacidad: la foto del sistema es del equipo (solo el administrador la ve); la línea base es por persona y cada
perfil ve solo la suya.
"""
import json
import shutil
import statistics
import threading
import time
import traceback
from datetime import datetime

import base
from base import ejecutar, fila, filas, kv_get, kv_set

HORA = 3600
GRACIA_DIARIA_H = 3          # la rutina diaria puede tardar en arrancar (PC apagado, GPU ocupada) antes de dar alarma
TOPE_CORRIENDO_H = 3         # una tarea de IA corriendo más tiempo que esto está colgada (una lección a fondo tarda ~30 min)
TEMP_ALTA, TEMP_CRITICA = 80, 85
DISCO_MIN_GB = 5

# Tareas que alguien está esperando en pantalla: si el servicio se reinicia, `reanudar()` no puede reconstruirlas
# (no hay de dónde) y la persona debe pedirlas otra vez. Todas las demás sí se reconstruyen desde la base.
INTERACTIVAS = {"tutor", "corregir", "prueba", "reexplicar", "entrega", "apunte", "tarea", "aporte", "paper",
                "area", "objetivo", "externo", "lectura", "reporte", "relaciones", "verificar"}


# ------------------------------------------------------------------ problemas
def problema(id_, gravedad, texto):
    return {"id": id_, "gravedad": gravedad, "texto": texto}


def evaluar(f):
    """`f`: foto del estado (ver `servidor.foto_salud`). Devuelve [{id, gravedad: alta|media|baja, texto}], las más
    graves primero. Una foto vacía no produce problemas: lo que no se puede medir no se inventa."""
    p = []
    ahora = f.get("ahora") or time.time()
    d = f.get("diaria") or {}
    prog, ult = d.get("programada"), d.get("ultima")
    if d.get("error"):
        p.append(problema("diaria_fallo", "alta", f"La rutina diaria falló: {str(d['error'])[:160]}"))
    recien = ahora - (f.get("inicio_servicio") or 0) < 180   # al arrancar, la rutina atrasada empieza a los ~20 s
    if prog and ahora - prog > GRACIA_DIARIA_H * HORA and (ult or 0) < prog and not recien:
        p.append(problema("diaria_atrasada", "alta",
                          f"La rutina diaria de las {datetime.fromtimestamp(prog):%H:%M} no se ejecutó "
                          f"(hace {round((ahora - prog) / HORA, 1)} h)."))
    elif d.get("inicio") and not d.get("fin") and ahora - d["inicio"] > 30 * 60:
        p.append(problema("diaria_larga", "media",
                          f"La rutina diaria lleva {round((ahora - d['inicio']) / 60)} min armando la cola."))
    c = f.get("cola") or {}
    if c.get("corriendo_max_s", 0) > TOPE_CORRIENDO_H * HORA:
        p.append(problema("cola_colgada", "alta",
                          f"Una tarea de IA lleva {round(c['corriendo_max_s'] / HORA, 1)} h corriendo (probable bloqueo)."))
    if c.get("fallidos_24h", 0) >= 5:
        p.append(problema("cola_fallos", "media", f"{c['fallidos_24h']} tareas de IA fallaron en las últimas 24 h."))
    if c.get("perdidos"):
        p.append(problema("cola_perdidos", "media",
                          f"{c['perdidos']} tarea(s) que alguien esperaba se perdieron en el último reinicio: "
                          "hay que pedirlas de nuevo."))
    g = (f.get("sistema") or {}).get("gpu") or {}
    if g.get("temp") is not None:
        if g["temp"] >= TEMP_CRITICA:
            p.append(problema("gpu_temp", "alta", f"La GPU está a {g['temp']} °C."))
        elif g["temp"] >= TEMP_ALTA:
            p.append(problema("gpu_temp", "media", f"La GPU está a {g['temp']} °C."))
    ia_ = f.get("ia") or {}
    if ia_.get("alcanzable") is False and (c.get("en_cola", 0) or c.get("corriendo", 0)):
        p.append(problema("ia_caida", "alta", "Hay tareas esperando pero el servidor de IA no responde."))
    disco = f.get("disco_libre_gb")
    if disco is not None and disco < DISCO_MIN_GB:
        p.append(problema("disco", "alta", f"Quedan solo {disco} GB libres en el disco."))
    orden = {"alta": 0, "media": 1, "baja": 2}
    return sorted(p, key=lambda x: orden[x["gravedad"]])


# ------------------------------------------------------------------ cola: resumen
def resumen_cola(trabajos, ahora=None, perdidos=0):
    """`trabajos`: [{tipo, estado, creado, terminado, inicio?}] de `ia.cola.trabajos`. Solo cuenta; no lee contenido."""
    ahora = ahora or time.time()
    por_estado, por_tipo = {}, {}
    mas_viejo = corriendo_max = 0
    fallidos = 0
    for t in trabajos:
        por_estado[t["estado"]] = por_estado.get(t["estado"], 0) + 1
        if t["estado"] in ("cola", "corriendo", "conflicto"):
            por_tipo[t["tipo"]] = por_tipo.get(t["tipo"], 0) + 1
            mas_viejo = max(mas_viejo, ahora - (t.get("creado") or ahora))
        if t["estado"] == "corriendo":
            corriendo_max = max(corriendo_max, ahora - (t.get("inicio") or t.get("creado") or ahora))
        if t["estado"] == "error" and (t.get("terminado") or 0) > ahora - 86400:
            fallidos += 1
    return {"por_estado": por_estado, "pendientes_por_tipo": dict(sorted(por_tipo.items(), key=lambda x: -x[1])),
            "en_cola": por_estado.get("cola", 0), "corriendo": por_estado.get("corriendo", 0),
            "conflicto": por_estado.get("conflicto", 0), "mas_viejo_s": round(mas_viejo),
            "corriendo_max_s": round(corriendo_max), "fallidos_24h": fallidos, "perdidos": perdidos}


def disco_libre_gb(ruta):
    try:
        return round(shutil.disk_usage(ruta).free / 1e9, 1)
    except OSError:
        return None


# ------------------------------------------------------------------ rutina diaria
def correr_diaria(fn, ahora=time.time):
    """Ejecuta la rutina diaria y la deja anotada en `kv:salud_diaria`: inicio, fin y error (si lo hubo). Un fallo
    se anota y se relanza para que el llamador lo siga registrando como hasta ahora."""
    kv_set("salud_diaria", {"inicio": ahora(), "fin": None, "error": None})
    try:
        r = fn()
    except Exception as e:  # noqa: BLE001
        d = kv_get("salud_diaria", {})
        kv_set("salud_diaria", d | {"fin": ahora(), "error": f"{type(e).__name__}: {e}"[:300]})
        raise
    d = kv_get("salud_diaria", {})
    kv_set("salud_diaria", d | {"fin": ahora(), "error": None})
    return r


# ------------------------------------------------------------------ diario de la cola
_candado = threading.Lock()
_antes = []          # lo que estaba pendiente cuando el proceso anterior se detuvo (lo llena `al_arrancar`)


def iniciar_tabla():
    ejecutar("""CREATE TABLE IF NOT EXISTS cola_diario (
        id TEXT PRIMARY KEY, tipo TEXT, usuario TEXT, etiqueta TEXT, prioridad INTEGER, creado REAL)""")


def anotar(t):
    """Gancho de `ia.Cola.poner`: apunta la tarea. Nunca debe impedir que se encole (un fallo aquí solo se imprime)."""
    try:
        ejecutar("INSERT OR REPLACE INTO cola_diario(id,tipo,usuario,etiqueta,prioridad,creado) VALUES(?,?,?,?,?,?)",
                 (t.id, t.tipo, t.usuario, t.etiqueta or "", t.prioridad, t.creado))
    except Exception:
        traceback.print_exc()


def cerrar(t):
    """Gancho al terminar (bien o con error): ya no está pendiente."""
    try:
        ejecutar("DELETE FROM cola_diario WHERE id=?", (t.id,))
    except Exception:
        traceback.print_exc()


def al_arrancar():
    """Antes de aceptar peticiones: guarda en memoria lo que quedó pendiente del proceso anterior y vacía el diario
    (lo que se vuelva a encolar se anotará de nuevo). Devuelve cuántas había."""
    global _antes
    with _candado:
        iniciar_tabla()
        _antes = filas("SELECT tipo, usuario, etiqueta, prioridad, creado FROM cola_diario")
        ejecutar("DELETE FROM cola_diario")
    return len(_antes)


def conciliar(trabajos):
    """Después de `reanudar()`: compara lo que había con lo que ahora está en la cola. `trabajos`: lista de
    {tipo, usuario, etiqueta, estado}. Lo que falta se anota como perdido (con su tipo, para decir si alguien lo
    esperaba) y se guarda en `kv:cola_perdidos`. Devuelve {antes, recuperadas, perdidas:[...]}."""
    global _antes
    with _candado:
        previas, _antes = _antes, []
    vivas = {(t["tipo"], t["usuario"], t["etiqueta"] or "") for t in trabajos
             if t["estado"] in ("cola", "corriendo", "conflicto")}
    perdidas, recuperadas = [], 0
    for x in previas:
        if (x["tipo"], x["usuario"], x["etiqueta"] or "") in vivas:
            recuperadas += 1
        else:
            perdidas.append({"tipo": x["tipo"], "usuario": x["usuario"], "etiqueta": x["etiqueta"],
                             "creado": x["creado"], "esperaba_alguien": x["tipo"] in INTERACTIVAS})
    info = {"cuando": time.time(), "antes": len(previas), "recuperadas": recuperadas, "perdidas": perdidas}
    kv_set("cola_reinicio", info)
    # solo cuentan como problema las que una persona estaba esperando; el fondo que no volvió se rehace en la diaria
    kv_set("cola_perdidos", [x for x in perdidas if x["esperaba_alguien"]])
    return info


def perdidos_visibles(usuario=None):
    """Las tareas perdidas del último reinicio; si se da `usuario`, solo las de esa persona."""
    v = kv_get("cola_perdidos", []) or []
    return [x for x in v if usuario is None or x["usuario"] == usuario]


# ------------------------------------------------------------------ línea base de uso
DIA = 86400


def _dia_local(t):
    return datetime.fromtimestamp(t - 4 * HORA).date()   # como `analitica`: lo de madrugada cuenta para el día anterior


def foto_uso(usuario, ahora=None):
    """Cómo usa la Academia esta persona, medido hoy. Todo sale de tablas que ya existen; cada número dice de dónde."""
    ahora = ahora or time.time()
    d14, d30 = ahora - 14 * DIA, ahora - 30 * DIA
    seg = lambda desde: fila("SELECT IFNULL(SUM(valor),0) s FROM actividad WHERE usuario=? AND tipo='tiempo' "  # noqa: E731
                             "AND fecha>?", (usuario, desde))["s"]
    min14, min30, min_total = round(seg(d14) / 60), round(seg(d30) / 60), round(seg(0) / 60)
    fechas = [r["fecha"] for r in filas("SELECT fecha FROM actividad WHERE usuario=? AND fecha>?", (usuario, d14))]
    dias14 = len({_dia_local(f) for f in fechas})
    estados = {r["estado"]: r["n"] for r in filas(
        "SELECT estado, COUNT(*) n FROM avance WHERE usuario=? GROUP BY estado", (usuario,))}
    dominados = estados.get("dominado", 0) + estados.get("probado", 0)
    tarjetas = fila("SELECT COUNT(*) n, SUM(CASE WHEN vence<=? AND suspendida=0 THEN 1 ELSE 0 END) v "
                    "FROM tarjeta WHERE usuario=?", (ahora, usuario))
    seg_rep = [r["segundos"] for r in filas(
        "SELECT segundos FROM repaso WHERE usuario=? AND fecha>? AND segundos IS NOT NULL AND segundos<300",
        (usuario, d30))]
    lecciones = fila("SELECT COUNT(*) n, SUM(completa!=0) c FROM leccion WHERE usuario=?", (usuario,))
    return {
        "fecha": ahora,
        "minutos_14d": {"valor": min14, "origen": "suma de los latidos de tiempo de estudio (actividad.tipo='tiempo')"},
        "minutos_30d": {"valor": min30, "origen": "igual, ventana de 30 días"},
        "minutos_por_dia_activo_14d": {"valor": round(min14 / dias14, 1) if dias14 else None,
                                       "origen": "minutos_14d / días con actividad"},
        "dias_activos_14d": {"valor": dias14, "origen": "días distintos con cualquier actividad registrada"},
        "temas_por_estado": {"valor": estados, "origen": "tabla avance (nuevo, visto, dominado, probado)"},
        "temas_dominados": {"valor": dominados, "origen": "avance.estado en dominado o probado (hoy sin prueba diferida)"},
        "minutos_por_tema_dominado": {"valor": round(min_total / dominados) if dominados else None,
                                      "origen": "todo el tiempo estudiado / temas dominados (aproximado)"},
        "tarjetas": {"valor": {"total": tarjetas["n"] or 0, "vencidas": tarjetas["v"] or 0},
                     "origen": "tabla tarjeta; vencidas = vence <= ahora y no suspendidas"},
        "segundos_por_tarjeta_30d": {"valor": round(statistics.median(seg_rep), 1) if seg_rep else None,
                                     "origen": "mediana de segundos por repaso (< 5 min) en 30 días"},
        "lecciones": {"valor": {"escritas": lecciones["n"] or 0, "completas": lecciones["c"] or 0},
                      "origen": "tabla leccion"},
    }


def linea_base(usuario, crear=True):
    """La primera foto de uso de la persona queda fija (`kv:linea_base:<usuario>`); las siguientes se comparan con ella.
    Devuelve {base, ahora}. Con `crear=False` no escribe nada."""
    clave = f"linea_base:{usuario}"
    b = kv_get(clave)
    if b is None and crear:
        b = foto_uso(usuario)
        kv_set(clave, b)
    return {"base": b, "ahora": foto_uso(usuario)}


def foto_base_datos(ruta_db):
    """Tamaño de la base y de su registro de escritura (para ver si crece sin control)."""
    out = {}
    for nombre, suf in (("db_mb", ""), ("wal_mb", "-wal")):
        try:
            out[nombre] = round(ruta_db.with_name(ruta_db.name + suf).stat().st_size / 1048576, 1)
        except OSError:
            out[nombre] = None
    return out
