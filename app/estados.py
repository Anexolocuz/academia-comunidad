"""🧬 Dominio medido: estados 0-5 por tema y prueba diferida (fase F3 del plan, en MODO SOMBRA).

Un tema solo cuenta como **dominado de verdad** con evidencia de más de un tipo, no por haberlo leído:

| Estado | Evidencia mínima |
|---|---|
| 0 No visto | — |
| 1 Expuesto | lo abriste o leíste |
| 2 Recuerda | quiz ≥ 60 % o tarjetas del tema repasadas con éxito |
| 3 Comprende | explicación Feynman ≥ 70 % o una pregunta del tutor examinador bien resuelta |
| 4 Aplica | ejercicio de código resuelto sin ver la solución, entrega de práctica ≥ 70 % o práctica ≥ 70 % |
| 5 Domina | 4 + **pruebas diferidas** aprobadas a los 3, 14 y 45 días del primer dominio + memoria estable (FSRS) |

**Modo sombra:** esto SOLO MIDE y se muestra. No cambia `avance.estado`, ni el repaso, ni qué te toca hoy: el plan exige que una
medida nueva compare primero con lo que ya decide el sistema antes de mandar.

**Prueba diferida:** preguntas de aplicación en un caso nuevo, distintas del quiz y de las pruebas diferidas anteriores del
tema. Solo toca cuando pasó el tiempo (esa es la gracia: medir lo que queda, no lo que se acaba de estudiar). El banco lo escribe
la IA y pasa por una **segunda lectura independiente**: otra llamada contesta cada pregunta sin ver la respuesta marcada; si no
coincide, la pregunta se descarta. Se corrige sin IA (opción múltiple) y cada pregunta lleva la confianza declarada, que alimenta
la calibración.
"""
import json
import re
import time
from datetime import datetime, timedelta

import config  # noqa: F401  (fija la carpeta de datos antes de abrir la base)
import curriculo as cur
from base import ejecutar, fila, filas, registrar

ejecutar("""CREATE TABLE IF NOT EXISTS prueba_diferida (
  id INTEGER PRIMARY KEY AUTOINCREMENT, usuario TEXT, tema TEXT, etapa INTEGER,   -- 1, 2, 3 = a los 3, 14 y 45 días
  estado TEXT DEFAULT 'lista',                                                    -- lista | hecha
  preguntas TEXT,                                                                 -- JSON [{pregunta, opciones, correcta, explicacion}]
  resultado TEXT,                                                                 -- JSON {aciertos, total, puntaje, aprobada, respuestas}
  creada REAL, hecha REAL)""")
ejecutar("CREATE INDEX IF NOT EXISTS prueba_diferida_u ON prueba_diferida(usuario, tema)")

DIAS_ETAPA = (3, 14, 45)
APRUEBA = 0.75
ESTADOS = ["No visto", "Expuesto", "Recuerda", "Comprende", "Aplica", "Domina"]
MIN_PREGUNTAS = 4
SIMILITUD_MAX = 0.55


