"""Cómo aprende el usuario (panel) y chequeo semanal de lo aprendido/olvidado.

Todo sale de lo que ya se registra: minutos por método y hora (latidos de 30 s
de la interfaz), repasos FSRS (nota, días desde el anterior, probabilidad
predicha de recordar), quizzes, Feynman, apuntes evaluados y chequeos.
"""
import json
import random
import statistics
import time
from datetime import datetime, timedelta

import curriculo as cur
import fsrs
import lectura
from base import ejecutar, fila, filas, kv_get

DIA = 86400
METODOS = {
    "leccion": "📖 Leer lecciones", "repaso": "🔁 Repasar tarjetas", "cuaderno": "✍️ Escribir a mano",
    "tutor": "💬 Tutor", "noticias": "🌍 Noticias y lectura", "practica": "🏋️ Tareas de práctica", "chequeo": "🧪 Chequeo semanal", "otro": "Otro"}
FRANJAS = [("madrugada", 0, 6), ("mañana", 6, 12), ("tarde", 12, 18), ("noche", 18, 24)]
DIAS_SEMANA = ["lun", "mar", "mié", "jue", "vie", "sáb", "dom"]


# ------------------------------------------------------------------ repaso
def aplicar_repaso(usuario, t, nota, segundos=None, origen="repaso"):
    """Programa la tarjeta con FSRS y registra el repaso (también lo usa el chequeo)."""
    ahora = time.time()
    p = fsrs.programar(t, nota, ahora)
    dias = (ahora - t["ultimo"]) / DIA if t.get("ultimo") else None
    ejecutar("""UPDATE tarjeta SET estabilidad=?, dificultad=?, vence=?, ultimo=?, repasos=repasos+1,
                fallos=fallos+? WHERE id=?""",
             (p["estabilidad"], p["dificultad"], p["vence"], p["ultimo"], 1 if nota == 1 else 0, t["id"]))
    ejecutar("""INSERT INTO repaso(usuario,tarjeta,nota,fecha,segundos,retenibilidad,dias,origen)
                VALUES(?,?,?,?,?,?,?,?)""",
             (usuario, t["id"], nota, ahora, segundos, p["retenibilidad"], dias, origen))
    ejecutar("INSERT INTO actividad(usuario,tipo,tema,area,valor,detalle,fecha) VALUES(?,?,?,?,?,?,?)",
             (usuario, "repaso", t["tema"], t["area"], nota, json.dumps({"origen": origen}), ahora))
    return p


def r_actual(t, ahora=None):
    if not t.get("estabilidad") or not t.get("ultimo"):
        return None
    return fsrs.retenibilidad(((ahora or time.time()) - t["ultimo"]) / DIA, t["estabilidad"])


# ------------------------------------------------------------------- panel
def _metodo(r):
    try:
        m = json.loads(r["detalle"] or "{}").get("metodo")
    except ValueError:
        m = None
    return m or ("leccion" if r["tema"] else "otro")


def _ret(rows):
    rows = [r for r in rows if r["retenibilidad"] is not None]
    return (sum(1 for r in rows if r["nota"] > 1) / len(rows), len(rows)) if rows else (None, 0)


