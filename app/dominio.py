"""Programa de dominio: llegar DE VERDAD a la frontera de una meta, en un plazo, y mantenerse al día.

Una meta («entender y aplicar la relatividad y la cuántica») no termina en un resumen: termina cuando puedes
resolver problemas, leer los papers de hoy, seguir una conferencia del tema y proponer algo propio. Para eso:

- 📅 Plan con plazo: con tu ritmo real (minutos por tema), cuánto cabe en el plazo, hitos semana a semana y si vas
  adelantado o atrasado. Los módulos de una meta con plazo pasan primero en el plan del día.
- 🔭 Frontera viva: mapa del estado del arte hecho con investigación REAL (OpenAlex: revisiones recientes, lo más
  citado de los últimos 2 años y preprints de arXiv) y la web: líneas activas, problemas abiertos, vocabulario de
  charla, conferencias y papers clave. Se renueva cada mes, dice qué cambió y agrega a la ruta los temas nuevos.
- 📄 Lectura guiada de papers: la habilidad de una conferencia. Un paper real de la frontera con su contexto,
  requisitos (enlazados a tu ruta), glosario y 6 preguntas (problema, método, resultado, límites, conexión, crítica)
  que la IA corrige.
- 💡 Tu aporte: propones una idea o pregunta de investigación y la IA la contrasta con los problemas abiertos y los
  papers: originalidad, viabilidad, si ya existe, el siguiente paso y cómo presentarla.
"""
import json
import re
import time
from datetime import datetime

import adaptativo as aa
import ciencia
import curriculo as cur
import ia
from base import ejecutar, fila, filas, kv_get, kv_set

DIA = 86400
RENOVAR_DIAS = 30

ejecutar("""CREATE TABLE IF NOT EXISTS frontera_meta (
  objetivo INTEGER, version INTEGER, usuario TEXT, datos TEXT, creada REAL, PRIMARY KEY (objetivo, version))""")
ejecutar("""CREATE TABLE IF NOT EXISTS lectura_paper (
  id INTEGER PRIMARY KEY AUTOINCREMENT, usuario TEXT, objetivo INTEGER, paper TEXT, guia TEXT,
  respuestas TEXT, creada REAL, actualizada REAL)""")
ejecutar("""CREATE TABLE IF NOT EXISTS aporte (
  id INTEGER PRIMARY KEY AUTOINCREMENT, usuario TEXT, objetivo INTEGER, texto TEXT, evaluacion TEXT, creada REAL)""")


def _objetivo(usuario, oid):
    return fila("SELECT * FROM objetivo WHERE id=? AND usuario=?", (int(oid), usuario))


# ------------------------------------------------------------------ plan con plazo
def poner_plazo(usuario, oid, semanas):
    """semanas = 0 quita el plazo. Guarda el punto de partida para medir si vas adelantado o atrasado."""
    o = _objetivo(usuario, oid)
    if not o:
        raise ValueError("meta desconocida")
    if not semanas:
        kv_set(f"programa:{usuario}:{o['id']}", None)
        return None
    e = cur.estado_objetivo(usuario, o)
    prog = {"semanas": int(semanas), "inicio": time.time(), "hechos_inicio": e["temas_hechos"],
            "total_inicio": e["temas_total"]}
    kv_set(f"programa:{usuario}:{o['id']}", prog)
    return prog


def programas(usuario):
    """{objetivo: programa} de las metas activas con plazo."""
    out = {}
    for o in filas("SELECT id FROM objetivo WHERE usuario=? AND estado='activo'", (usuario,)):
        p = kv_get(f"programa:{usuario}:{o['id']}")
        if p:
            out[o["id"]] = p
    return out


