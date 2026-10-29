"""Línea de tiempo de eventos (fase F1 del plan de mejoras): una sola tabla donde cae todo lo que la persona hace.

Es una **proyección**: no reemplaza ninguna tabla. Las que ya existen (actividad, repasos, lectura, entregas, reexplicaciones,
partes entendidas, pruebas de nivel, chequeos) siguen siendo la fuente; `sincronizar()` las copia aquí con una marca de agua por fuente,
sin tocar las rutas que las escriben, y es idempotente (correrla dos veces no duplica nada). Además recibe los eventos indirectos que solo
ve la interfaz (cuánto estuvo en una vista, a dónde fue después) y la sugerencia que se le mostró en «Hoy».

Cada evento: `usuario, ts, fuente, tipo, objeto, valor, contexto (JSON), directo`.
* **Directo** (`directo=1`): la persona lo dio de forma explícita (una nota de repaso, un puntaje, una entrega).
* **Indirecto** (`directo=0`): se deduce de cómo se comporta (tiempo, lectura, navegación, lo que ignora).

Privacidad: todo es por persona (columna `usuario`); ninguna función cruza perfiles. El texto de lo que escribe (apuntes, entregas, chat) NO se
copia aquí: solo el hecho, el objeto, el puntaje y el tiempo.
"""
import json
import sqlite3
import threading
import time

from base import ejecutar, fila, filas, db, kv_get, kv_set

HORA = 3600
_candado = threading.Lock()

# Tipos que acepta la interfaz (lista blanca: nada más entra por la API) y cuánto puede pesar su contexto.
TIPOS_CLIENTE = {"vista": "segundos en una vista antes de salir", "navega": "paso de una vista a otra"}
VISTAS_VALIDAS = 60          # largo máximo del nombre de una vista
MAX_POR_LLAMADA = 50


def iniciar_tablas():
    ejecutar("""CREATE TABLE IF NOT EXISTS evento (
        id INTEGER PRIMARY KEY AUTOINCREMENT, usuario TEXT NOT NULL, ts REAL NOT NULL, fuente TEXT NOT NULL,
        tipo TEXT NOT NULL, objeto TEXT, valor REAL, contexto TEXT, directo INTEGER DEFAULT 0, ref TEXT)""")
    ejecutar("CREATE UNIQUE INDEX IF NOT EXISTS evento_ref ON evento(fuente, ref) WHERE ref IS NOT NULL")
    ejecutar("CREATE INDEX IF NOT EXISTS evento_usuario_ts ON evento(usuario, ts)")
    ejecutar("CREATE INDEX IF NOT EXISTS evento_usuario_tipo ON evento(usuario, tipo, ts)")


# ------------------------------------------------------------------ escritura
def _guardar(filas_):
    """filas_: [(usuario, ts, fuente, tipo, objeto, valor, contexto_dict|None, directo, ref)]. Sin `ref` siempre inserta;
    con `ref` actualiza si ya existía (así una sesión de lectura que crece sigue siendo un solo evento)."""
    if not filas_:
        return 0
    c = db()
    for u, ts, fuente, tipo, objeto, valor, ctx, directo, ref in filas_:
        datos = (u, ts, fuente, tipo, objeto, valor, json.dumps(ctx, ensure_ascii=False) if ctx else None, int(directo), ref)
        if ref is None:
            c.execute("INSERT INTO evento(usuario,ts,fuente,tipo,objeto,valor,contexto,directo,ref) VALUES(?,?,?,?,?,?,?,?,?)", datos)
        else:
            c.execute("""INSERT INTO evento(usuario,ts,fuente,tipo,objeto,valor,contexto,directo,ref) VALUES(?,?,?,?,?,?,?,?,?)
                         ON CONFLICT(fuente, ref) WHERE ref IS NOT NULL DO UPDATE SET ts=excluded.ts, tipo=excluded.tipo,
                         objeto=excluded.objeto, valor=excluded.valor, contexto=excluded.contexto, directo=excluded.directo""", datos)
    c.commit()
    return len(filas_)


def _json(texto):
    try:
        v = json.loads(texto) if texto else None
        return v if isinstance(v, dict) else ({"detalle": v} if v is not None else {})
    except (TypeError, ValueError):
        return {}


# Qué tipos de la tabla actividad son explícitos de la persona (el resto son rastros de su comportamiento).
DIRECTAS = {"quiz", "prueba", "practica", "apunte_eval", "chequeo_tema", "pulso", "pulso_sesion", "nivel", "chequeo", "feynman", "calibracion", "codigo", "examen", "diferida"}