def analitica(usuario):
    ahora = time.time()
    d30, d56, d90 = ahora - 30 * DIA, ahora - 56 * DIA, ahora - 90 * DIA
    tiempo = filas("SELECT fecha, valor, tema, area, detalle FROM actividad WHERE usuario=? AND tipo='tiempo' AND fecha>?",
                   (usuario, d56))
    act = filas("SELECT tipo, tema, area, valor, detalle, fecha FROM actividad WHERE usuario=? AND fecha>? ORDER BY fecha",
                (usuario, d90))
    rep = filas("""SELECT r.nota, r.fecha, r.segundos, r.retenibilidad, r.dias, r.origen, t.area, t.tema
                   FROM repaso r JOIN tarjeta t ON t.id=r.tarjeta WHERE r.usuario=? AND r.fecha>?""", (usuario, d90))
    areas = cur.areas(usuario)
    nombre_area = lambda a: (areas.get(a) or {}).get("nombre", a or "—")  # noqa: E731

    # --- cuándo: hora del día y día de la semana
    por_hora = [{"h": h, "min": 0.0, "repasos": 0, "bien": 0} for h in range(24)]
    calor = [[0.0] * 24 for _ in range(7)]
    for r in tiempo:
        dt = datetime.fromtimestamp(r["fecha"])
        if r["fecha"] > d30:
            por_hora[dt.hour]["min"] += r["valor"] / 60
        calor[dt.weekday()][dt.hour] += r["valor"] / 60
    for r in rep:
        if r["retenibilidad"] is None:
            continue
        h = datetime.fromtimestamp(r["fecha"]).hour
        por_hora[h]["repasos"] += 1
        por_hora[h]["bien"] += r["nota"] > 1
    franjas = []
    for nombre, a, b in FRANJAS:
        n = sum(por_hora[h]["repasos"] for h in range(a, b))
        bien = sum(por_hora[h]["bien"] for h in range(a, b))
        franjas.append({"franja": nombre, "desde": a, "hasta": b, "repasos": n,
                        "retencion": bien / n if n else None,
                        "min": round(sum(por_hora[h]["min"] for h in range(a, b)))})
    for x in por_hora:
        x["min"] = round(x["min"], 1)

    # --- cómo: métodos
    met = {k: {"id": k, "nombre": v, "min": 0.0, "usos": 0, "puntajes": []} for k, v in METODOS.items()}
    for r in tiempo:
        if r["fecha"] > d30:
            met[_metodo(r)]["min"] += r["valor"] / 60
    for r in act:
        if r["fecha"] < d30:
            continue
        k = {"leccion": "leccion", "quiz": "leccion", "feynman": "leccion", "repaso": "repaso",
             "apunte": "cuaderno", "apunte_eval": "cuaderno", "prueba": "leccion",
             "entrega": "leccion"}.get(r["tipo"])
        if r["tipo"] in ("leccion", "repaso", "apunte", "entrega"):
            met[k]["usos"] += 1
    chats = fila("SELECT COUNT(*) n FROM chat WHERE usuario=? AND rol='usuario' AND fecha>?", (usuario, d30))["n"]
    met["tutor"]["usos"] = chats
    puntajes = {}
    for r in act:
        if r["fecha"] > d30 and r["tipo"] in ("quiz", "feynman", "apunte_eval", "prueba", "practica") and r["valor"] is not None:
            puntajes.setdefault(r["tipo"], []).append(r["valor"])
    ret30, n30 = _ret([r for r in rep if r["fecha"] > d30])
    metodos = [{"id": m["id"], "nombre": m["nombre"], "min": round(m["min"]), "usos": m["usos"]}
               for m in met.values() if m["min"] >= 1 or m["usos"]]
    metodos.sort(key=lambda m: -m["min"])
    resultados = {
        "quiz": _media(puntajes.get("quiz")), "feynman": _media(puntajes.get("feynman")),
        "apuntes": _media(puntajes.get("apunte_eval")), "prueba": _media(puntajes.get("prueba")),
        "practica": _media(puntajes.get("practica")),
        "repaso": ret30, "n": {k: len(v) for k, v in puntajes.items()} | {"repaso": n30}}

    # --- ¿qué método fija mejor? retención de tarjetas según cómo se estudió el tema
    temas_feynman = {r["tema"] for r in filas("SELECT tema FROM avance WHERE usuario=? AND feynman IS NOT NULL", (usuario,))}
    temas_mano = {r["tema"] for r in filas("SELECT DISTINCT tema FROM cuaderno WHERE usuario=? AND tema IS NOT NULL", (usuario,))}
    eficacia = []
    for nombre, conj in (("Explicar con Feynman", temas_feynman), ("Apuntes a mano", temas_mano)):
        con, cn = _ret([r for r in rep if r["tema"] in conj and r["dias"] and r["dias"] >= 1])
        sin, sn = _ret([r for r in rep if r["tema"] and r["tema"] not in conj and r["dias"] and r["dias"] >= 1])
        eficacia.append({"metodo": nombre, "con": con, "n_con": cn, "sin": sin, "n_sin": sn})

    # --- sesiones: tiempo real dentro de la app; un hueco de más de 30 min = sesión nueva
    sesiones, ini, fin = [], None, None
    for r in sorted(tiempo, key=lambda r: r["fecha"]):
        if r["fecha"] < d30:
            continue
        if ini is None or r["fecha"] - fin > 1800:
            if ini is not None:
                sesiones.append((ini, fin))
            ini = r["fecha"]
        fin = r["fecha"]
    if ini is not None:
        sesiones.append((ini, fin))
    largos = [max(1, (b - a) / 60 + 0.5) for a, b in sesiones]
    inicio_horas = [datetime.fromtimestamp(a).hour for a, _ in sesiones]
    ses = {"n": len(sesiones), "mediana": round(statistics.median(largos)) if largos else 0,
           "max": round(max(largos)) if largos else 0,
           "hora_tipica": statistics.mode(inicio_horas) if inicio_horas else None,
           "por_semana": round(len(sesiones) / 4.3, 1)}

    # --- tendencia por semana (8 semanas)
    semanas = []
    lunes = datetime.fromtimestamp(ahora).replace(hour=0, minute=0, second=0, microsecond=0)
    lunes -= timedelta(days=lunes.weekday())
    for i in range(7, -1, -1):
        a = (lunes - timedelta(weeks=i)).timestamp()
        b = a + 7 * DIA
        rr = [r for r in rep if a <= r["fecha"] < b]
        rt, _ = _ret(rr)
        semanas.append({"desde": a, "etiqueta": datetime.fromtimestamp(a).strftime("%d/%m"),
                        "min": round(sum(r["valor"] for r in tiempo if a <= r["fecha"] < b) / 60),
                        "lecciones": sum(1 for r in act if r["tipo"] == "leccion" and a <= r["fecha"] < b),
                        "repasos": len(rr), "retencion": rt})

    # --- curva del olvido real (retención según días desde el repaso anterior)
    cortes = [(0, 1, "<1 d"), (1, 3, "1-3 d"), (3, 7, "3-7 d"), (7, 14, "1-2 sem"), (14, 30, "2-4 sem"), (30, 9999, "+1 mes")]
    curva = []
    for a, b, et in cortes:
        rt, n = _ret([r for r in rep if r["dias"] is not None and a <= r["dias"] < b])
        curva.append({"rango": et, "retencion": rt, "n": n})

    # --- estado de la memoria ahora (FSRS)
    tarj = filas("SELECT * FROM tarjeta WHERE usuario=? AND suspendida=0", (usuario,))
    estado = {"firme": 0, "estable": 0, "olvidando": 0, "olvidada": 0, "nueva": 0}
    por_area, por_tema = {}, {}
    for t in tarj:
        R = r_actual(t, ahora)
        if R is None:
            estado["nueva"] += 1
            continue
        estado["firme" if R >= 0.9 else "estable" if R >= 0.8 else "olvidando" if R >= 0.6 else "olvidada"] += 1
        por_area.setdefault(t["area"], []).append(R)
        if t["tema"]:
            por_tema.setdefault(t["tema"], []).append(R)
    areas_mem = sorted(({"area": a, "nombre": nombre_area(a), "r": sum(v) / len(v), "n": len(v)}
                        for a, v in por_area.items()), key=lambda x: x["r"])
    olvidando = []
    for tid, v in sorted(por_tema.items(), key=lambda x: sum(x[1]) / len(x[1]))[:8]:
        r = sum(v) / len(v)
        if r < 0.85:
            tt = cur.tema(tid, usuario)
            olvidando.append({"id": tid, "t": tt["t"] if tt else tid, "area": nombre_area(tt["area"]) if tt else "", "r": r})
    seg = [r["segundos"] for r in rep if r["segundos"] and r["segundos"] < 300 and r["fecha"] > d30]

    datos = {"por_hora": por_hora, "franjas": franjas, "calor": [[round(x, 1) for x in f] for f in calor],
             "metodos": metodos, "resultados": resultados, "eficacia": eficacia, "sesiones": ses,
             "semanas": semanas, "curva": curva, "memoria": estado, "areas_memoria": areas_mem,
             "olvidando": olvidando, "seg_por_tarjeta": round(statistics.median(seg), 1) if seg else None,
             "minutos_30": round(sum(m["min"] for m in metodos)),
             "dias_activos_14": len({datetime.fromtimestamp(r["fecha"] - 4 * 3600).date() for r in act
                                     if r["fecha"] - 4 * 3600 >= _inicio_ventana(ahora, 14)}),
             "minutos_area": sorted(({"area": a, "nombre": nombre_area(a), "min": round(m)} for a, m in _min_area(tiempo, d30).items()),
                                    key=lambda x: -x["min"])}
    datos["lectura"] = lectura.resumen(usuario)
    datos["consejos"] = consejos(datos, usuario)
    ult = fila("SELECT informe, creado FROM chequeo WHERE usuario=? AND informe IS NOT NULL ORDER BY id DESC LIMIT 1",
               (usuario,))
    datos["informe"] = ult
    return datos