def estado_programa(usuario, perfil, oid):
    o = _objetivo(usuario, oid)
    if not o:
        return None
    e = cur.estado_objetivo(usuario, o)
    prog = kv_get(f"programa:{usuario}:{o['id']}")
    rit = aa.ritmo(usuario)
    pend = [(p, t) for p in e["pasos"] for t in p["faltan"]]   # ya en orden: nivel y requisitos
    faltan = len(pend)
    horas = round(faltan * rit["min_por_tema"] / 60, 1)
    minutos_meta = float(perfil.get("minutos_dia") or 60)
    out = {"faltan": faltan, "horas": horas, "ritmo": rit, "minutos_meta": minutos_meta, "programa": prog,
           # sin plazo: cuánto tardaría a tu meta diaria y a tu ritmo real
           "dias_a_tu_meta": round(horas * 60 / (minutos_meta * aa.FRACCION_NUEVO)) if faltan else 0,
           "dias_a_tu_ritmo": (round(horas * 60 / (rit["min_dia_real"] * aa.FRACCION_NUEVO))
                               if faltan and rit["min_dia_real"] else None)}
    if not prog:
        return out
    fin = prog["inicio"] + prog["semanas"] * 7 * DIA
    ahora = time.time()
    dias_rest = max(1.0, (fin - ahora) / DIA)
    transcurrido = min(1.0, max(0.0, (ahora - prog["inicio"]) / (fin - prog["inicio"])))
    por_hacer_inicio = max(1, prog["total_inicio"] - prog["hechos_inicio"])
    esperado = prog["hechos_inicio"] + por_hacer_inicio * transcurrido
    min_dia = round(faltan * rit["min_por_tema"] / dias_rest / aa.FRACCION_NUEVO)
    # hitos: lo que falta, repartido en las semanas que quedan (en orden de ruta)
    semanas_rest = max(1, -(-int(dias_rest) // 7))
    por_semana = -(-faltan // semanas_rest) if faltan else 0
    hitos = []
    for k in range(semanas_rest):
        trozo = pend[k * por_semana:(k + 1) * por_semana]
        if not trozo:
            break
        mods = []
        for p, t in trozo:
            if not mods or mods[-1]["ref"] != p["ref"]:
                mods.append({"ref": p["ref"], "t": p["t"], "nivel": p["nivel"], "temas": 0, "primero": t["id"]})
            mods[-1]["temas"] += 1
        hitos.append({"semana": k + 1, "desde": ahora + k * 7 * DIA, "temas": len(trozo), "modulos": mods})
    out.update({"fin": fin, "dias_restantes": round(dias_rest), "temas_por_dia": round(faltan / dias_rest, 2),
                "min_dia_necesarios": min_dia, "esperado": round(esperado, 1), "hechos": e["temas_hechos"],
                "diferencia": round(e["temas_hechos"] - esperado, 1), "hitos": hitos,
                "viable_meta": min_dia <= minutos_meta,
                "viable_real": bool(rit["min_dia_real"]) and min_dia <= rit["min_dia_real"]})
    return out


def necesidad_diaria(usuario, perfil):
    """Temas nuevos por día que piden TODAS tus metas con plazo (para avisar en el plan del día)."""
    total, nombres = 0.0, []
    for oid in programas(usuario):
        est = estado_programa(usuario, perfil, oid)
        if est and est.get("temas_por_dia"):
            total += est["temas_por_dia"]
            nombres.append(fila("SELECT titulo FROM objetivo WHERE id=?", (oid,))["titulo"])
    return total, nombres


# ------------------------------------------------------------------ frontera viva
def ultima_frontera(oid):
    r = fila("SELECT * FROM frontera_meta WHERE objetivo=? ORDER BY version DESC LIMIT 1", (int(oid),))
    if not r:
        return None
    d = json.loads(r["datos"])
    d.update({"version": r["version"], "creada": r["creada"]})
    return d


def _temas_de_la_ruta(usuario, o):
    plan = json.loads(o["plan"] or "{}")
    refs = cur.cierre_prerrequisitos(plan.get("modulos", []) + plan.get("extra", []), usuario)
    out = []
    for r in refs:
        m = cur.modulo(r, usuario)
        if m:
            out.append(f"{m['t']}: " + "; ".join(t["t"] for t in m["temas_obj"]))
    return out


def _esquema_frontera(n_p, n_w):
    refs = {"type": "array", "maxItems": 6, "items": {"type": "string"}}
    return {"type": "object", "properties": {
        "estado_del_arte": {"type": "string"},
        "lineas": {"type": "array", "minItems": 3, "maxItems": 7, "items": {"type": "object", "properties": {
            "nombre": {"type": "string"}, "que_es": {"type": "string"}, "por_que_importa": {"type": "string"},
            "madurez": {"type": "string", "enum": ["emergente", "en auge", "consolidada"]}, "refs": refs},
            "required": ["nombre", "que_es", "por_que_importa", "madurez", "refs"]}},
        "problemas_abiertos": {"type": "array", "minItems": 3, "maxItems": 8, "items": {"type": "object", "properties": {
            "problema": {"type": "string"}, "por_que_es_dificil": {"type": "string"},
            "que_haria_falta": {"type": "string"}, "refs": refs},
            "required": ["problema", "por_que_es_dificil", "que_haria_falta", "refs"]}},
        "vocabulario": {"type": "array", "minItems": 6, "maxItems": 20, "items": {"type": "object", "properties": {
            "termino": {"type": "string"}, "significado": {"type": "string"}}, "required": ["termino", "significado"]}},
        "conferencias": {"type": "array", "maxItems": 8, "items": {"type": "object", "properties": {
            "nombre": {"type": "string"}, "nota": {"type": "string"}, "ref": {"type": "string"}},
            "required": ["nombre", "nota", "ref"]}},
        "papers_clave": {"type": "array", "maxItems": 8, "items": {"type": "object", "properties": {
            "p": {"type": "integer", "minimum": 1, "maximum": max(1, n_p)}, "titulo": {"type": "string"},
            "por_que": {"type": "string"}}, "required": ["p", "titulo", "por_que"]}},
        "temas_nuevos": {"type": "array", "maxItems": 8, "items": {"type": "object", "properties": {
            "t": {"type": "string"}, "d": {"type": "string"}}, "required": ["t", "d"]}},
        "que_cambio": {"type": "string"}},
        "required": ["estado_del_arte", "lineas", "problemas_abiertos", "vocabulario", "conferencias",
                     "papers_clave", "temas_nuevos", "que_cambio"]}


def generar_frontera(ctx, usuario, perfil, oid):
    import lecciones as lec
    o = _objetivo(usuario, oid)
    if not o:
        raise ValueError("meta desconocida")
    previa = ultima_frontera(o["id"])
    anio = datetime.now().year
    ctx.fase("Eligiendo qué investigar de la frontera")
    q = ctx.chat([{"role": "system", "content": lec.SISTEMA_BASE}, {"role": "user", "content": (
        f"Meta del estudiante: «{o['titulo']}». {o['descripcion'] or ''}\n"
        "Escribe 4-6 consultas de búsqueda académica en INGLÉS (2-5 palabras cada una, términos técnicos que usan los "
        "artículos), una por cada línea de investigación ACTIVA hoy en la frontera de esta meta (no lo básico). "
        "JSON compacto.")}], max_tokens=300, temperatura=0.2, mostrar=False,
        esquema={"type": "object", "properties": {"consultas": {"type": "array", "minItems": 3, "maxItems": 6,
                                                                  "items": {"type": "string"}}},
                 "required": ["consultas"]})
    consultas = [c.strip() for c in q["consultas"] if c.strip()][:6]
    ctx.fase("Buscando revisiones, lo más citado y preprints recientes (OpenAlex)")
    papers, vistos = [], set()
    for c in consultas:
        for p in ciencia.frontera(c, 6):
            if p["openalex"] not in vistos:
                vistos.add(p["openalex"])
                papers.append(p)
    papers = papers[:24]
    ctx.fase("Buscando problemas abiertos y conferencias en la web")
    web = []
    for consulta in (f"{consultas[0]} open problems review", f"{consultas[0]} conference {anio}",
                     f"{o['titulo']} estado del arte {anio}"):
        for w in ia.buscar_web(consulta, 4, "en" if consulta[0].isascii() else "es"):
            if w["url"] not in {x["url"] for x in web}:
                web.append(w)
    web = web[:10]
    material = ciencia.bloque_prompt(papers) + "\n" + "\n".join(
        f"[W{i + 1}] {w['titulo']} — {w['url']}\n{w['texto']}" for i, w in enumerate(web))
    ruta = _temas_de_la_ruta(usuario, o)
    ctx.fase("Escribiendo el mapa de la frontera")
    prompt = (
        f"{lec.texto_perfil(perfil)}\n\nMeta: «{o['titulo']}». {o['descripcion'] or ''}\n"
        f"Fecha de hoy: {datetime.now():%Y-%m-%d}.\n\n"
        "Arma el MAPA DE LA FRONTERA de esta meta para alguien que quiere entender la investigación actual, seguir "
        "una conferencia del tema y llegar a aportar. Usa SOLO el material de abajo (papers [Pn] y web [Wn]) para "
        "afirmar qué está pasando hoy; cita con [Pn]/[Wn]. Si un paper parece marginal, dudoso o fuera del consenso, "
        "no lo uses como referencia central (y si lo mencionas, dilo). Nunca inventes autores, cifras ni conferencias.\n"
        "- estado_del_arte: 350-600 palabras en markdown: qué se sabe, qué se discute y dónde está el borde.\n"
        "- lineas: líneas de investigación activas, cada una con qué es, por qué importa, su madurez y refs.\n"
        "- problemas_abiertos: qué no se ha resuelto, por qué es difícil y qué haría falta.\n"
        "- vocabulario: los términos que se oyen en las charlas del tema, con su significado claro.\n"
        "- conferencias: SOLO las que aparezcan en el material web (ref = [Wn]); si no hay, lista vacía.\n"
        "- papers_clave: 4-8 papers para leer en orden, de lo más accesible (revisiones) a lo más avanzado: su número "
        "[Pn], su título EXACTO copiado del material y por qué leerlo.\n"
        "- temas_nuevos: temas que hacen falta para seguir la frontera y que la ruta del estudiante (abajo) NO cubre; "
        "'t' = título corto, 'd' = descripción corta.\n"
        + ("- que_cambio: compara con el mapa anterior (abajo): qué apareció, qué avanzó, qué perdió fuerza.\n"
           if previa else "- que_cambio: cadena vacía (es el primer mapa).\n")
        + ("\nMAPA ANTERIOR (resumen):\n" + previa.get("estado_del_arte", "")[:2500] + "\nLíneas: "
           + "; ".join(x["nombre"] for x in previa.get("lineas", [])) + "\n" if previa else "")
        + "\nRUTA ACTUAL DEL ESTUDIANTE (módulos: temas):\n" + "\n".join(ruta)[:7000]
        + "\n\nMATERIAL:\n" + material[:26000])
    r = ctx.chat([{"role": "system", "content": lec.SISTEMA_BASE}, {"role": "user", "content": prompt}],
                 max_tokens=6000, temperatura=0.3, esquema=_esquema_frontera(len(papers), len(web)))
    r["papers"] = papers
    r["web"] = web
    r["consultas"] = consultas
    r["papers_clave"] = _emparejar_por_titulo(r.get("papers_clave", []), papers)
    agregados = _agregar_temas(usuario, o, r.get("temas_nuevos", []))
    r["temas_agregados"] = agregados
    version = (previa["version"] + 1) if previa else 1
    ejecutar("INSERT INTO frontera_meta(objetivo,version,usuario,datos,creada) VALUES(?,?,?,?,?)",
             (o["id"], version, usuario, json.dumps(r, ensure_ascii=False), time.time()))
    return {"objetivo": o["id"], "version": version, "temas_agregados": agregados}


def _palabras(t):
    return set(re.findall(r"[a-z0-9]{4,}", str(t).lower()))


def _emparejar_por_titulo(clave, papers):
    """La IA a veces confunde los números [Pn]: se usa el título que escribió para ubicar el paper correcto (y así la
    explicación queda con su paper). Si no se reconoce ninguno, la recomendación se descarta."""
    out, usados = [], set()
    for x in clave:
        w = _palabras(x.get("titulo", ""))
        mejor, punt = None, 0.0
        for i, p in enumerate(papers):
            pw = _palabras(p["titulo"])
            s_ = len(w & pw) / max(1, len(w | pw))
            if s_ > punt:
                mejor, punt = i + 1, s_
        n = mejor if punt >= 0.3 else (x["p"] if 1 <= x["p"] <= len(papers) and not w else None)
        if n and n not in usados:
            usados.add(n)
            out.append({"p": n, "por_que": x["por_que"]})
    return out


def _agregar_temas(usuario, o, nuevos):
    """Los temas que pide la frontera y la ruta no tenía van al módulo «🔭 Frontera viva» del área de la meta
    (se agregan al final: los temas ya estudiados no cambian de id)."""
    if not nuevos:
        return []
    area_id = f"obj{o['id']}"
    r = fila("SELECT datos FROM area_extra WHERE id=? AND usuario=?", (area_id, usuario))
    plan = json.loads(o["plan"] or "{}")
    if r:
        area = json.loads(r["datos"])
    else:
        area = {"id": area_id, "nombre": f"🎯 {o['titulo']}", "icono": "🎯", "grupo": "Mis objetivos",
                "color": "#f39c12", "descripcion": plan.get("resumen", ""), "objetivo": o["id"], "usuario": usuario,
                "recursos": [], "modulos": []}
    mod = next((m for m in area["modulos"] if m["id"] == "frontera"), None)
    if not mod:
        previos = [m["id"] for m in area["modulos"]]
        pre = [f"{area_id}.{previos[-1]}"] if previos else [r_ for r_ in plan.get("modulos", [])][-1:]
        mod = {"id": "frontera", "t": "🔭 Frontera viva (se actualiza cada mes)", "nivel": 5, "pre": pre, "temas": []}
        area["modulos"].append(mod)
        plan.setdefault("extra", []).append(f"{area_id}.frontera")
        plan.setdefault("razones", {})[f"{area_id}.frontera"] = "Lo que hoy se investiga y la ruta aún no cubría."
        ejecutar("UPDATE objetivo SET plan=? WHERE id=?", (json.dumps(plan, ensure_ascii=False), o["id"]))
    existentes = {re.sub(r"\W+", " ", str(t).split("|")[0].lower()).strip() for t in mod["temas"]}
    agregados = []
    for t in nuevos:
        clave = re.sub(r"\W+", " ", t["t"].lower()).strip()
        if clave and clave not in existentes:
            existentes.add(clave)
            mod["temas"].append(f"{t['t'].replace('|', '/')}|{t['d'].replace('|', '/')}")
            agregados.append(t["t"])
    ejecutar("INSERT OR REPLACE INTO area_extra(id,usuario,datos,creado) VALUES(?,?,?,?)",
             (area_id, usuario, json.dumps(area, ensure_ascii=False), time.time()))
    return agregados


def fronteras_vencidas(usuario):
    """Metas activas cuyo mapa de la frontera no existe o tiene más de RENOVAR_DIAS días."""
    out = []
    for o in filas("SELECT id FROM objetivo WHERE usuario=? AND estado='activo'", (usuario,)):
        f = fila("SELECT MAX(creada) c FROM frontera_meta WHERE objetivo=?", (o["id"],))
        if not f["c"] or time.time() - f["c"] > RENOVAR_DIAS * DIA:
            out.append(o["id"])
    return out


# ------------------------------------------------------------- lectura guiada de papers
ESQUEMA_GUIA = {"type": "object", "properties": {
    "idea_central": {"type": "string"}, "por_que_importa": {"type": "string"}, "como_leerlo": {"type": "string"},
    "requisitos": {"type": "array", "maxItems": 8, "items": {"type": "object", "properties": {
        "concepto": {"type": "string"}, "explicacion": {"type": "string"}, "tema": {"type": "string"}},
        "required": ["concepto", "explicacion", "tema"]}},
    "glosario": {"type": "array", "maxItems": 15, "items": {"type": "object", "properties": {
        "termino": {"type": "string"}, "significado": {"type": "string"}}, "required": ["termino", "significado"]}},
    "preguntas": {"type": "array", "minItems": 6, "maxItems": 6, "items": {"type": "object", "properties": {
        "tipo": {"type": "string", "enum": ["problema", "metodo", "resultado", "limites", "conexion", "critica"]},
        "pregunta": {"type": "string"}, "respuesta_modelo": {"type": "string"}},
        "required": ["tipo", "pregunta", "respuesta_modelo"]}}},
    "required": ["idea_central", "por_que_importa", "como_leerlo", "requisitos", "glosario", "preguntas"]}


def guia_paper(ctx, usuario, perfil, oid, n):
    import lecciones as lec
    import noticias as nt
    o = _objetivo(usuario, oid)
    f = ultima_frontera(oid) if o else None
    if not f or not 1 <= int(n) <= len(f["papers"]):
        raise ValueError("paper desconocido")
    p = f["papers"][int(n) - 1]
    previa = fila("SELECT id FROM lectura_paper WHERE usuario=? AND objetivo=? AND paper LIKE ?",
                  (usuario, o["id"], f'%"openalex": "{p["openalex"]}"%'))
    if previa:
        return {"id": previa["id"]}
    texto = ""
    if p.get("abierto") and not p["abierto"].lower().endswith(".pdf"):
        ctx.fase("Leyendo el texto abierto del paper")
        texto = nt._texto_articulo(p["abierto"], 14000)
    temas = []
    for r in cur.cierre_prerrequisitos(json.loads(o["plan"] or "{}").get("modulos", []) +
                                       json.loads(o["plan"] or "{}").get("extra", []), usuario):
        m = cur.modulo(r, usuario)
        if m:
            temas += [f"{t['id']} = {t['t']}" for t in m["temas_obj"]]
    ctx.fase("Preparando la lectura guiada")
    prompt = (
        f"{lec.texto_perfil(perfil)}\n\nPrepara una LECTURA GUIADA de este paper para que el estudiante lo lea él "
        "mismo y lo entienda como lo entendería alguien en una conferencia del tema (no un resumen para no leerlo).\n"
        f"Paper: {p['autores']} ({p['anio']}). «{p['titulo']}». {p['revista'] or p['tipo']}. {p['citas']} citas.\n"
        f"Resumen: {p['resumen']}\n" + (f"Texto disponible (parcial):\n{texto}\n" if texto else
                                         "(Solo hay resumen: las preguntas deben poder responderse leyendo el paper.)\n")
        + "\n- idea_central: una frase.\n- por_que_importa: por qué existe este trabajo y qué cambia (3-5 frases).\n"
        "- como_leerlo: en qué orden leer las secciones y en qué fijarse (lista markdown).\n"
        "- requisitos: conceptos necesarios para entenderlo, con explicación breve y, si existe en su ruta, el id del "
        "tema ('tema'; si no, cadena vacía). Usa SOLO ids de esta lista:\n" + "\n".join(temas)[:6000] + "\n"
        "- glosario: términos del paper.\n- preguntas: exactamente 6, una de cada tipo (problema, metodo, resultado, "
        "limites, conexion con su ruta/meta, critica), con respuesta_modelo basada en el paper. Si algo no se puede "
        "saber con el material dado, la respuesta modelo lo dice. Nunca inventes resultados ni cifras.")
    g = ctx.chat([{"role": "system", "content": lec.SISTEMA_BASE}, {"role": "user", "content": prompt}],
                 max_tokens=4000, temperatura=0.3, esquema=ESQUEMA_GUIA)
    ids = {t.split(" = ")[0] for t in temas}
    for r in g["requisitos"]:
        if r["tema"] not in ids:
            r["tema"] = ""
    lid = ejecutar("""INSERT INTO lectura_paper(usuario,objetivo,paper,guia,respuestas,creada,actualizada)
                      VALUES(?,?,?,?,?,?,?)""", (usuario, o["id"], json.dumps(p, ensure_ascii=False),
                                                 json.dumps(g, ensure_ascii=False), "{}", time.time(), time.time())).lastrowid
    return {"id": lid}


def lectura(usuario, lid):
    r = fila("SELECT * FROM lectura_paper WHERE id=? AND usuario=?", (int(lid), usuario))
    if not r:
        return None
    return {"id": r["id"], "objetivo": r["objetivo"], "paper": json.loads(r["paper"]), "guia": json.loads(r["guia"]),
            "respuestas": json.loads(r["respuestas"] or "{}"), "creada": r["creada"]}


def corregir_respuesta(ctx, usuario, lid, i, respuesta):
    import lecciones as lec
    lec_ = lectura(usuario, lid)
    if not lec_ or not 0 <= int(i) < len(lec_["guia"]["preguntas"]):
        raise ValueError("pregunta desconocida")
    q = lec_["guia"]["preguntas"][int(i)]
    p = lec_["paper"]
    ctx.fase("Corrigiendo tu respuesta")
    nota = ctx.chat([{"role": "system", "content": lec.SISTEMA_BASE}, {"role": "user", "content": (
        f"Lectura guiada del paper «{p['titulo']}» ({p['anio']}). Resumen: {p['resumen']}\n\n"
        f"Pregunta ({q['tipo']}): {q['pregunta']}\nRespuesta de referencia: {q['respuesta_modelo']}\n"
        f"Respuesta del estudiante: {respuesta}\n\nCorrige como lo haría un investigador del tema: acepta "
        "formulaciones equivalentes y premia el razonamiento propio y la crítica bien fundada aunque difiera de la "
        "referencia. JSON: puntaje 0-100, bien, mal, falto, siguiente (un consejo accionable). Frases cortas.")}],
        max_tokens=700, temperatura=0.2, esquema=lec.ESQUEMA_NOTA)
    nota = lec.normalizar_puntaje(nota) if hasattr(lec, "normalizar_puntaje") else nota
    r = fila("SELECT respuestas FROM lectura_paper WHERE id=?", (int(lid),))
    resp = json.loads(r["respuestas"] or "{}")
    resp[str(int(i))] = {"respuesta": respuesta, "nota": nota, "fecha": time.time()}
    ejecutar("UPDATE lectura_paper SET respuestas=?, actualizada=? WHERE id=?",
             (json.dumps(resp, ensure_ascii=False), time.time(), int(lid)))
    return nota


def lecturas_de(usuario, oid):
    out = []
    for r in filas("SELECT id, paper, respuestas, guia FROM lectura_paper WHERE usuario=? AND objetivo=? ORDER BY id",
                   (usuario, int(oid))):
        p, resp = json.loads(r["paper"]), json.loads(r["respuestas"] or "{}")
        notas = [x["nota"]["puntaje"] for x in resp.values() if x.get("nota")]
        out.append({"id": r["id"], "titulo": p["titulo"], "anio": p["anio"], "openalex": p.get("openalex"),
                    "respondidas": len(resp), "total": len(json.loads(r["guia"])["preguntas"]),
                    "promedio": round(sum(notas) / len(notas)) if notas else None})
    return out


# ------------------------------------------------------------------ tu aporte
ESQUEMA_APORTE = {"type": "object", "properties": {
    "originalidad": {"type": "integer", "minimum": 1, "maximum": 5},
    "viabilidad": {"type": "integer", "minimum": 1, "maximum": 5},
    "problema_que_toca": {"type": "string"}, "ya_existe": {"type": "string"},
    "fortalezas": {"type": "string"}, "debilidades": {"type": "string"},
    "siguiente_paso": {"type": "string"}, "como_presentarlo": {"type": "string"},
    "que_te_falta_aprender": {"type": "string"}},
    "required": ["originalidad", "viabilidad", "problema_que_toca", "ya_existe", "fortalezas", "debilidades",
                 "siguiente_paso", "como_presentarlo", "que_te_falta_aprender"]}


def evaluar_aporte(ctx, usuario, perfil, oid, texto):
    import lecciones as lec
    o = _objetivo(usuario, oid)
    f = ultima_frontera(oid) if o else None
    if not o:
        raise ValueError("meta desconocida")
    ctx.fase("Contrastando tu idea con la frontera")
    contexto = ""
    if f:
        contexto = ("PROBLEMAS ABIERTOS:\n" + "\n".join(f"- {x['problema']}: {x['por_que_es_dificil']}"
                                                        for x in f["problemas_abiertos"])
                    + "\n\nPAPERS:\n" + ciencia.bloque_prompt(f["papers"][:16]))
    ev = ctx.chat([{"role": "system", "content": lec.SISTEMA_BASE}, {"role": "user", "content": (
        f"{lec.texto_perfil(perfil)}\n\nMeta: «{o['titulo']}». El estudiante propone esta idea, pregunta o enfoque de "
        f"investigación:\n«{texto}»\n\nEvalúala como un investigador generoso pero honesto, usando el contexto: "
        "originalidad y viabilidad (1-5), qué problema abierto toca, si algo parecido ya existe en los papers dados "
        "(cita [Pn]; si no lo sabes, dilo), fortalezas, debilidades, el siguiente paso concreto (un experimento, un "
        "cálculo, una lectura), cómo presentarla en 2-3 frases en una conferencia, y qué le falta aprender para "
        "desarrollarla.\n\n" + contexto[:20000])}], max_tokens=1600, temperatura=0.3, esquema=ESQUEMA_APORTE)
    q = ctx.chat([{"role": "user", "content": f"Escribe SOLO una búsqueda académica en inglés de 3-6 palabras para "
                                               f"encontrar trabajos parecidos a esta idea: {texto}"}],
                 max_tokens=40, temperatura=0.1, mostrar=False).strip().strip('"')[:120]
    ev["novedad_literatura"] = _chequeo_novedad(ctx, texto, q) if q else None
    aid = ejecutar("INSERT INTO aporte(usuario,objetivo,texto,evaluacion,creada) VALUES(?,?,?,?,?)",
                   (usuario, o["id"], texto, json.dumps(ev, ensure_ascii=False), time.time())).lastrowid
    return {"id": aid, **ev}


def aportes_de(usuario, oid):
    return [{"id": r["id"], "texto": r["texto"], "evaluacion": json.loads(r["evaluacion"]), "creada": r["creada"]}
            for r in filas("SELECT * FROM aporte WHERE usuario=? AND objetivo=? ORDER BY id DESC", (usuario, int(oid)))]


# ------------------------------------------------------------------ 🌳 mapa de sub-ramas
def _esquema_ramas(refs):
    return {"type": "object", "properties": {"ramas": {"type": "array", "minItems": 4, "maxItems": 22, "items": {
        "type": "object", "properties": {
            "nombre": {"type": "string"},
            "importancia": {"type": "string", "enum": ["esencial", "importante", "complementaria"]},
            "por_que": {"type": "string"},
            "nivel": {"type": "integer", "minimum": 1, "maximum": 5},
            "temas_clave": {"type": "array", "minItems": 3, "maxItems": 8, "items": {"type": "string"}},
            "cubierta_por": {"type": "array", "maxItems": 4, "items": {"type": "string", "enum": refs}}},
        "required": ["nombre", "importancia", "por_que", "nivel", "temas_clave", "cubierta_por"]}}},
        "required": ["ramas"]}


def mapear_ramas(ctx, usuario, perfil, oid):
    """Todo el árbol de conocimiento de la meta (sub-ramas y sus fundamentos, p. ej. la matemática que piden), con lo
    esencial marcado; cada rama esencial o importante que ninguna parte de la ruta cubre se vuelve un módulo nuevo y
    los módulos del catálogo que la cubren entran a la meta. Así la ruta no deja huecos."""
    import lecciones as lec
    o = _objetivo(usuario, oid)
    if not o:
        raise ValueError("meta desconocida")
    plan = json.loads(o["plan"] or "{}")
    catalogo = cur.catalogo_modulos(usuario)
    area_id = f"obj{o['id']}"
    propios = [(m["ref"], f"🎯 {m['t']} (nivel {m['nivel']})") for m in (cur.areas(usuario).get(area_id) or {}).get("modulos", [])]
    refs = [r for r, _ in catalogo] + [r for r, _ in propios]
    ruta = set(cur.cierre_prerrequisitos(plan.get("modulos", []) + plan.get("extra", []), usuario))
    lista = "\n".join(f"{r} = {d}{' [EN LA RUTA]' if r in ruta else ''}" for r, d in catalogo + propios)
    ctx.fase("Mapeando todas las sub-ramas de la meta")
    r = ctx.chat([{"role": "system", "content": lec.SISTEMA_BASE}, {"role": "user", "content": (
        f"{lec.texto_perfil(perfil)}\n\nMeta: «{o['titulo']}». {o['descripcion'] or ''}\n"
        "El estudiante quiere dominar esto desde lo más básico hasta la frontera, al punto de poder presentar algo "
        "innovador. Haz el MAPA COMPLETO de sub-ramas que necesita: las del propio campo, las de campos vecinos que "
        "hacen falta y los FUNDAMENTOS (matemática, física, programación… que de verdad se usan). Para cada rama: "
        "importancia (esencial = sin ella no se puede; importante = la frontera la usa mucho; complementaria = suma), "
        "por qué, nivel = en qué punto del camino está (1 = fundamentos que van primero, 3 = avanzado, 5 = frontera), "
        "3-8 temas clave y cubierta_por = módulos del catálogo que la enseñan de verdad "
        "(vacío si ninguno la cubre). No olvides ninguna rama esencial. JSON compacto.\n\nCATÁLOGO:\n" + lista)}],
        max_tokens=6000, temperatura=0.3, esquema=_esquema_ramas(refs))
    ramas = r["ramas"]
    # módulos del catálogo que cubren ramas esenciales/importantes entran a la meta (con sus requisitos)
    nuevos_refs = []
    for x in ramas:
        if x["importancia"] != "complementaria":
            for ref in x["cubierta_por"]:
                if ref not in ruta and ref not in nuevos_refs and not ref.startswith(area_id + "."):
                    nuevos_refs.append(ref)
    plan.setdefault("modulos", [])
    plan["modulos"] += nuevos_refs
    for ref in nuevos_refs:
        plan.setdefault("razones", {})[ref] = "Cubre una sub-rama necesaria (🌳 mapa de sub-ramas)."
    # ramas esenciales/importantes sin cobertura → módulos propios de la meta
    huecos = [x for x in ramas if x["importancia"] != "complementaria" and not x["cubierta_por"]]
    creados = []
    if huecos:
        fila_area = fila("SELECT datos FROM area_extra WHERE id=? AND usuario=?", (area_id, usuario))
        area = json.loads(fila_area["datos"]) if fila_area else {
            "id": area_id, "nombre": f"🎯 {o['titulo']}", "icono": "🎯", "grupo": "Mis objetivos", "color": "#f39c12",
            "descripcion": plan.get("resumen", ""), "objetivo": o["id"], "usuario": usuario, "recursos": [], "modulos": []}
        existentes = {re.sub(r"\W+", " ", m["t"].lower()).strip() for m in area["modulos"]}
        k = sum(1 for m in area["modulos"] if m["id"].startswith("rama"))
        for x in sorted(huecos, key=lambda y: y["nivel"]):
            clave = re.sub(r"\W+", " ", x["nombre"].lower()).strip()
            if clave in existentes:
                continue
            existentes.add(clave)
            k += 1
            mid = f"rama{k}"
            pre = [f"{area_id}.{m['id']}" for m in area["modulos"] if m["nivel"] < x["nivel"]][-1:]
            area["modulos"].append({"id": mid, "t": f"🌳 {x['nombre']}", "nivel": x["nivel"], "pre": pre,
                                    "temas": [f"{t.replace('|', '/')}|" for t in x["temas_clave"]]})
            plan.setdefault("extra", []).append(f"{area_id}.{mid}")
            plan.setdefault("razones", {})[f"{area_id}.{mid}"] = x["por_que"]
            x["cubierta_por"] = [f"{area_id}.{mid}"]
            creados.append(x["nombre"])
        ejecutar("INSERT OR REPLACE INTO area_extra(id,usuario,datos,creado) VALUES(?,?,?,?)",
                 (area_id, usuario, json.dumps(area, ensure_ascii=False), time.time()))
    plan["ramas"] = ramas
    plan["ramas_fecha"] = time.time()
    ejecutar("UPDATE objetivo SET plan=? WHERE id=?", (json.dumps(plan, ensure_ascii=False), o["id"]))
    return {"objetivo": o["id"], "ramas": len(ramas), "modulos_agregados": nuevos_refs, "ramas_creadas": creados}


def ramas_de(usuario, oid):
    """El mapa de sub-ramas con cuánto domina cada una (promedio de sus módulos)."""
    o = _objetivo(usuario, oid)
    if not o:
        return None
    plan = json.loads(o["plan"] or "{}")
    if not plan.get("ramas"):
        return None
    avs = cur.avances(usuario)
    out = []
    for x in plan["ramas"]:
        mods = [m for m in (cur.modulo(r, usuario) for r in x["cubierta_por"]) if m]
        dom = sum(cur.dominio_modulo(m, avs) for m in mods) / len(mods) if mods else None
        out.append({**x, "dominio": round(dom, 3) if dom is not None else None,
                    "modulos": [{"ref": m["ref"], "t": m["t"], "primero": m["temas_obj"][0]["id"] if m["temas_obj"] else None}
                                for m in mods]})
    orden = {"esencial": 0, "importante": 1, "complementaria": 2}
    out.sort(key=lambda x: (orden[x["importancia"]], x["nivel"]))
    return {"ramas": out, "fecha": plan.get("ramas_fecha")}


# ------------------------------------------------------------------ 🚀 laboratorio de innovación
ejecutar("""CREATE TABLE IF NOT EXISTS idea (
  id INTEGER PRIMARY KEY AUTOINCREMENT, usuario TEXT, objetivo INTEGER, datos TEXT, novedad TEXT,
  presentacion TEXT, revision TEXT, elegida INTEGER DEFAULT 0, creada REAL)""")


def _refs_meta(usuario, o):
    plan = json.loads(o["plan"] or "{}")
    return cur.cierre_prerrequisitos(plan.get("modulos", []) + plan.get("extra", []), usuario)


def _fortalezas(usuario):
    """Áreas donde la persona ya sabe algo (para cruzar campos: de ahí sale mucho de lo nuevo)."""
    avs = cur.avances(usuario)
    out = []
    for a in cur.areas(usuario).values():
        if a["id"] not in cur.areas_de(usuario) or a.get("objetivo"):
            continue
        n = sum(1 for m in a["modulos"] for t in m["temas_obj"] if cur.dominio_tema(avs.get(t["id"])) >= 0.5)
        if n:
            out.append((n, a["nombre"]))
    return [x[1] for x in sorted(out, reverse=True)[:6]]


ESQUEMA_IDEAS = {"type": "object", "properties": {"ideas": {"type": "array", "minItems": 3, "maxItems": 6, "items": {
    "type": "object", "properties": {
        "titulo": {"type": "string"}, "problema": {"type": "string"}, "idea": {"type": "string"},
        "por_que_nueva": {"type": "string"}, "cruce": {"type": "string"}, "como_probarla": {"type": "string"},
        "riesgo": {"type": "string"}, "consulta_en": {"type": "string"},
        "modulos": {"type": "array", "maxItems": 8, "items": {"type": "string"}}},
    "required": ["titulo", "problema", "idea", "por_que_nueva", "cruce", "como_probarla", "riesgo", "consulta_en",
                 "modulos"]}}}, "required": ["ideas"]}

ESQUEMA_NOVEDAD = {"type": "object", "properties": {
    "novedad": {"type": "integer", "minimum": 1, "maximum": 5},
    "mas_parecidos": {"type": "array", "maxItems": 4, "items": {"type": "integer", "minimum": 1, "maximum": 12}},
    "diferencia": {"type": "string"}, "como_hacerla_mas_nueva": {"type": "string"}},
    "required": ["novedad", "mas_parecidos", "diferencia", "como_hacerla_mas_nueva"]}


def _chequeo_novedad(ctx, texto_idea, consulta_en):
    """Busca trabajos parecidos de verdad (OpenAlex, incluidos preprints de arXiv recientes) y compara la idea con
    ellos: lo innovador se demuestra contra la literatura, no se supone."""
    import lecciones as lec
    vistos, trabajos = set(), []
    for p in ciencia.buscar(consulta_en, 6) + ciencia.frontera(consulta_en, 6):
        k = p.get("doi") or p["url"]
        if k not in vistos and p.get("resumen"):
            vistos.add(k)
            trabajos.append(p)
    trabajos = trabajos[:12]
    if not trabajos:
        return {"novedad": None, "mas_parecidos": [], "diferencia": "No se encontraron trabajos parecidos para comparar "
                "(puede ser muy nueva o la búsqueda no dio con ellos: revísalo a mano).", "como_hacerla_mas_nueva": "",
                "trabajos": []}
    ctx.fase("Comparando la idea con trabajos parecidos (novedad)")
    r = ctx.chat([{"role": "system", "content": lec.SISTEMA_BASE}, {"role": "user", "content": (
        f"IDEA:\n{texto_idea}\n\nTRABAJOS PUBLICADOS PARECIDOS:\n{ciencia.bloque_prompt(trabajos)}\n\n"
        "¿Qué tan nueva es la idea frente a estos trabajos? novedad 1-5 (1 = ya está hecha tal cual; 3 = variación de "
        "algo existente; 5 = no hay nada parecido en lo encontrado). mas_parecidos = números [Pn] de los más cercanos. "
        "diferencia = qué aporta la idea que ellos no (concreto). como_hacerla_mas_nueva = cómo llevarla más allá. "
        "Honesto: no infles la novedad. JSON compacto.")}], max_tokens=900, temperatura=0.2, esquema=ESQUEMA_NOVEDAD,
        mostrar=False)
    r["mas_parecidos"] = [i for i in r["mas_parecidos"] if 1 <= i <= len(trabajos)]
    r["trabajos"] = [{k: p.get(k) for k in ("titulo", "autores", "anio", "citas", "url", "abierto")} for p in trabajos]
    return r


def idear(ctx, usuario, perfil, oid, enfoque=""):
    import lecciones as lec
    o = _objetivo(usuario, oid)
    f = ultima_frontera(oid) if o else None
    if not f:
        raise ValueError("primero hace falta el mapa de la frontera de esta meta")
    refs = _refs_meta(usuario, o)
    mods = "\n".join(f"{r} = {(cur.modulo(r, usuario) or {}).get('t', r)}" for r in refs)
    ctx.fase("Generando ideas en la frontera")
    r = ctx.chat([{"role": "system", "content": lec.SISTEMA_BASE}, {"role": "user", "content": (
        f"{lec.texto_perfil(perfil)}\n\nMeta: «{o['titulo']}». {o['descripcion'] or ''}\n"
        + (f"Enfoque que pide el estudiante: {enfoque}\n" if enfoque else "")
        + f"Lo que ya sabe (para cruzar campos): {', '.join(_fortalezas(usuario)) or 'aún poco'}.\n\n"
        "Propón 4-6 ideas de proyecto o investigación lo más INNOVADORAS posible pero realizables por esta persona en "
        "semanas o meses (con un PC, simulación, datos abiertos o un prototipo sencillo). Cada una ataca un problema "
        "abierto o una línea activa de la frontera (abajo) y, si puede, cruza la meta con otra área que ya sabe "
        "(de los cruces sale mucho de lo nuevo). Para cada idea: título, problema (de la frontera), la idea, por qué "
        "sería nueva, el cruce de áreas, cómo probarla (experimento, simulación o demostración concreta), el riesgo "
        "principal, consulta_en (búsqueda académica en inglés de 3-6 palabras para encontrar trabajos parecidos) y "
        "modulos = refs de la ruta que hacen falta para hacerla (de la lista). JSON compacto.\n\n"
        "FRONTERA:\nLíneas: " + "; ".join(f"{x['nombre']}: {x['que_es']}" for x in f["lineas"])
        + "\nProblemas abiertos: " + "; ".join(f"{x['problema']} ({x['por_que_es_dificil']})" for x in f["problemas_abiertos"])
        + "\n\nMÓDULOS DE LA RUTA:\n" + mods[:8000])}], max_tokens=4000, temperatura=0.8, esquema=ESQUEMA_IDEAS)
    creadas = []
    for i, idea in enumerate(r["ideas"]):
        idea["modulos"] = [m for m in idea["modulos"] if m in refs]
        ctx.fase(f"Chequeando novedad de la idea {i + 1}/{len(r['ideas'])} contra la literatura")
        nov = _chequeo_novedad(ctx, f"{idea['titulo']}. {idea['idea']} ({idea['problema']})", idea["consulta_en"])
        iid = ejecutar("INSERT INTO idea(usuario,objetivo,datos,novedad,creada) VALUES(?,?,?,?,?)",
                       (usuario, o["id"], json.dumps(idea, ensure_ascii=False), json.dumps(nov, ensure_ascii=False),
                        time.time())).lastrowid
        creadas.append(iid)
    return {"ideas": creadas}


def _idea(usuario, iid):
    r = fila("SELECT * FROM idea WHERE id=? AND usuario=?", (int(iid), usuario))
    if not r:
        return None
    return {"id": r["id"], "objetivo": r["objetivo"], "datos": json.loads(r["datos"]), "novedad": json.loads(r["novedad"] or "null"),
            "presentacion": json.loads(r["presentacion"] or "null"), "revision": json.loads(r["revision"] or "null"),
            "elegida": bool(r["elegida"]), "creada": r["creada"]}


def ideas_de(usuario, oid):
    return [_idea(usuario, r["id"]) for r in filas("SELECT id FROM idea WHERE usuario=? AND objetivo=? ORDER BY elegida DESC, id DESC",
                                                     (usuario, int(oid)))]


def elegir_idea(usuario, iid):
    """La idea elegida es TU proyecto: sus módulos (la ruta crítica) pasan primero en el plan del día."""
    x = _idea(usuario, iid)
    if not x:
        raise ValueError("idea desconocida")
    ejecutar("UPDATE idea SET elegida=0 WHERE usuario=? AND objetivo=?", (usuario, x["objetivo"]))
    ejecutar("UPDATE idea SET elegida=1 WHERE id=?", (x["id"],))
    return x


def refs_proyecto(usuario):
    """Ruta crítica de los proyectos elegidos (módulos que la idea necesita, con sus requisitos)."""
    refs = []
    for r in filas("SELECT i.datos FROM idea i JOIN objetivo o ON o.id=i.objetivo WHERE i.usuario=? AND i.elegida=1 "
                   "AND o.estado='activo'", (usuario,)):
        refs += json.loads(r["datos"]).get("modulos", [])
    return set(cur.cierre_prerrequisitos(refs, usuario)) if refs else set()


ESQUEMA_PRESENTACION = {"type": "object", "properties": {
    "titulo": {"type": "string"}, "resumen": {"type": "string"},
    "estructura": {"type": "array", "minItems": 5, "maxItems": 12, "items": {"type": "object", "properties": {
        "seccion": {"type": "string"}, "contenido": {"type": "string"}}, "required": ["seccion", "contenido"]}},
    "guion_10min": {"type": "string"},
    "preguntas_dificiles": {"type": "array", "minItems": 6, "maxItems": 10, "items": {"type": "object", "properties": {
        "pregunta": {"type": "string"}, "como_responder": {"type": "string"}}, "required": ["pregunta", "como_responder"]}},
    "plan_validacion": {"type": "array", "minItems": 3, "maxItems": 10, "items": {"type": "object", "properties": {
        "semana": {"type": "integer", "minimum": 1, "maximum": 52}, "tarea": {"type": "string"}, "entregable": {"type": "string"}},
        "required": ["semana", "tarea", "entregable"]}},
    "que_dominar": {"type": "array", "maxItems": 10, "items": {"type": "string"}}},
    "required": ["titulo", "resumen", "estructura", "guion_10min", "preguntas_dificiles", "plan_validacion", "que_dominar"]}


def preparar_presentacion(ctx, usuario, perfil, iid):
    import lecciones as lec
    x = _idea(usuario, iid)
    if not x:
        raise ValueError("idea desconocida")
    i, nov = x["datos"], x["novedad"] or {}
    f = ultima_frontera(x["objetivo"]) or {}
    previos = "\n".join(f"- {t['titulo']} ({t['anio']})" for t in nov.get("trabajos", [])[:8])
    ctx.fase("Preparando la presentación")
    r = ctx.chat([{"role": "system", "content": lec.SISTEMA_BASE}, {"role": "user", "content": (
        f"{lec.texto_perfil(perfil)}\n\nPrepara al estudiante para PRESENTAR esta idea ante expertos (congreso, "
        "seminario, convocatoria o inversionistas técnicos):\n"
        f"Idea: {i['titulo']}. {i['idea']}\nProblema: {i['problema']}\nPor qué es nueva: {i['por_que_nueva']}\n"
        f"Diferencia con lo publicado: {nov.get('diferencia', '')}\nCómo probarla: {i['como_probarla']}\n"
        f"Trabajos relacionados:\n{previos}\nContexto de la frontera: "
        + "; ".join(p["problema"] for p in f.get("problemas_abiertos", [])) + "\n\n"
        "Devuelve: título atractivo y preciso; resumen tipo abstract (200-250 palabras); estructura de la charla o póster "
        "(secciones con lo que va en cada una); guion de 10 minutos en markdown; las preguntas MÁS difíciles que haría "
        "el público experto, con cómo responderlas honestamente (incluido «aún no lo sé, y así lo averiguaría»); plan de "
        "validación semana a semana con entregables; y qué_dominar = conceptos que debe manejar a fondo antes de "
        "presentarla. Nunca inventes resultados. JSON compacto.")}], max_tokens=5000, temperatura=0.4,
        esquema=ESQUEMA_PRESENTACION)
    ejecutar("UPDATE idea SET presentacion=? WHERE id=?", (json.dumps(r, ensure_ascii=False), x["id"]))
    return r


ESQUEMA_PARES = {"type": "object", "properties": {"revisores": {"type": "array", "minItems": 3, "maxItems": 3, "items": {
    "type": "object", "properties": {
        "perfil": {"type": "string"}, "puntaje": {"type": "integer", "minimum": 1, "maximum": 10},
        "fortalezas": {"type": "string"}, "debilidades": {"type": "string"}, "pide": {"type": "string"},
        "veredicto": {"type": "string", "enum": ["aceptar", "aceptar con cambios", "rechazar"]}},
    "required": ["perfil", "puntaje", "fortalezas", "debilidades", "pide", "veredicto"]}},
    "cambios_prioritarios": {"type": "array", "minItems": 2, "maxItems": 6, "items": {"type": "string"}}},
    "required": ["revisores", "cambios_prioritarios"]}


def revision_pares(ctx, usuario, iid):
    import lecciones as lec
    x = _idea(usuario, iid)
    if not x:
        raise ValueError("idea desconocida")
    i, nov, pres = x["datos"], x["novedad"] or {}, x["presentacion"] or {}
    ctx.fase("Revisión de pares simulada (3 revisores)")
    r = ctx.chat([{"role": "system", "content": lec.SISTEMA_BASE}, {"role": "user", "content": (
        "Simula una revisión de pares exigente de esta propuesta, con 3 revisores distintos: un experto teórico del "
        "campo, uno experimental/aplicado y un escéptico metodológico. Cada uno: puntaje 1-10, fortalezas, debilidades, "
        "qué pide para aceptarla y veredicto. Luego los cambios prioritarios. Sé duro pero justo y concreto.\n\n"
        f"Propuesta: {pres.get('titulo') or i['titulo']}\n{pres.get('resumen') or i['idea']}\n"
        f"Cómo se probaría: {i['como_probarla']}\nRiesgo: {i['riesgo']}\n"
        f"Novedad estimada frente a la literatura: {nov.get('novedad')}/5. {nov.get('diferencia', '')}")}],
        max_tokens=2500, temperatura=0.4, esquema=ESQUEMA_PARES)
    ejecutar("UPDATE idea SET revision=? WHERE id=?", (json.dumps(r, ensure_ascii=False), x["id"]))
    return r
