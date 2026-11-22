"""Índice y Reto: un puntaje que sube o baja según lo que de verdad sabes responder, sin IA en el camino.

Qué es
------
El **Índice** es una medida en una escala tipo CI (media 100, pasos de 15), pero **no es un CI** ni se compara con
otras personas: se compara con los **niveles del currículo**. Cada nivel de módulo tiene una dificultad fija:

    Fundamentos 85 · Intermedio 100 · Avanzado 115 · Experto 130 · Horizonte 145

Un Índice de 115 quiere decir: «respondes las preguntas de nivel Avanzado a mitad de camino entre adivinar y
acertar siempre». Con cada respuesta el Índice se mueve como en el ajedrez (Elo) sobre un modelo de respuesta al
ítem con adivinación (3PL): acertar una difícil sube mucho, fallar una fácil baja mucho.

Por qué así
-----------
- Practicar la **recuperación** (acordarse sin mirar) es de lo que más fija la memoria; el Reto es eso, con un
  número que motiva a repetirlo. Lo fallado vuelve como tarjeta FSRS y enlaza su lección.
- Una **racha** premia abrir la app; el Índice premia saber. No baja por no entrar: lo que crece con el tiempo sin
  practicar es la **incertidumbre** (±), como en Glicko.
- Solo se guardan las respuestas crudas (`reto_respuesta`). El Índice se **recalcula** reproduciendo ese registro:
  si mañana se ajusta la fórmula, se recalcula todo sin migrar nada.

Sin suerte
----------
- **Pista de longitud**: en las preguntas escritas por IA la correcta suele ser la opción más larga (en un banco real,
  el 71 %; «elegir la más larga» acertaba el 66 % sin saber nada). Cada pregunta guarda su `pista` (largo de la correcta
  ÷ largo de la opción más larga de las otras). El Reto arma cada ronda **neutral**: la correcta es la más larga en
  ~1/4 de las preguntas y la más corta en ~1/4, como si fuera al azar, y deja fuera las de pista fuerte (> 1,1). Si
  alguna se cuela (banco agotado), acertarla vale como acertar entre 2 opciones.
- **Antes de ver las opciones**: la pregunta aparece sola y se dice «la sé», «creo» o «no sé». La respuesta se forma
  antes de ver los largos. «No sé» no deja adivinar: muestra la respuesta y cuenta lo mismo que, en promedio, daría
  adivinar (ni premia ni castiga decir la verdad). «La sé» y fallar = falsa seguridad, que se muestra aparte.

Aislamiento: cada perfil solo ve su Índice, sus retos y las preguntas de **sus** lecciones.
"""
import hashlib
import json
import math
import random
import time

from base import ejecutar, fila, filas
import auditoria as aud
import curriculo as cur

# ------------------------------------------------------------------ escala y modelo
BASE = 100.0                    # Índice inicial (sin datos)
DIF_NIVEL = {1: 85.0, 2: 100.0, 3: 115.0, 4: 130.0, 5: 145.0}
NOMBRES = [(92.5, "Fundamentos"), (107.5, "Intermedio"), (122.5, "Avanzado"), (137.5, "Experto"),
           (float("inf"), "Horizonte")]
ESCALA = 40.0                   # 40 puntos de diferencia = probabilidad de acertar (sin adivinar) 10 a 1
DERIVA_DIA = 100.0 / 60.0       # varianza que se suma por día sin practicar: +10 de ± a los 60 días desde 0
PISO, TECHO = 55.0, 175.0      # dos escalones bajo Fundamentos y dos sobre Horizonte: más allá la escala no mide nada
PROVISIONAL = 20                # respuestas antes de que el Índice deje de ser provisional
PREGUNTAS_RETO = 10
SEGUNDOS = 60                   # por pregunta, a la vista
GRACIA = 15                     # el servidor tolera la latencia de la red; más allá cuenta como sin responder
SIN_REPETIR_DIAS = 30
MIN_BANCO = 10                  # menos preguntas que esto en tus lecciones: aún no hay reto
PISTA_MAX = 1.1                 # la correcta más de un 10 % más larga que cualquier otra: pista fuerte, fuera del reto
AZAR_PISTA = 0.5                # si una de pista fuerte llega a usarse, acertarla vale como acertar entre 2
SEGURIDADES = ("se", "creo", "nose")
# Regla para todo prompt que escriba opción múltiple: sin ella, la IA alarga y matiza la correcta y se acierta sin saber.
REGLA_OPCIONES = ("Las 4 opciones deben tener LARGO y NIVEL DE DETALLE PARECIDOS (máximo ±15 % de caracteres entre ellas): "
                  "la correcta NO puede ser la más larga, la más completa ni la única con matices o salvedades; los "
                  "distractores son errores conceptuales plausibles escritos con el mismo cuidado; nada de «todas/ninguna "
                  "de las anteriores» ni de palabras que la delaten.")