def _inicio_ventana(ahora, dias):
    """Medianoche (día de estudio, corte a las 4 a. m.) de hace `dias`-1 días: ventana de exactamente `dias` días."""
    d = datetime.fromtimestamp(ahora - 4 * 3600).replace(hour=0, minute=0, second=0, microsecond=0)
    return (d - timedelta(days=dias - 1)).timestamp()


def _media(v):
    return sum(v) / len(v) if v else None


def _min_area(tiempo, desde):
    out = {}
    for r in tiempo:
        if r["fecha"] > desde and r["area"]:
            out[r["area"]] = out.get(r["area"], 0) + r["valor"] / 60
    return out


def consejos(d, usuario):
    """Observaciones con datos suficientes (no se inventa nada con 3 repasos)."""
    c = []
    fr = [f for f in d["franjas"] if f["repasos"] >= 20 and f["retencion"] is not None]
    if len(fr) >= 2:
        mejor, peor = max(fr, key=lambda f: f["retencion"]), min(fr, key=lambda f: f["retencion"])
        if mejor["retencion"] - peor["retencion"] >= 0.05:
            c.append(f"Recuerdas mejor en la **{mejor['franja']}** ({mejor['retencion']:.0%}) que en la "
                     f"**{peor['franja']}** ({peor['retencion']:.0%}). Deja lo difícil (lecciones nuevas, quizzes) para la {mejor['franja']}.")
    r = d["resultados"]["repaso"]
    if r is not None and d["resultados"]["n"]["repaso"] >= 30:
        if r < 0.8:
            c.append(f"Tu retención en repasos es {r:.0%}: estás metiendo material nuevo más rápido de lo que lo fijas. "
                     "Baja las tarjetas nuevas por día o repasa a diario.")
        elif r > 0.95:
            c.append(f"Retención {r:.0%}: muy alta. Puedes subir el ritmo (más lecciones o tarjetas nuevas por día).")
        else:
            c.append(f"Retención {r:.0%}: estás en la zona ideal (85-92 %).")
    s = d["sesiones"]
    if s["n"] >= 4:
        if s["mediana"] > 100:
            c.append(f"Tus sesiones duran ~{s['mediana']} min seguidos. A partir de ~50-90 min la atención cae: "
                     "usa el bloque de concentración y descansa 5-10 min entre bloques.")
        elif s["mediana"] < 12:
            c.append(f"Tus sesiones son cortas (~{s['mediana']} min). Sirven para repasar, pero para temas nuevos "
                     "intenta al menos un bloque de 25 min sin interrupciones.")
    if d["dias_activos_14"] and d["dias_activos_14"] < 7:
        c.append(f"Estudiaste {d['dias_activos_14']} de los últimos 14 días. Para la memoria rinde más poco cada día "
                 "que mucho de vez en cuando.")
    for e in d["eficacia"]:
        if e["con"] is not None and e["sin"] is not None and e["n_con"] >= 20 and e["n_sin"] >= 20:
            dif = e["con"] - e["sin"]
            if abs(dif) >= 0.04:
                c.append(f"Los temas trabajados con **{e['metodo'].lower()}** los recuerdas un {abs(dif):.0%} "
                         f"{'mejor' if dif > 0 else 'peor'} ({e['con']:.0%} vs {e['sin']:.0%}).")
    mem = d["memoria"]
    if mem["olvidada"] + mem["olvidando"] >= 10:
        c.append(f"{mem['olvidada'] + mem['olvidando']} tarjetas están por debajo del 80 % de probabilidad de recordarlas: "
                 "ponte al día en Repasar antes de ver temas nuevos.")
    perfil = fila("SELECT datos FROM perfil WHERE usuario=?", (usuario,))
    if perfil:
        pesos = json.loads(perfil["datos"]).get("pesos", {})
        tocadas = {x["area"] for x in d["minutos_area"]}
        olvidadas = [cur.areas(usuario)[a]["nombre"] for a, w in pesos.items()
                     if w >= 3 and a not in tocadas and a in cur.areas(usuario)]
        if olvidadas and d["minutos_30"] >= 60:
            c.append("Áreas con prioridad máxima sin tiempo en 30 días: " + ", ".join(olvidadas) + ".")
    if not c:
        c.append("Aún hay pocos datos. Con 1-2 semanas de uso aparecen aquí tus patrones: mejor hora, método que más "
                 "te sirve, duración ideal de sesión y qué estás olvidando.")
    return c