# ---------------------------------------------------------------------------- estados 0-5
def _evidencias(usuario):
    """Lo que hay de cada tema, en una pasada por las tablas (para toda la persona)."""
    ev = {}

    def de(t):
        return ev.setdefault(t, {"vista": False, "quiz": None, "feynman": None, "tarjetas": 0, "estab": [], "examen": [],
                                 "codigo": False, "practica": None, "entrega": None})
    for r in filas("SELECT tema, estado, quiz, feynman FROM avance WHERE usuario=?", (usuario,)):
        e = de(r["tema"])
        e["vista"] = r["estado"] in ("visto", "dominado", "probado") or r["quiz"] is not None
        e["quiz"], e["feynman"] = r["quiz"], r["feynman"]
    for r in filas("SELECT tema, COUNT(*) n, AVG(estabilidad) est FROM tarjeta WHERE usuario=? AND tema IS NOT NULL AND repasos>=2 AND fallos<=repasos/2 "
                   "GROUP BY tema", (usuario,)):
        e = de(r["tema"])
        e["tarjetas"] = r["n"]
        if r["est"]:
            e["estab"].append(r["est"])
    for r in filas("SELECT tema, tipo, valor, detalle FROM actividad WHERE usuario=? AND tema IS NOT NULL AND tipo IN ('examen','codigo','practica','leccion','lectura')",
                   (usuario,)):
        e = de(r["tema"])
        d = json.loads(r["detalle"] or "{}") if r["detalle"] else {}
        if r["tipo"] in ("leccion", "lectura"):
            e["vista"] = True
        elif r["tipo"] == "examen" and r["valor"] is not None:
            e["examen"].append((r["valor"], d.get("ayudas") or 0))
        elif r["tipo"] == "codigo" and (r["valor"] or 0) >= 1 and not d.get("vio_solucion"):
            e["codigo"] = True
        elif r["tipo"] == "practica" and r["valor"] is not None:
            e["practica"] = max(e["practica"] or 0, r["valor"])
    for r in filas("SELECT tema, MAX(puntaje) p FROM entrega WHERE usuario=? AND puntaje IS NOT NULL GROUP BY tema", (usuario,)):
        de(r["tema"])["entrega"] = (r["p"] or 0) / 100
    return ev


def _diferidas(usuario):
    out = {}
    for r in filas("SELECT tema, etapa, resultado FROM prueba_diferida WHERE usuario=? AND estado='hecha' ORDER BY id", (usuario,)):
        res = json.loads(r["resultado"] or "{}")
        out.setdefault(r["tema"], {})[r["etapa"]] = res
    return out


def _fechas_dominio(usuario):
    import adaptacion
    return adaptacion._fechas_dominio(usuario)


def _nivel(e, difs):
    """(nivel, evidencia, falta) de un tema a partir de sus evidencias."""
    ok = []
    exp = e["vista"] or e["quiz"] is not None
    if exp:
        ok.append((1, "lo abriste o leíste"))
    if (e["quiz"] or 0) >= 0.6 or e["tarjetas"]:
        ok.append((2, f"quiz {round((e['quiz'] or 0) * 100)} %" if (e["quiz"] or 0) >= 0.6 else f"{e['tarjetas']} tarjeta(s) repasadas con éxito"))
    if (e["feynman"] or 0) >= 0.7 or any(v >= 0.8 and a <= 1 for v, a in e["examen"]):
        ok.append((3, "explicación Feynman ≥ 70 %" if (e["feynman"] or 0) >= 0.7 else "pregunta del tutor examinador bien resuelta"))
    if e["codigo"] or (e["practica"] or 0) >= 0.7 or (e["entrega"] or 0) >= 0.7:
        ok.append((4, "ejercicio de código resuelto sin ver la solución" if e["codigo"] else "práctica o entrega ≥ 70 %"))
    pasadas = [k for k in (1, 2, 3) if (difs.get(k) or {}).get("aprobada")]
    estable = (sum(e["estab"]) / len(e["estab"]) >= 30) if e["estab"] else True      # sin tarjetas no se exige
    if any(n == 4 for n, _ in ok) and len(pasadas) == 3 and estable:
        ok.append((5, "pruebas diferidas aprobadas a los 3, 14 y 45 días"))
    nivel = max([n for n, _ in ok], default=0)
    falta = []
    if nivel < 2:
        falta.append("haz el quiz de la lección (60 % o más) o repasa sus tarjetas")
    if nivel < 3:
        falta.append("explícalo con tus palabras (Feynman) o que el tutor te examine y lo resuelvas sin pistas")
    if nivel < 4:
        falta.append("resuelve un ejercicio de aplicación sin ver la solución (código o entrega de práctica)")
    if nivel == 4:
        falta.append(f"pruebas diferidas: {len(pasadas)} de 3 aprobadas (a los {', '.join(str(d) for d in DIAS_ETAPA)} días del primer dominio)")
    return nivel, [t for _, t in ok], falta