# ------------------------------------------------------------------ proyección desde las tablas que ya existen
def _marca(fuente):
    return (kv_get("evento_marca:" + fuente, 0) or 0)


def _fijar(fuente, v):
    kv_set("evento_marca:" + fuente, v)


def _desde_actividad():
    m = _marca("actividad")
    # repaso, parte y entrega ya llegan, con más datos, desde sus propias tablas: aquí se omiten para no contarlos dos veces
    rows = filas("SELECT * FROM actividad WHERE id>? AND tipo NOT IN ('repaso','parte','entrega') ORDER BY id LIMIT 5000", (m,))
    out = []
    for r in rows:
        ctx = _json(r["detalle"])
        if r["area"]:
            ctx["area"] = r["area"]
        out.append((r["usuario"], r["fecha"], "actividad", r["tipo"], r["tema"], r["valor"], ctx or None,
                    r["tipo"] in DIRECTAS, "a%d" % r["id"]))
    if rows:
        _fijar("actividad", rows[-1]["id"])
    return out


def _desde_repaso():
    m = _marca("repaso")
    rows = filas("""SELECT r.*, t.tema, t.area FROM repaso r LEFT JOIN tarjeta t ON t.id=r.tarjeta
                    WHERE r.id>? ORDER BY r.id LIMIT 5000""", (m,))
    out = [(r["usuario"], r["fecha"], "repaso", "repaso", r["tema"], r["nota"],
            {k: r[k] for k in ("segundos", "retenibilidad", "dias", "origen", "area", "tarjeta") if r.get(k) is not None},
            True, "r%d" % r["id"]) for r in rows]
    if rows:
        _fijar("repaso", rows[-1]["id"])
    return out


def _desde_lectura():
    m = _marca("lectura")
    rows = filas("SELECT * FROM lectura WHERE fin>=? ORDER BY fin LIMIT 5000", (m,))
    out = [(r["usuario"], r["fin"], "lectura", "lectura", r["tema"], r["segundos"],
            {k: r[k] for k in ("metodo", "idioma", "avance", "palabras", "formulas", "acciones", "audio", "inicio", "area")
             if r.get(k) is not None}, False, "l" + r["id"]) for r in rows]
    if rows:
        _fijar("lectura", rows[-1]["fin"])
    return out


def _desde_entrega():
    m = _marca("entrega")
    rows = filas("""SELECT *, MAX(creado, IFNULL(corregido, 0)) mov FROM entrega WHERE MAX(creado, IFNULL(corregido, 0))>=?
                    ORDER BY mov LIMIT 5000""", (m,))
    out = [(r["usuario"], r["corregido"] or r["creado"], "entrega", "entrega", r["tema"], r["puntaje"],
            {"ejercicio": r["ejercicio"], "version": r["version"], "tipo": r["tipo"], "corregida": bool(r["corregido"]),
             "area": r["area"]}, True, "e%d" % r["id"]) for r in rows]
    if rows:
        _fijar("entrega", rows[-1]["mov"])
    return out


def _desde_reexplicacion():
    m = _marca("reexplicacion")
    rows = filas("SELECT id, usuario, tema, parte, estilo, fecha FROM reexplicacion WHERE id>? ORDER BY id LIMIT 5000", (m,))
    out = [(r["usuario"], r["fecha"], "reexplicacion", "reexplicacion", r["tema"], r["parte"], {"estilo": r["estilo"]},
            True, "x%d" % r["id"]) for r in rows]
    if rows:
        _fijar("reexplicacion", rows[-1]["id"])
    return out


def _desde_parte():
    m = _marca("parte_estado")
    rows = filas("SELECT * FROM parte_estado WHERE fecha>=? ORDER BY fecha LIMIT 5000", (m,))
    out = [(r["usuario"], r["fecha"], "parte_estado", "parte_" + str(r["estado"]), r["tema"], r["segundos"],
            {"parte": r["parte"]}, True, "p%s|%s" % (r["tema"], r["parte"])) for r in rows]
    if rows:
        _fijar("parte_estado", rows[-1]["fecha"])
    return out


def _desde_prueba():
    m = _marca("prueba_nivel")
    rows = filas("SELECT id, usuario, ref, estado, terminada FROM prueba_nivel WHERE terminada>=? ORDER BY terminada LIMIT 5000", (m,))
    out = [(r["usuario"], r["terminada"], "prueba_nivel", "prueba_nivel", r["ref"], None, {"estado": r["estado"]},
            True, "n%d" % r["id"]) for r in rows]
    if rows:
        _fijar("prueba_nivel", rows[-1]["terminada"])
    return out