# ---------------------------------------------------------- chequeo semanal
def clave_semana(t=None):
    return datetime.fromtimestamp(t or time.time()).strftime("%G-S%V")


def aprendido_semana(usuario, desde=None):
    desde = desde or time.time() - 7 * DIA
    vistos = filas("SELECT tema, estado FROM avance WHERE usuario=? AND visto>?", (usuario, desde))
    dominados = filas("""SELECT DISTINCT tema FROM actividad WHERE usuario=? AND fecha>? AND
                         ((tipo='quiz' AND valor>=0.8) OR tipo='prueba')""", (usuario, desde))
    lapsos = filas("""SELECT t.tema, COUNT(*) n FROM repaso r JOIN tarjeta t ON t.id=r.tarjeta
                      WHERE r.usuario=? AND r.fecha>? AND r.nota=1 AND r.dias>=1 GROUP BY t.tema ORDER BY n DESC""",
                   (usuario, desde))
    nombre = lambda tid: (cur.tema(tid, usuario) or {}).get("t", tid) if tid else "Tarjetas sueltas"  # noqa: E731
    return {
        "nuevos": [{"id": v["tema"], "t": nombre(v["tema"])} for v in vistos],
        "dominados": [{"id": v["tema"], "t": nombre(v["tema"])} for v in dominados if v["tema"]],
        "tarjetas_nuevas": fila("SELECT COUNT(*) n FROM tarjeta WHERE usuario=? AND creada>?", (usuario, desde))["n"],
        "repasos": fila("SELECT COUNT(*) n FROM repaso WHERE usuario=? AND fecha>?", (usuario, desde))["n"],
        "minutos": round((fila("""SELECT IFNULL(SUM(valor),0) s FROM actividad WHERE usuario=? AND tipo='tiempo'
                                  AND fecha>?""", (usuario, desde))["s"]) / 60),
        "olvidos": [{"id": x["tema"], "t": nombre(x["tema"]), "n": x["n"]} for x in lapsos[:10]],
    }