def estado_tema(usuario, tema, _ev=None, _difs=None):
    ev = (_ev if _ev is not None else _evidencias(usuario)).get(tema) or {"vista": False, "quiz": None, "feynman": None, "tarjetas": 0,
                                                                          "estab": [], "examen": [], "codigo": False, "practica": None, "entrega": None}
    difs = (_difs if _difs is not None else _diferidas(usuario)).get(tema, {})
    n, evidencia, falta = _nivel(ev, difs)
    return {"nivel": n, "etiqueta": ESTADOS[n], "evidencia": evidencia, "falta": falta}


def estados_persona(usuario):
    """Para el tablero: cuántos temas hay en cada estado y qué pruebas diferidas están disponibles ya."""
    ev, difs = _evidencias(usuario), _diferidas(usuario)
    cuenta = [0] * 6
    for t, e in ev.items():
        cuenta[_nivel(e, difs.get(t, {}))[0]] += 1
    return {"por_nivel": [{"nivel": k, "etiqueta": ESTADOS[k], "temas": n} for k, n in enumerate(cuenta)],
            "con_evidencia": sum(cuenta), "pendientes": pendientes(usuario)}


# ---------------------------------------------------------------------------- calendario de pruebas diferidas
def calendario(usuario, tema, ahora=None):
    """Las tres citas de un tema dominado: fecha desde la que toca cada una, si ya se hizo y su puntaje. Vacío si no se ha dominado."""
    ahora = ahora or time.time()
    t0 = _fechas_dominio(usuario).get(tema)
    if not t0:
        return []
    hechas = _diferidas(usuario).get(tema, {})
    out = []
    for k, dias in enumerate(DIAS_ETAPA, 1):
        r = hechas.get(k)
        desde = t0 + dias * 86400
        out.append({"etapa": k, "dias": dias, "desde": desde, "disponible": ahora >= desde, "hecha": r is not None,
                    "aprobada": bool(r and r.get("aprobada")), "puntaje": r.get("puntaje") if r else None})
    return out


def siguiente_cita(usuario, tema, ahora=None):
    """La primera etapa sin hacer (en orden: no se salta la de 3 días para ir a la de 14)."""
    return next((c for c in calendario(usuario, tema, ahora) if not c["hecha"]), None)