def _desde_chequeo():
    m = _marca("chequeo")
    rows = filas("SELECT id, usuario, semana, completado FROM chequeo WHERE completado>=? ORDER BY completado LIMIT 5000", (m,))
    out = [(r["usuario"], r["completado"], "chequeo", "chequeo_completo", r["semana"], None, None, True, "c%d" % r["id"])
           for r in rows]
    if rows:
        _fijar("chequeo", rows[-1]["completado"])
    return out


FUENTES = (_desde_actividad, _desde_repaso, _desde_lectura, _desde_entrega, _desde_reexplicacion, _desde_parte,
           _desde_prueba, _desde_chequeo)


def sincronizar():
    """Copia a `evento` lo nuevo de cada tabla de origen. Idempotente y a prueba de cortes: la marca de agua se mueve
    después de leer y las filas llevan `ref`, así que repetir una pasada solo vuelve a escribir lo mismo. Devuelve cuántos
    eventos procesó."""
    n = 0
    with _candado:
        for f in FUENTES:
            while True:
                try:
                    lote = f()
                except sqlite3.OperationalError:   # esa tabla aún no existe (su módulo no se ha iniciado): se salta
                    break
                if not lote:
                    break
                n += _guardar(lote)
                if len(lote) < 5000:
                    break
    return n


# ------------------------------------------------------------------ eventos que llegan de la interfaz y de «Hoy»
def apagado(usuario):
    """La persona apagó la familia «Decisión y comportamiento» en 🔬: no se guardan sus eventos de navegación ni sugerencias."""
    return "decision" in (kv_get(f"metricas_off:{usuario}", []) or [])


def registrar_cliente(usuario, lista, ahora=None):
    """Eventos indirectos que solo ve la interfaz. `lista`: [{tipo, objeto, valor, contexto}]. Solo tipos de la lista
    blanca; nombres cortos; valores acotados. Devuelve cuántos se guardaron."""
    ahora = ahora or time.time()
    if apagado(usuario):
        return 0
    out = []
    for e in (lista or [])[:MAX_POR_LLAMADA]:
        if not isinstance(e, dict) or e.get("tipo") not in TIPOS_CLIENTE:
            continue
        objeto = str(e.get("objeto") or "")[:VISTAS_VALIDAS]
        try:
            valor = max(0.0, min(float(e.get("valor") or 0), 3600.0))
        except (TypeError, ValueError):
            continue
        ctx = e.get("contexto") if isinstance(e.get("contexto"), dict) else {}
        ctx = {str(k)[:20]: (str(v)[:VISTAS_VALIDAS] if isinstance(v, str) else v) for k, v in list(ctx.items())[:5]
               if isinstance(v, (str, int, float, bool))}
        out.append((usuario, ahora, "cliente", e["tipo"], objeto, valor, ctx or None, False, None))
    return _guardar(out)


def sugerencia(usuario, destino, titulo="", ahora=None):
    """Lo que «Hoy» le propuso como siguiente paso. Para saber después si lo siguió o lo ignoró. Se anota una vez por
    hora y destino (recargar la pantalla no infla el conteo)."""
    ahora = ahora or time.time()
    if apagado(usuario):
        return 0
    ref = "%s|%s|%d" % (usuario, destino, int(ahora // HORA))
    return _guardar([(usuario, ahora, "hoy", "sugerencia", str(destino or "")[:VISTAS_VALIDAS], None,
                      {"titulo": str(titulo)[:80]}, False, ref)])


# ------------------------------------------------------------------ lectura
def de_persona(usuario, tipo=None, desde=0, hasta=None, limite=100000):
    """Eventos de UNA persona (nunca de otra), del más viejo al más nuevo."""
    sql, args = "SELECT * FROM evento WHERE usuario=? AND ts>=?", [usuario, desde]
    if hasta:
        sql += " AND ts<?"; args.append(hasta)
    if tipo:
        sql += " AND tipo=?"; args.append(tipo)
    rows = filas(sql + " ORDER BY ts LIMIT ?", tuple(args) + (limite,))
    for r in rows:
        r["contexto"] = _json(r["contexto"])
    return rows


def resumen(usuario):
    """Cuántos eventos tiene la persona, por tipo y por origen (directo/indirecto): lo que muestra la vista de transparencia."""
    por_tipo = filas("""SELECT tipo, directo, COUNT(*) n, MIN(ts) desde, MAX(ts) hasta FROM evento WHERE usuario=?
                        GROUP BY tipo, directo ORDER BY n DESC""", (usuario,))
    return {"total": sum(x["n"] for x in por_tipo), "por_tipo": por_tipo}