def elegir_material(usuario):
    """Temas a examinar (lo de esta semana + lo más viejo sin tocar) y las
    tarjetas con menor probabilidad de recordarse."""
    ahora = time.time()
    estudiados = filas("""SELECT tema, estado, visto, actualizado FROM avance WHERE usuario=?
                          AND estado IN ('visto','dominado','probado')""", (usuario,))
    ultimo = {r["tema"]: r["f"] for r in filas(
        "SELECT tema, MAX(fecha) f FROM actividad WHERE usuario=? AND tema IS NOT NULL GROUP BY tema", (usuario,))}
    nuevos = sorted([e for e in estudiados if (e["visto"] or 0) > ahora - 7 * DIA], key=lambda e: -(e["visto"] or 0))[:4]
    resto = [e for e in estudiados if e not in nuevos and cur.tema(e["tema"], usuario)]
    resto.sort(key=lambda e: ultimo.get(e["tema"], 0))           # lo más olvidado primero
    viejos = random.sample(resto[:12], min(len(resto[:12]), 8 - len(nuevos)))
    temas = [e["tema"] for e in nuevos + viejos if cur.tema(e["tema"], usuario)]
    tarj = [t for t in filas("SELECT * FROM tarjeta WHERE usuario=? AND suspendida=0 AND estabilidad IS NOT NULL",
                             (usuario,))]
    tarj.sort(key=lambda t: r_actual(t, ahora) or 1)
    debiles, otras = tarj[:7], tarj[7:]
    elegidas = debiles + random.sample(otras, min(3, len(otras)))
    return temas, [{"id": t["id"], "frente": t["frente"], "reverso": t["reverso"], "idioma": t["idioma"],
                    "area": t["area"], "r": round(r_actual(t, ahora) or 0, 2)} for t in elegidas]