ESQUEMA = """
CREATE TABLE IF NOT EXISTS reto (
  id INTEGER PRIMARY KEY AUTOINCREMENT, usuario TEXT NOT NULL,
  items TEXT NOT NULL,           -- JSON: preguntas ya barajadas (con la correcta: nunca sale al navegador antes de responder)
  i INTEGER DEFAULT 0,           -- pregunta actual
  servida REAL,                  -- cuándo se mostró la pregunta actual (para el tiempo)
  indice_antes REAL, indice_despues REAL, aciertos INTEGER DEFAULT 0,
  creado REAL, terminado REAL);
CREATE INDEX IF NOT EXISTS reto_usuario ON reto(usuario, terminado);
CREATE TABLE IF NOT EXISTS reto_respuesta (
  id INTEGER PRIMARY KEY AUTOINCREMENT, usuario TEXT NOT NULL, reto INTEGER, item TEXT, tema TEXT, area TEXT,
  nivel INTEGER, dificultad REAL, opciones INTEGER, acierto INTEGER, elegida INTEGER, ms INTEGER, ts REAL,
  pista REAL,                    -- largo de la correcta / largo de la opción más larga de las otras (> 1 = la correcta es la más larga)
  seguridad TEXT);               -- se | creo | nose (dicho ANTES de ver las opciones); NULL en respuestas viejas
CREATE INDEX IF NOT EXISTS reto_respuesta_usuario ON reto_respuesta(usuario, ts);
"""


def iniciar():
    from base import db
    db().executescript(ESQUEMA)
    cols = {r[1] for r in db().execute("PRAGMA table_info(reto_respuesta)")}
    for col, tipo in (("pista", "REAL"), ("seguridad", "TEXT")):
        if col not in cols:
            db().execute(f"ALTER TABLE reto_respuesta ADD COLUMN {col} {tipo}")
    # respuestas de antes de guardar la pista: se calcula desde las preguntas guardadas en su reto
    for r in db().execute("SELECT id, reto, item FROM reto_respuesta WHERE pista IS NULL").fetchall():
        x = db().execute("SELECT items FROM reto WHERE id=?", (r[1],)).fetchone()
        c = next((c for c in json.loads(x[0]) if c["item"] == r[2]), None) if x else None
        if c:
            db().execute("UPDATE reto_respuesta SET pista=? WHERE id=?", (pista(c["opciones"], c["correcta"]), r[0]))
    db().commit()


def pista(opciones, correcta):
    """Largo de la correcta ÷ largo de la opción más larga entre las demás: > 1 = la correcta es la más larga."""
    otras = [len(str(o).strip()) for k, o in enumerate(opciones) if k != correcta]
    return round(len(str(opciones[correcta]).strip()) / max(1, max(otras) if otras else 1), 3)


def corta(opciones, correcta):
    """True si la correcta es estrictamente la opción más corta."""
    L = [len(str(o).strip()) for o in opciones]
    return all(L[correcta] < x for k, x in enumerate(L) if k != correcta)


def azar(r):
    """Probabilidad de acertar sin saber: 1/opciones, o más si la correcta se delata por su largo."""
    g = 1.0 / max(2, r["opciones"])
    return max(g, AZAR_PISTA) if (r.get("pista") or 0) > PISTA_MAX else g