def pendientes(usuario, ahora=None):
    """Temas con una prueba diferida que ya toca y aún no se hizo."""
    ahora = ahora or time.time()
    out = []
    for tema in _fechas_dominio(usuario):
        c = siguiente_cita(usuario, tema, ahora)
        if c and c["disponible"]:
            t = cur.tema(tema, usuario)
            if t:
                out.append({"tema": tema, "titulo": t["t"], "etapa": c["etapa"], "dias": c["dias"], "vencida_hace_dias": int((ahora - c["desde"]) // 86400)})
    return sorted(out, key=lambda x: -x["vencida_hace_dias"])


# ---------------------------------------------------------------------------- el banco (lo escribe la IA y se lee dos veces)
ESQUEMA_BANCO = {"type": "object", "properties": {"preguntas": {"type": "array", "minItems": 5, "maxItems": 6, "items": {"type": "object", "properties": {
    "pregunta": {"type": "string"}, "opciones": {"type": "array", "minItems": 4, "maxItems": 4, "items": {"type": "string"}},
    "correcta": {"type": "integer", "minimum": 0, "maximum": 3}, "explicacion": {"type": "string"}},
    "required": ["pregunta", "opciones", "correcta", "explicacion"]}}}, "required": ["preguntas"]}
ESQUEMA_RESPUESTA = {"type": "object", "properties": {"respuesta": {"type": "integer", "minimum": 0, "maximum": 3}}, "required": ["respuesta"]}


def _palabras(texto):
    return {w for w in re.findall(r"[a-záéíóúñü]{4,}", (texto or "").lower())}


def parecida(a, b):
    """Parecido de dos enunciados (Jaccard de palabras de 4+ letras): evita repetir el quiz o una prueba anterior."""
    pa, pb = _palabras(a), _palabras(b)
    return len(pa & pb) / len(pa | pb) if pa and pb else 0.0


def _previas(usuario, tema):
    """Enunciados que ya se preguntaron de este tema: el quiz de la lección y las pruebas diferidas anteriores."""
    out = []
    r = fila("SELECT ejercicios FROM leccion WHERE usuario=? AND tema=?", (usuario, tema))
    if r and r["ejercicios"]:
        out += [q.get("pregunta", "") for q in (json.loads(r["ejercicios"]).get("quiz") or [])]
    for d in filas("SELECT preguntas FROM prueba_diferida WHERE usuario=? AND tema=?", (usuario, tema)):
        out += [q.get("pregunta", "") for q in json.loads(d["preguntas"] or "[]")]
    return out


def depurar(preguntas, previas):
    """Primer filtro (sin IA): formato válido, 4 opciones distintas, índice correcto y nada que se parezca a lo ya preguntado."""
    buenas = []
    for q in preguntas:
        ops = q.get("opciones") or []
        if (len(ops) != 4 or len({o.strip().lower() for o in ops}) != 4 or not isinstance(q.get("correcta"), int)
                or not 0 <= q["correcta"] < 4 or len(q.get("pregunta", "")) < 25):
            continue
        if any(parecida(q["pregunta"], p) > SIMILITUD_MAX for p in previas + [b["pregunta"] for b in buenas]):
            continue
        buenas.append(q)
    return buenas


def generar_banco(ctx, usuario, tema, etapa, perfil):
    """Trabajo de la cola: escribe preguntas de aplicación (caso nuevo), las deduplica contra lo ya preguntado y las hace pasar por
    una segunda lectura independiente (otra llamada contesta sin ver la respuesta marcada). Guarda la prueba lista."""
    t = cur.tema(tema, usuario)
    if not t:
        raise ValueError("tema desconocido")
    previas = _previas(usuario, tema)
    leccion = fila("SELECT contenido FROM leccion WHERE usuario=? AND tema=?", (usuario, tema)) or {}
    ctx.fase("Escribiendo preguntas de aplicación")
    prompt = (f"Tema: «{t['t']}» ({t['d']}).\n"
              + (f"Extracto de la lección que estudió:\n{(leccion.get('contenido') or '')[:2500]}\n\n" if leccion.get("contenido") else "")
              + ("Preguntas que YA se le hicieron (no las repitas ni las parafrasees):\n" + "\n".join(f"- {p[:140]}" for p in previas[:14]) + "\n\n" if previas else "")
              + f"Escribe entre 5 y 6 preguntas de opción múltiple (4 opciones, una sola correcta) para una PRUEBA DIFERIDA (han pasado {DIAS_ETAPA[etapa - 1]} "
                "días desde que dominó el tema). Deben medir comprensión y aplicación, no memoria de frases:\n"
                "- Cada pregunta plantea un CASO NUEVO y concreto (un escenario, un dato, un fragmento) distinto de los ejemplos de la lección.\n"
                "- Los distractores son errores conceptuales plausibles, no absurdos.\n- Una sola respuesta es correcta y defendible sin ambigüedad.\n"
                "- explicacion: por qué la correcta lo es y qué error delata cada distractor, en 2-3 frases.\nTodo en español.")
    r = ctx.chat([{"role": "system", "content": "Eres un examinador riguroso. Respondes en español."}, {"role": "user", "content": prompt}],
                 max_tokens=3000, temperatura=0.5, esquema=ESQUEMA_BANCO)
    candidatas = depurar(r["preguntas"], previas)
    confirmadas = []
    for k, q in enumerate(candidatas, 1):
        ctx.fase(f"Segunda lectura independiente ({k}/{len(candidatas)})")
        ops = "\n".join(f"{i}. {o}" for i, o in enumerate(q["opciones"]))
        a = ctx.chat([{"role": "system", "content": "Respondes preguntas de opción múltiple con rigor. Devuelves solo el índice (0-3) de la ÚNICA opción correcta."},
                      {"role": "user", "content": f"Tema: {t['t']}\n\n{q['pregunta']}\n\n{ops}"}], max_tokens=200, temperatura=0.0, esquema=ESQUEMA_RESPUESTA)
        if a.get("respuesta") == q["correcta"]:
            confirmadas.append(q)
    if len(confirmadas) < MIN_PREGUNTAS:
        raise ValueError(f"Solo {len(confirmadas)} de {len(r['preguntas'])} preguntas pasaron la revisión (se piden {MIN_PREGUNTAS}). Inténtalo de nuevo.")
    pid = ejecutar("INSERT INTO prueba_diferida(usuario,tema,etapa,estado,preguntas,creada) VALUES(?,?,?,?,?,?)",
                   (usuario, tema, etapa, "lista", json.dumps(confirmadas, ensure_ascii=False), time.time())).lastrowid
    return {"id": pid, "tema": tema}


# ---------------------------------------------------------------------------- hacer la prueba
def publica(fila_p):
    """La prueba sin las respuestas."""
    return {"id": fila_p["id"], "tema": fila_p["tema"], "etapa": fila_p["etapa"], "dias": DIAS_ETAPA[fila_p["etapa"] - 1],
            "estado": fila_p["estado"], "preguntas": [{"pregunta": q["pregunta"], "opciones": q["opciones"]} for q in json.loads(fila_p["preguntas"])]}


def responder(usuario, fila_p, respuestas):
    """Corrige sin IA. `respuestas` = [{j: índice elegido, conf: seguro|dudo|adivino|None}] en el orden de las preguntas.
    Una prueba se responde una sola vez: así el resultado es una medida y no un ensayo repetible."""
    if fila_p["estado"] == "hecha":
        return {"error": "esta prueba ya se respondió"}
    qs = json.loads(fila_p["preguntas"])
    if not isinstance(respuestas, list) or len(respuestas) != len(qs):
        return {"error": "faltan respuestas"}
    import adaptacion
    t = cur.tema(fila_p["tema"], usuario)
    detalle, aciertos = [], 0
    for q, r in zip(qs, respuestas):
        j = r.get("j") if isinstance(r, dict) else None
        ok = isinstance(j, int) and j == q["correcta"]
        aciertos += ok
        detalle.append({"j": j, "ok": ok, "correcta": q["correcta"], "explicacion": q["explicacion"], "conf": (r or {}).get("conf")})
        conf = adaptacion.NIVELES_CONFIANZA.get(str((r or {}).get("conf") or ""))
        if conf is not None:
            registrar(usuario, "calibracion", fila_p["tema"], (t or {}).get("area"), 1.0 if ok else 0.0,
                      {"p": conf, "nivel": r["conf"], "origen": "diferida"})
    puntaje = aciertos / len(qs)
    res = {"aciertos": aciertos, "total": len(qs), "puntaje": round(puntaje, 3), "aprobada": puntaje >= APRUEBA, "respuestas": detalle}
    ejecutar("UPDATE prueba_diferida SET estado='hecha', resultado=?, hecha=? WHERE id=?", (json.dumps(res, ensure_ascii=False), time.time(), fila_p["id"]))
    registrar(usuario, "diferida", fila_p["tema"], (t or {}).get("area"), puntaje,
              {"etapa": fila_p["etapa"], "dias": DIAS_ETAPA[fila_p["etapa"] - 1], "aprobada": res["aprobada"]})
    res["preguntas"] = [{"pregunta": q["pregunta"], "opciones": q["opciones"]} for q in qs]
    return res