def esquema_chequeo(n):
    return {"type": "object", "properties": {"preguntas": {
        "type": "array", "minItems": n, "maxItems": n, "items": {"type": "object", "properties": {
            "tema": {"type": "integer", "minimum": 0, "maximum": max(0, n - 1)},
            "pregunta": {"type": "string"},
            "opciones": {"type": "array", "minItems": 4, "maxItems": 4, "items": {"type": "string"}},
            "correcta": {"type": "integer", "minimum": 0, "maximum": 3},
            "explicacion": {"type": "string"}},
            "required": ["tema", "pregunta", "opciones", "correcta", "explicacion"]}}}, "required": ["preguntas"]}


def crear_chequeo(ctx, usuario, perfil):
    from lecciones import SISTEMA_BASE, texto_perfil
    temas, tarjetas = elegir_material(usuario)
    if len(temas) < 2 and len(tarjetas) < 3:
        return {"vacio": True, "motivo": "Todavía no hay suficiente estudiado para un chequeo (mínimo 2 temas o 3 tarjetas)."}
    preguntas = []
    if temas:
        bloques = []
        for i, tid in enumerate(temas):
            t = cur.tema(tid, usuario)
            lec = fila("SELECT contenido FROM leccion WHERE usuario=? AND tema=?", (usuario, tid))
            extracto = (lec["contenido"][:600] if lec else "")
            bloques.append(f"[{i}] {cur.areas(usuario)[t['area']]['nombre']} › {t['t']} — {t['d']}\n{extracto}")
        ctx.fase("Preparando las preguntas del chequeo")
        r = ctx.chat([{"role": "system", "content": SISTEMA_BASE}, {"role": "user", "content": (
            "Chequeo semanal de retención: el estudiante ya estudió estos temas hace días. Escribe EXACTAMENTE una "
            "pregunta de opción múltiple por tema (campo 'tema' = su índice), en el mismo orden. Que evalúe comprensión "
            "y aplicación (no detalles triviales ni copiar frases de la lección): si la acierta, lo recuerda de verdad; "
            "si no, lo olvidó. 4 opciones plausibles, distractores con errores típicos. Explicación de 1-2 frases. "
            "Fórmulas en texto simple o LaTeX corto entre $...$ (nunca \\text ni espacios en LaTeX). "
            "JSON compacto en una sola línea.\n\n"
            + "\n\n".join(bloques))}], max_tokens=3500, temperatura=0.4, esquema=esquema_chequeo(len(temas)))
        preguntas = r["preguntas"]
    ctx.fase("Escribiendo tu informe semanal")
    datos = analitica(usuario)
    resumen = {k: datos[k] for k in ("franjas", "metodos", "resultados", "sesiones", "semanas", "memoria",
                                      "minutos_area", "olvidando", "dias_activos_14", "consejos")}
    resumen["semana"] = aprendido_semana(usuario)
    informe = ctx.chat([{"role": "system", "content": SISTEMA_BASE}, {"role": "user", "content": (
        f"{texto_perfil(perfil)}\nEres su coach de aprendizaje. Con estos datos reales de su última semana y su historial "
        "escribe el informe semanal en markdown (250-400 palabras): ## Cómo aprendiste esta semana (qué métodos, cuándo, "
        "cuánto) ## Lo que funciona ## Lo que se está olvidando ## Plan para la próxima semana (3-5 acciones concretas: "
        "horas, métodos, temas). Usa SOLO estos datos; si hay pocos datos, dilo y da el plan para empezar bien. "
        "No inventes cifras.\n\nDATOS:\n" + json.dumps(resumen, ensure_ascii=False, default=str)[:7000])}],
        max_tokens=1100, temperatura=0.4)
    cid = ejecutar("""INSERT INTO chequeo(usuario,semana,temas,preguntas,tarjetas,informe,creado) VALUES(?,?,?,?,?,?,?)""",
                   (usuario, clave_semana(), json.dumps(temas), json.dumps(preguntas, ensure_ascii=False),
                    json.dumps(tarjetas, ensure_ascii=False), informe, time.time())).lastrowid
    return {"chequeo": cid}