def resultado(r):
    """Lo que vale la respuesta para el Índice: 1 o 0; «no sé» vale lo que daría adivinar en promedio."""
    return azar(r) if r.get("seguridad") == "nose" else (1.0 if r["acierto"] else 0.0)


def nombre_nivel(x):
    return next(n for tope, n in NOMBRES if x < tope)


def siguiente_nivel(x):
    """(nombre, puntos que faltan) del siguiente escalón, o None en el último."""
    for tope, n in NOMBRES[:-1]:
        if x < tope:
            sig = NOMBRES[[t for t, _ in NOMBRES].index(tope) + 1][1]
            return {"nombre": sig, "faltan": max(1, math.ceil(tope - x))}
    return None


def p_acierto(theta, dif, opciones, g=None):
    """Probabilidad de acertar (3PL con a fija): adivinar da g (por omisión 1/opciones)."""
    g = 1.0 / max(2, opciones) if g is None else g
    return g + (1 - g) / (1 + 10 ** ((dif - theta) / ESCALA))


def k_factor(n):
    """Paso del Elo: grande al principio (encontrar tu nivel rápido), pequeño después (estable)."""
    return 24.0 if n < PROVISIONAL else 12.0 if n < 60 else 8.0


def _info(theta, dif, opciones, g=None):
    """Información de Fisher del ítem (3PL) en theta: cuánto precisa esta respuesta el Índice."""
    g = 1.0 / max(2, opciones) if g is None else g
    a = math.log(10) / ESCALA
    p = p_acierto(theta, dif, opciones, g)
    return a * a * ((p - g) ** 2 / (1 - g) ** 2) * ((1 - p) / p)


def calcular(respuestas, ahora=None):
    """Reproduce las respuestas en orden y devuelve el Índice, su ± y la serie.

    respuestas: [{dificultad, opciones, acierto, ts, reto, pista?, seguridad?}] ordenadas por ts."""
    ahora = ahora or time.time()
    theta, info, serie, n = BASE, 0.0, [], 0
    for r in respuestas:
        g = azar(r)
        p = p_acierto(theta, r["dificultad"], r["opciones"], g)
        theta = min(TECHO, max(PISO, theta + k_factor(n) * (resultado(r) - p)))
        n += 1
        serie.append((r["ts"], theta, r.get("reto")))
    for r in respuestas:
        info += _info(theta, r["dificultad"], r["opciones"], azar(r))
    var = (1 / info) if info > 0 else 30.0 ** 2
    if respuestas:
        var += DERIVA_DIA * max(0.0, (ahora - respuestas[-1]["ts"]) / 86400)
    se = min(30.0, math.sqrt(var))
    return {"indice": round(theta, 1), "mas_menos": round(se, 1), "n": n, "provisional": n < PROVISIONAL,
            "nivel": nombre_nivel(theta), "siguiente": siguiente_nivel(theta), "serie": serie}


# ------------------------------------------------------------------ banco de preguntas
def _clave(tema, pregunta):
    return tema + "#" + hashlib.sha1(pregunta.strip().encode()).hexdigest()[:10]


def banco(usuario):
    """Preguntas de opción múltiple válidas de las lecciones de esta persona, con la dificultad de su nivel."""
    out, auditados = [], aud.mapa(usuario)
    nombres = {a: x.get("nombre", a) for a, x in cur.areas(usuario).items()}
    for r in filas("SELECT tema, ejercicios FROM leccion WHERE usuario=? AND ejercicios IS NOT NULL", (usuario,)):
        t = cur.tema(r["tema"], usuario)
        m = cur.modulo(r["tema"].rpartition(".")[0], usuario)
        if not t or not m or m.get("nivel") not in DIF_NIVEL:
            continue
        try:
            quiz = (json.loads(r["ejercicios"] or "{}") or {}).get("quiz") or []
        except (ValueError, AttributeError):
            continue
        for p in quiz:
            if not isinstance(p, dict):
                continue
            ops = p.get("opciones") or []
            c = p.get("correcta")
            if p.get("tipo") != "opcion" or len(ops) < 2 or not isinstance(c, int) or not 0 <= c < len(ops) \
                    or not (p.get("pregunta") or "").strip():
                continue
            usable, c, _, _ = aud.aplicar(p, auditados)   # clave corregida o pregunta descartada por la auditoría
            if not usable:
                continue
            out.append({"item": _clave(r["tema"], p["pregunta"]), "tema": r["tema"], "area": t["area"],
                        "area_n": nombres.get(t["area"], t["area"]), "tema_t": t["t"], "nivel": m["nivel"], "dificultad": DIF_NIVEL[m["nivel"]],
                        "pregunta": p["pregunta"], "opciones": ops, "correcta": c,
                        "explicacion": p.get("explicacion") or "", "pista": pista(ops, c), "corta": corta(ops, c)})
    return out


