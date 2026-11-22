"""Auditoría de las claves de las preguntas y erratas de las lecciones.

Por qué existe (2026-11-18): una revisión a mano de las 130 preguntas respondidas en pruebas iniciales encontró 15 claves
falsas escritas por la IA (en la prueba de nivel de Bases de datos la clave estaba corrida una posición en 12 de 14
preguntas), 2 preguntas sin ninguna opción correcta y varias ambiguas. La lógica de calificación estaba bien: el
problema eran las claves. Este módulo guarda el veredicto de cada pregunta (lo da Claude, Hermes o una persona) y lo
aplican quienes evalúan: el Reto, el examen por chat de Hermes y su material.

Una pregunta se identifica por la huella de su texto, así que el mismo veredicto sirve aunque la pregunta aparezca en
el quiz de la lección, en el Reto o en una prueba. Nada aquí recalifica resultados ya guardados: eso lo decide la
persona.
"""
import hashlib
import json
import re
import time

from base import ejecutar, fila, filas

# ok = clave correcta · matiz = correcta pero simplificada · ambigua = dos opciones defendibles · clave_mal = la clave
# apunta a una opción falsa (`real` = índice de la correcta) · sin_correcta / mal_planteada = ninguna opción sirve ·
# errata = error en el texto de una lección (no es una pregunta)
VEREDICTOS = ("ok", "matiz", "ambigua", "clave_mal", "sin_correcta", "mal_planteada", "errata")
NO_EVALUAR = ("ambigua", "sin_correcta", "mal_planteada")


def iniciar():
    ejecutar("""CREATE TABLE IF NOT EXISTS auditoria_pregunta (
        usuario TEXT NOT NULL, huella TEXT NOT NULL, tema TEXT, fuente TEXT, pregunta TEXT,
        veredicto TEXT NOT NULL, real INTEGER, nota TEXT, autor TEXT, fecha REAL,
        PRIMARY KEY (usuario, huella))""")
    ejecutar("CREATE INDEX IF NOT EXISTS auditoria_pregunta_tema ON auditoria_pregunta(usuario, tema)")
    try:   # texto de la opción correcta: el Reto baraja las opciones, así que el índice solo no basta
        ejecutar("ALTER TABLE auditoria_pregunta ADD COLUMN real_texto TEXT")
    except Exception:
        pass


def huella(texto):
    return hashlib.sha1(re.sub(r"\s+", " ", (texto or "").strip()).encode()).hexdigest()[:16]


def guardar(usuario, v, autor="hermes"):
    """Guarda un veredicto. `v`: {pregunta, veredicto, tema?, fuente?, real?, nota?, opciones?}. Devuelve un error
    legible o None."""
    pregunta = str(v.get("pregunta") or "").strip()
    ver = str(v.get("veredicto") or "").strip()
    if not pregunta or ver not in VEREDICTOS:
        return f"hace falta «pregunta» y un «veredicto» de {', '.join(VEREDICTOS)}"
    real, opciones, real_texto = v.get("real"), v.get("opciones") or [], None
    if ver == "clave_mal":
        n = len(opciones) or 4
        if not isinstance(real, int) or isinstance(real, bool) or not 0 <= real < n:
            return "con «clave_mal» hace falta «real»: el índice (desde 0) de la opción correcta"
        real_texto = str(opciones[real]) if opciones else None
    else:
        real = None
    ejecutar("""INSERT OR REPLACE INTO auditoria_pregunta(usuario,huella,tema,fuente,pregunta,veredicto,real,nota,autor,fecha,real_texto)
                VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
             (usuario, huella(pregunta), v.get("tema"), str(v.get("fuente") or "")[:40], pregunta[:600], ver, real,
              str(v.get("nota") or "")[:800], str(autor)[:40], time.time(), real_texto))
    return None


def de_tema(usuario, tema):
    return [dict(r) for r in filas("SELECT * FROM auditoria_pregunta WHERE usuario=? AND tema=? ORDER BY fecha",
                                   (usuario, tema))]


def mapa(usuario, tema=None):
    sql, args = "SELECT * FROM auditoria_pregunta WHERE usuario=?", [usuario]
    if tema:
        sql, args = sql + " AND tema=?", args + [tema]
    return {r["huella"]: dict(r) for r in filas(sql, tuple(args))}


def aplicar(p, auditados):
    """Para una pregunta de opción {pregunta, opciones, correcta}: (usable, correcta, veredicto, nota).
    Con «clave_mal» devuelve la clave corregida; con NO_EVALUAR, usable = False."""
    a = auditados.get(huella(p.get("pregunta")))
    if not a:
        return True, p.get("correcta"), None, None
    if a["veredicto"] in NO_EVALUAR:
        return False, p.get("correcta"), a["veredicto"], a["nota"]
    if a["veredicto"] == "clave_mal":
        ops = [str(o) for o in p.get("opciones") or []]
        if a.get("real_texto") in ops:                       # por texto: vale aunque las opciones estén barajadas
            return True, ops.index(a["real_texto"]), a["veredicto"], a["nota"]
        if a["real"] is not None and a["real"] < len(ops) and not a.get("real_texto"):
            return True, a["real"], a["veredicto"], a["nota"]
        return False, p.get("correcta"), a["veredicto"], a["nota"]   # no se sabe cuál es: mejor no usarla
    return True, p.get("correcta"), a["veredicto"], a["nota"]


def preguntas_de_tema(usuario, tema):
    """Todas las preguntas de opción que existen para un tema (quiz de su lección y pruebas de nivel), sin repetir."""
    vistas, out = set(), []

    def poner(p, fuente):
        h = huella(p.get("pregunta"))
        if h not in vistas and p.get("opciones"):
            vistas.add(h)
            out.append({"pregunta": p["pregunta"], "opciones": p["opciones"], "correcta": p.get("correcta"),
                        "explicacion": p.get("explicacion") or "", "tipo": p.get("tipo") or "opcion", "fuente": fuente})
    r = fila("SELECT ejercicios FROM leccion WHERE usuario=? AND tema=? AND ejercicios IS NOT NULL", (usuario, tema))
    if r:
        try:
            for p in (json.loads(r["ejercicios"]) or {}).get("quiz") or []:
                if isinstance(p, dict) and p.get("tipo", "opcion") == "opcion":
                    poner(p, "quiz")
        except ValueError:
            pass
    ref, _, i = tema.rpartition(".")
    for r in filas("SELECT id, datos FROM prueba_nivel WHERE usuario=? AND ref=?", (usuario, ref)):
        try:
            d = json.loads(r["datos"])
        except ValueError:
            continue
        for p in d.get("preguntas") or []:
            if str(p.get("tema")) == i:
                poner(p, f"prueba {r['id']}")
    return out


def pendientes(usuario, tema):
    hechos = mapa(usuario, None)
    return [p for p in preguntas_de_tema(usuario, tema) if huella(p["pregunta"]) not in hechos]