def responder_chequeo(usuario, cid, respuestas, tarjetas_resp):
    c = fila("SELECT * FROM chequeo WHERE id=? AND usuario=?", (cid, usuario))
    if not c or c["completado"]:
        return {"error": "chequeo inexistente o ya respondido"}
    temas = json.loads(c["temas"])
    preguntas = json.loads(c["preguntas"])
    elegidas = {int(r["i"]): int(r["elegida"]) for r in respuestas}
    ahora = time.time()
    res_temas = []
    for i, p in enumerate(preguntas):
        tid = temas[p["tema"]] if p["tema"] < len(temas) else None
        ok = elegidas.get(i) == p["correcta"]
        t = cur.tema(tid, usuario) if tid else None
        res_temas.append({"id": tid, "t": t["t"] if t else "", "area": t["area"] if t else None, "ok": ok})
        if tid and not ok:
            # Olvidado: deja de contar como dominado y sus tarjetas vuelven ya al repaso
            ejecutar("""UPDATE avance SET estado='visto', quiz=MIN(IFNULL(quiz,0),0.6), actualizado=?
                        WHERE usuario=? AND tema=? AND estado IN ('dominado','probado')""", (ahora, usuario, tid))
            ejecutar("UPDATE tarjeta SET vence=? WHERE usuario=? AND tema=? AND estabilidad IS NOT NULL",
                     (ahora, usuario, tid))
        ejecutar("INSERT INTO actividad(usuario,tipo,tema,area,valor,fecha) VALUES(?,?,?,?,?,?)",
                 (usuario, "chequeo_tema", tid, t["area"] if t else None, 1 if ok else 0, ahora))
    res_tarj = []
    for r in tarjetas_resp:
        t = fila("SELECT * FROM tarjeta WHERE id=? AND usuario=?", (int(r["id"]), usuario))
        if t:
            aplicar_repaso(usuario, t, 3 if r.get("recordada") else 1, r.get("segundos"), "chequeo")
            res_tarj.append({"id": t["id"], "frente": t["frente"], "ok": bool(r.get("recordada"))})
    total = len(res_temas) + len(res_tarj)
    bien = sum(x["ok"] for x in res_temas) + sum(x["ok"] for x in res_tarj)
    resultado = {"temas": res_temas, "tarjetas": res_tarj, "puntaje": bien / total if total else None,
                 "semana": aprendido_semana(usuario, c["creado"] - 7 * DIA)}
    ejecutar("UPDATE chequeo SET resultado=?, completado=? WHERE id=?",
             (json.dumps(resultado, ensure_ascii=False), ahora, cid))
    ejecutar("INSERT INTO actividad(usuario,tipo,valor,fecha) VALUES(?,?,?,?)",
             (usuario, "chequeo", resultado["puntaje"], ahora))
    return resultado


def historial(usuario):
    out = []
    for c in filas("SELECT id, semana, creado, completado, resultado FROM chequeo WHERE usuario=? ORDER BY id DESC LIMIT 26",
                   (usuario,)):
        r = json.loads(c["resultado"]) if c["resultado"] else None
        out.append({"id": c["id"], "semana": c["semana"], "creado": c["creado"], "completado": c["completado"],
                    "puntaje": r["puntaje"] if r else None,
                    "olvidados": sum(1 for x in r["temas"] if not x["ok"]) + sum(1 for x in r["tarjetas"] if not x["ok"]) if r else None,
                    "retenidos": sum(1 for x in r["temas"] if x["ok"]) + sum(1 for x in r["tarjetas"] if x["ok"]) if r else None})
    return out


def dia_chequeo(usuario=None):
    """Día del chequeo semanal de cada persona (0 = lunes … 6 = domingo); por defecto el general."""
    propio = kv_get(f"chequeo_dia:{usuario}", None) if usuario else None
    return int(propio if propio is not None else kv_get("chequeo_dia", 6))