def respuestas(usuario, area=None):
    """Respuestas del Reto que cuentan para el Índice: fuera las preguntas que la auditoría marcó sin opción correcta,
    ambiguas o mal planteadas (no medían nada)."""
    sql = "SELECT * FROM reto_respuesta WHERE usuario=?" + (" AND area=?" if area else "") + " ORDER BY ts, id"
    rs = filas(sql, (usuario, area) if area else (usuario,))
    malas = {h for h, a in aud.mapa(usuario).items() if a["veredicto"] in aud.NO_EVALUAR}
    if not malas:
        return rs
    fuera = set()
    for r in filas("SELECT items FROM reto WHERE usuario=?", (usuario,)):
        for it in json.loads(r["items"] or "[]"):
            if aud.huella(it.get("pregunta")) in malas:
                fuera.add(it.get("item"))
    return [r for r in rs if r["item"] not in fuera]


def tipo_largo(c):
    """larga = la correcta es la opción más larga (o empata con la más larga) · corta = la más corta · media = el resto."""
    return "larga" if c["pista"] >= 1.0 else "corta" if c.get("corta") else "media"


def elegir(cands, theta_global, theta_area, recientes, n=PREGUNTAS_RETO, rng=random):
    """Elige n preguntas cerca de tu nivel (aprender rinde más donde aciertas ~60-70 %), variando áreas y temas.

    Neutral al largo: la correcta es la opción más larga en ~1/4 de las preguntas y la más corta en ~1/4 (lo que
    pasaría al azar con 4 opciones), así que ni «elige la más larga» ni «nunca la más larga» sirven. Las de pista
    fuerte (la correcta mucho más larga) solo entran si no queda otra cosa.
    No repite preguntas respondidas en los últimos SIN_REPETIR_DIAS (si el banco no alcanza, usa las más viejas)."""
    for c in cands:
        c.setdefault("pista", pista(c["opciones"], c["correcta"]))
        c.setdefault("corta", corta(c["opciones"], c["correcta"]))
    frescas = [c for c in cands if c["item"] not in recientes]
    if len(frescas) < n:
        frescas += sorted([c for c in cands if c["item"] in recientes], key=lambda c: recientes[c["item"]])[:n - len(frescas)]
    puntuadas = []
    for c in frescas:
        objetivo = theta_area.get(c["area"], theta_global) + 5 + rng.gauss(0, 10)
        puntuadas.append((abs(c["dificultad"] - objetivo) + rng.random(), c))
    puntuadas.sort(key=lambda x: x[0])
    limpias = [c for _, c in puntuadas if c["pista"] <= PISTA_MAX]
    con_pista = [c for _, c in puntuadas if c["pista"] > PISTA_MAX]
    cuarto = n / 4
    cuota = {t: int(cuarto) + (1 if rng.random() < cuarto - int(cuarto) else 0) for t in ("larga", "corta")}
    cuota["media"] = n - cuota["larga"] - cuota["corta"]
    tope_area = max(3, math.ceil(n * 0.4))
    elegidas, por_area, temas, por_tipo = [], {}, set(), {"larga": 0, "corta": 0, "media": 0}
    # pasadas cada vez más flexibles: 1) todo; 2) cuotas de largo sin variar temas; 3) variar temas sin cuotas
    # (el banco no tiene de ese tipo); 4) sin restricciones; 5) con pista fuerte
    for pasada, lista in ((1, limpias), (2, limpias), (3, limpias), (4, limpias), (5, con_pista)):
        for c in lista:
            if len(elegidas) >= n:
                break
            if any(c is e for e in elegidas):
                continue
            t = tipo_largo(c)
            if pasada <= 2 and por_tipo[t] >= cuota[t]:
                continue
            if pasada in (1, 3) and (c["tema"] in temas or por_area.get(c["area"], 0) >= tope_area):
                continue
            elegidas.append(c)
            temas.add(c["tema"])
            por_area[c["area"]] = por_area.get(c["area"], 0) + 1
            por_tipo[t] += 1
    rng.shuffle(elegidas)
    return elegidas


def barajar(c, rng=random):
    """Baraja las opciones: las IA suelen dejar la correcta en las primeras posiciones (casi nunca la última)."""
    orden = list(range(len(c["opciones"])))
    rng.shuffle(orden)
    return dict(c, opciones=[c["opciones"][k] for k in orden], correcta=orden.index(c["correcta"]))


# ------------------------------------------------------------------ resumen
def calibracion(rs):
    """Cuánto aciertas según lo que dijiste antes de ver las opciones. «La sé» debería acertar casi siempre;
    cada fallo con «la sé» es falsa seguridad: lo que crees saber y no sabes (lo más peligroso de un examen)."""
    out = {}
    for s_ in SEGURIDADES:
        sub = [r for r in rs if r.get("seguridad") == s_]
        out[s_] = {"n": len(sub), "aciertos": sum(r["acierto"] for r in sub),
                   "pct": round(sum(r["acierto"] for r in sub) / len(sub), 2) if sub else None}
    out["falsa_seguridad"] = sum(1 for r in rs if r.get("seguridad") == "se" and not r["acierto"])
    return out


def resumen(usuario, ahora=None):
    ahora = ahora or time.time()
    rs = respuestas(usuario)
    g = calcular(rs, ahora)
    nombres = {a: x["nombre"] for a, x in cur.areas(usuario).items()}
    areas = []
    for a in sorted({r["area"] for r in rs}):
        sub = [r for r in rs if r["area"] == a]
        x = calcular(sub, ahora)
        areas.append({"area": a, "nombre": nombres.get(a, a), "indice": x["indice"], "mas_menos": x["mas_menos"],
                      "n": x["n"], "provisional": x["n"] < 10, "nivel": x["nivel"],
                      "aciertos": sum(r["acierto"] for r in sub)})
    areas.sort(key=lambda x: -x["n"])
    # al final de cada reto: la serie que se dibuja y el récord (solo cuando ya no es provisional)
    fin_reto, vistos = [], 0
    for ts, th, reto in g["serie"]:
        vistos += 1
        if fin_reto and fin_reto[-1]["reto"] == reto:
            fin_reto[-1] = {"ts": ts, "indice": round(th, 1), "reto": reto, "n": vistos}
        else:
            fin_reto.append({"ts": ts, "indice": round(th, 1), "reto": reto, "n": vistos})
    firmes = [p["indice"] for p in fin_reto if p["n"] >= PROVISIONAL]
    hace30 = [p for p in fin_reto if p["ts"] <= ahora - 30 * 86400]
    b = banco(usuario)
    recientes = {r["item"] for r in rs if r["ts"] > ahora - SIN_REPETIR_DIAS * 86400}
    abierto = fila("SELECT id, i, items FROM reto WHERE usuario=? AND terminado IS NULL ORDER BY id DESC LIMIT 1", (usuario,))
    hoy0 = time.mktime(time.localtime(ahora)[:3] + (0, 0, 0, 0, 0, -1))
    return {"global": {k: v for k, v in g.items() if k != "serie"},
            "areas": areas, "historial": [{"ts": p["ts"], "indice": p["indice"]} for p in fin_reto][-60:],
            "record": max(firmes) if firmes else None,
            "hace30": hace30[-1]["indice"] if hace30 else None,
            "retos_hoy": fila("SELECT COUNT(*) n FROM reto WHERE usuario=? AND terminado>=?", (usuario, hoy0))["n"],
            "retos": fila("SELECT COUNT(*) n FROM reto WHERE usuario=? AND terminado IS NOT NULL", (usuario,))["n"],
            "calibracion": calibracion(rs),
            "banco": {"total": len(b), "frescas": sum(1 for c in b if c["item"] not in recientes),
                      "con_pista": sum(1 for c in b if c["pista"] > PISTA_MAX),
                      "minimo": MIN_BANCO, "por_nivel": {n: sum(1 for c in b if c["nivel"] == n) for n in DIF_NIVEL}},
            "abierto": {"id": abierto["id"], "i": abierto["i"], "total": len(json.loads(abierto["items"]))} if abierto else None,
            "escala": {"niveles": {cur.NIVELES[n]: d for n, d in DIF_NIVEL.items()}, "segundos": SEGUNDOS,
                       "preguntas": PREGUNTAS_RETO}}


# ------------------------------------------------------------------ reto
def _publica(r, items):
    """La pregunta actual sin la respuesta correcta ni la explicación."""
    c = items[r["i"]]
    return {"id": r["id"], "i": r["i"], "total": len(items), "segundos": SEGUNDOS,
            "pregunta": {"texto": c["pregunta"], "opciones": c["opciones"], "area": c.get("area_n", c["area"]), "tema_t": c["tema_t"],
                         "nivel": cur.NIVELES[c["nivel"]]}}


def _reloj(r):
    """Al retomar: si la pregunta se mostró hace poco, el reloj sigue corriendo (recargar no regala tiempo);
    si quedó abandonada, empieza de nuevo."""
    if not r["servida"] or time.time() - r["servida"] > SEGUNDOS + GRACIA:
        r["servida"] = time.time()
        ejecutar("UPDATE reto SET servida=? WHERE id=?", (r["servida"], r["id"]))


def nuevo(usuario, rng=random):
    """Abre un reto (o retoma el que quedó abierto). Devuelve la primera pregunta pendiente."""
    r = fila("SELECT * FROM reto WHERE usuario=? AND terminado IS NULL ORDER BY id DESC LIMIT 1", (usuario,))
    if r:
        _reloj(r)
        return _publica(r, json.loads(r["items"]))
    b = banco(usuario)
    if len(b) < MIN_BANCO:
        return {"error": "banco_corto", "banco": len(b), "minimo": MIN_BANCO}
    rs = respuestas(usuario)
    g = calcular(rs)["indice"]
    th_area = {a: calcular([x for x in rs if x["area"] == a])["indice"] for a in {x["area"] for x in rs}}
    recientes = {}
    for x in rs:
        if x["ts"] > time.time() - SIN_REPETIR_DIAS * 86400:
            recientes[x["item"]] = x["ts"]
    items = [barajar(c, rng) for c in elegir(b, g, th_area, recientes, rng=rng)]
    ahora = time.time()
    cur_ = ejecutar("INSERT INTO reto(usuario, items, i, servida, indice_antes, creado) VALUES(?,?,0,?,?,?)",
                    (usuario, json.dumps(items, ensure_ascii=False), ahora, g, ahora))
    return _publica({"id": cur_.lastrowid, "i": 0}, items)


def actual(usuario, rid):
    r = fila("SELECT * FROM reto WHERE id=? AND usuario=?", (rid, usuario))
    if not r:
        return {"error": "reto desconocido"}
    if r["terminado"]:
        return {"terminado": True, "id": rid}
    _reloj(r)
    return _publica(r, json.loads(r["items"]))


def responder(usuario, rid, i, elegida, ahora=None, seguridad=None):
    """Registra una respuesta. elegida=None = se acabó el tiempo. seguridad (dicha antes de ver las opciones):
    se | creo | nose; con «nose» no se elige opción: se muestra la respuesta y vale lo que daría adivinar.
    Devuelve la corrección y, si hay, la siguiente."""
    ahora = ahora or time.time()
    r = fila("SELECT * FROM reto WHERE id=? AND usuario=?", (rid, usuario))
    if not r:
        return {"error": "reto desconocido"}
    if r["terminado"]:
        return {"error": "el reto ya terminó"}
    items = json.loads(r["items"])
    if i != r["i"]:                       # doble clic o pestaña vieja: no se responde dos veces la misma
        return {"error": "esa pregunta ya se respondió", "actual": _publica(r, items)}
    c = items[i]
    seguridad = seguridad if seguridad in SEGURIDADES else None
    if seguridad == "nose":
        elegida = None
    ms = int((ahora - (r["servida"] or ahora)) * 1000)
    a_tiempo = ms <= (SEGUNDOS + GRACIA) * 1000
    valida = isinstance(elegida, int) and 0 <= elegida < len(c["opciones"])
    acierto = 1 if (valida and a_tiempo and elegida == c["correcta"]) else 0
    pi = c.get("pista") or pista(c["opciones"], c["correcta"])
    antes = calcular(respuestas(usuario), ahora)
    ejecutar("INSERT INTO reto_respuesta(usuario, reto, item, tema, area, nivel, dificultad, opciones, acierto, "
             "elegida, ms, ts, pista, seguridad) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
             (usuario, rid, c["item"], c["tema"], c["area"], c["nivel"], c["dificultad"], len(c["opciones"]),
              acierto, elegida if valida else None, ms, ahora, pi, seguridad))
    despues = calcular(respuestas(usuario), ahora)
    sig = i + 1
    fin = sig >= len(items)
    ejecutar("UPDATE reto SET i=?, servida=?, aciertos=aciertos+?, terminado=?, indice_despues=? WHERE id=?",
             (sig, ahora, acierto, ahora if fin else None, despues["indice"] if fin else None, rid))
    out = {"acierto": bool(acierto), "correcta": c["correcta"], "elegida": elegida if valida else None,
           "a_tiempo": a_tiempo, "explicacion": c["explicacion"], "tema": c["tema"], "tema_t": c["tema_t"],
           "seguridad": seguridad, "falsa_seguridad": seguridad == "se" and not acierto,
           "con_pista": pi > PISTA_MAX,
           "prob": round(p_acierto(antes["indice"], c["dificultad"], len(c["opciones"]),
                                   azar({"opciones": len(c["opciones"]), "pista": pi})), 2),
           "delta": round(despues["indice"] - antes["indice"], 1), "indice": despues["indice"]}
    if fin:
        out["fin"] = cierre(usuario, rid)
    else:
        r2 = dict(r, i=sig)
        out["siguiente"] = _publica(r2, items)
    return out


def cierre(usuario, rid):
    """Resumen al terminar: cuánto cambió el Índice, récord, y qué estudiar (los fallos, con su lección)."""
    r = fila("SELECT * FROM reto WHERE id=? AND usuario=?", (rid, usuario))
    items = {c["item"]: c for c in json.loads(r["items"])}
    rs = filas("SELECT * FROM reto_respuesta WHERE usuario=? AND reto=? ORDER BY id", (usuario, rid))
    fallos = [items[x["item"]] for x in rs if not x["acierto"] and x["item"] in items]
    debiles = []
    for c in fallos:
        if c["tema"] not in {d["tema"] for d in debiles}:
            debiles.append({"tema": c["tema"], "t": c["tema_t"], "area": c.get("area_n", c["area"])})
    res = resumen(usuario)
    anteriores = [p["indice"] for p in res["historial"][:-1]]
    return {"aciertos": sum(x["acierto"] for x in rs), "total": len(rs), "calibracion": calibracion(rs),
            "antes": r["indice_antes"], "despues": res["global"]["indice"],
            "delta": round(res["global"]["indice"] - (r["indice_antes"] or BASE), 1),
            "record_nuevo": (not res["global"]["provisional"] and res["record"] is not None
                             and res["record"] == res["global"]["indice"]
                             and all(res["global"]["indice"] > x for x in anteriores)),
            "global": res["global"], "debiles": debiles[:3],
            "fallos": [{"tema": c["tema"], "area": c["area"], "pregunta": c["pregunta"],
                        "correcta": c["opciones"][c["correcta"]], "explicacion": c["explicacion"]} for c in fallos]}
