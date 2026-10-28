"""Rutas vivas: cada ruta (área o meta) se revisa sola y se completa con lo que falta.

- Una ruta del catálogo (curriculo/*.json) es común a todos; lo que la revisión le agrega a UNA persona va a su capa
  propia (tabla ruta_extra: temas nuevos al final de módulos existentes y módulos nuevos «🆕 …»), que
  `curriculo.areas(usuario)` mezcla al cargar. Los temas se agregan al FINAL: los ids de lo ya estudiado no cambian.
- Las áreas propias (p_…) y las de metas (obj…) son de la persona: se editan en su fila de area_extra.
- Evidencia: el referente del mercado de hoy (mercado.py: competencias que la ruta no enseña o enseña poco) y, en las
  metas, el mapa de la frontera (dominio.py); en las áreas del catálogo, además, la investigación reciente de sus
  módulos de nivel 4-5 (OpenAlex). Lo que va de salida se marca «📉 en declive» (no se borra nada).
"""
import json
import re
import time
from datetime import datetime

import ciencia
import curriculo as cur
import mercado
from base import ejecutar, fila, kv_get, kv_set

ejecutar("""CREATE TABLE IF NOT EXISTS ruta_extra (
  usuario TEXT, area TEXT, datos TEXT, actualizado REAL, PRIMARY KEY (usuario, area))""")


MAX_TEMAS, MAX_MODULOS = 5, 1   # por revisión: que la ruta crezca con lo necesario, no se infle día a día


def _clave(t):
    t = re.sub(r"[^\w ]+", " ", str(t).split("|")[0].lower())
    return re.sub(r"\s+", " ", t).strip()


def _esquema(refs):
    tema = {"type": "object", "properties": {"t": {"type": "string"}, "d": {"type": "string"}}, "required": ["t", "d"]}
    return {"type": "object", "properties": {
        "resumen": {"type": "string"},
        "temas_nuevos": {"type": "array", "maxItems": 12, "items": {"type": "object", "properties": {
            "modulo": {"type": "string", "enum": refs}, "t": {"type": "string"}, "d": {"type": "string"},
            "por_que": {"type": "string"}}, "required": ["modulo", "t", "d", "por_que"]}},
        "modulos_nuevos": {"type": "array", "maxItems": 3, "items": {"type": "object", "properties": {
            "t": {"type": "string"}, "nivel": {"type": "integer", "minimum": 1, "maximum": 5},
            "pre": {"type": "array", "maxItems": 2, "items": {"type": "string", "enum": refs}},
            "temas": {"type": "array", "minItems": 3, "maxItems": 7, "items": tema}, "por_que": {"type": "string"}},
            "required": ["t", "nivel", "pre", "temas", "por_que"]}},
        "en_declive": {"type": "array", "maxItems": 6, "items": {"type": "object", "properties": {
            "tema": {"type": "string"}, "por_que": {"type": "string"}}, "required": ["tema", "por_que"]}}},
        "required": ["resumen", "temas_nuevos", "modulos_nuevos", "en_declive"]}


def _evidencia(usuario, area):
    partes = []
    if not area.get("objetivo"):
        ev = mercado.evaluar(usuario, area["id"])
        if ev:
            partes.append("MERCADO DE HOY (competencias por nivel; cobertura = cuánto la enseña la ruta):\n" + "\n".join(
                f"- N{n['nivel']} {c['competencia']} ({c['tipo']}, {c['tendencia']}; "
                f"{'NO la enseña la ruta' if c.get('cobertura') is None else 'módulos: ' + ', '.join(c['modulos'])})"
                for n in ev["referente"] for c in n["competencias"]))
            partes.append("Cambios en 5 años: " + "; ".join(ev["cambios_5_anios"]))
        for m in [m for m in area["modulos"] if m["nivel"] >= 4][:4]:
            q = kv_get(f"consulta_en:{m['ref']}")
            ps = ciencia.frontera(q, 4) if q else []
            if ps:
                partes.append(f"INVESTIGACIÓN RECIENTE de «{m['t']}»:\n" + "\n".join(
                    f"- ({p['anio']}, {p['clase']}, {p['citas']} citas) {p['titulo']}" for p in ps))
    else:
        import dominio
        f = dominio.ultima_frontera(area["objetivo"])
        if f:
            partes.append("FRONTERA DE LA META (mapa del " + datetime.fromtimestamp(f["creada"]).strftime("%Y-%m-%d")
                          + "):\nLíneas: " + "; ".join(f"{x['nombre']} ({x['madurez']})" for x in f["lineas"])
                          + "\nProblemas abiertos: " + "; ".join(x["problema"] for x in f["problemas_abiertos"])
                          + "\nVocabulario: " + ", ".join(x["termino"] for x in f["vocabulario"]))
    return "\n\n".join(partes)


def revisar(ctx, usuario, perfil, area_id):
    from lecciones import SISTEMA_BASE, texto_perfil
    area = cur.areas(usuario).get(area_id)
    if not area:
        raise ValueError("ruta desconocida")
    ctx.fase(f"Revisando la ruta «{area['nombre']}» contra el mercado y la investigación de hoy")
    evidencia = _evidencia(usuario, area)
    refs = [m["ref"] for m in area["modulos"]]
    estructura = "\n".join(f"{m['ref']} (nivel {m['nivel']}) {m['t']}: " + "; ".join(t["t"] for t in m["temas_obj"])
                           for m in area["modulos"])
    previa = kv_get(f"revision:{usuario}:{area_id}")
    prompt = (
        f"{texto_perfil(perfil)}\n\nFecha: {datetime.now():%Y-%m-%d}. Revisa la RUTA DE APRENDIZAJE «{area['nombre']}» "
        "para que lleve de verdad desde lo básico hasta la frontera actual y a lo que hoy se exige al nivel profesional. "
        "Usa la evidencia de abajo (no inventes): agrega SOLO lo que falte de verdad y valga la pena estudiar.\n"
        "Sé conservador: una ruta que crece sin control se vuelve más lenta de recorrer. Máximo 5 temas nuevos y 1 "
        "módulo nuevo por revisión, y solo con respaldo claro en la evidencia (no por intuición).\n"
        "- temas_nuevos: temas que faltan dentro de un módulo existente (modulo = su ref).\n"
        "- modulos_nuevos: solo si falta un bloque entero (p. ej. una herramienta o línea nueva); con nivel 1-5, "
        "requisitos (pre = refs) y 3-7 temas.\n"
        "- en_declive: temas de la ruta que hoy pesan menos (no se borran; se marcan).\n"
        "- resumen: 2-4 frases de qué cambia y por qué. Si la ruta ya está al día, listas vacías y dilo.\n"
        "No repitas temas que ya están (aunque tengan otro nombre). Todo en español. JSON compacto.\n\n"
        + (f"REVISIÓN ANTERIOR ({datetime.fromtimestamp(previa['fecha']):%Y-%m-%d}): {previa['resumen']}\n\n" if previa else "")
        + f"RUTA ACTUAL:\n{estructura[:14000]}\n\nEVIDENCIA:\n{evidencia[:14000] or '(sin evidencia nueva)'}")
    r = ctx.chat([{"role": "system", "content": SISTEMA_BASE}, {"role": "user", "content": prompt}],
                 max_tokens=3500, temperatura=0.3, esquema=_esquema(refs))
    agregados = aplicar(usuario, area, r)
    reg = {"fecha": time.time(), "resumen": r["resumen"], "agregados": agregados,
           "en_declive": r.get("en_declive", []),
           "historial": ((previa or {}).get("historial", []) + ([{"fecha": previa["fecha"], "resumen": previa["resumen"],
                                                                    "agregados": previa["agregados"]}] if previa else []))[-10:]}
    kv_set(f"revision:{usuario}:{area_id}", reg)
    return {"area": area_id, "agregados": agregados, "resumen": r["resumen"]}


def aplicar(usuario, area, r):
    """Agrega lo nuevo (sin duplicar) y devuelve [{tipo, modulo, t, id}] con los ids de los temas nuevos."""
    existentes = {_clave(t["t"]) for m in area["modulos"] for t in m["temas_obj"]}
    propia = bool(area.get("usuario"))          # área propia o de meta: se edita su fila de area_extra
    if propia:
        datos = json.loads(fila("SELECT datos FROM area_extra WHERE id=? AND usuario=?", (area["id"], usuario))["datos"])
        mods = {m["id"]: m for m in datos["modulos"]}
    else:
        row = fila("SELECT datos FROM ruta_extra WHERE usuario=? AND area=?", (usuario, area["id"]))
        datos = json.loads(row["datos"]) if row else {"temas": {}, "modulos": []}
    hechos = []
    por_ref = {m["ref"]: m for m in area["modulos"]}
    for t in r.get("temas_nuevos", [])[:MAX_TEMAS]:
        m = por_ref.get(t["modulo"])
        k = _clave(t["t"])
        if not m or not k or k in existentes:
            continue
        existentes.add(k)
        texto = f"{t['t'].replace('|', '/')}|{t['d'].replace('|', '/')}"
        if propia:
            mods[m["id"]]["temas"].append(texto)
        elif m["id"].startswith("upd"):     # módulo nuevo de una revisión anterior (vive en la capa propia)
            next(x for x in datos["modulos"] if x["id"] == m["id"])["temas"].append(texto)
        else:
            datos["temas"].setdefault(m["id"], []).append(texto)
        hechos.append({"tipo": "tema", "modulo": m["t"], "t": t["t"], "por_que": t["por_que"]})
    n_prev = len([m for m in area["modulos"] if m["id"].startswith("upd")])
    for k, mn in enumerate(r.get("modulos_nuevos", [])[:MAX_MODULOS]):
        temas = [x for x in mn["temas"] if _clave(x["t"]) and _clave(x["t"]) not in existentes]
        if len(temas) < 2:
            continue
        existentes |= {_clave(x["t"]) for x in temas}
        mid = f"upd{n_prev + k + 1}"
        nuevo = {"id": mid, "t": f"🆕 {mn['t']}", "nivel": mn["nivel"], "pre": [p for p in mn["pre"] if p in por_ref],
                 "temas": [f"{x['t'].replace('|', '/')}|{x['d'].replace('|', '/')}" for x in temas]}
        datos["modulos"].append(nuevo)
        hechos.append({"tipo": "modulo", "modulo": nuevo["t"], "t": f"{len(temas)} temas", "por_que": mn["por_que"]})
    if propia:
        ejecutar("UPDATE area_extra SET datos=? WHERE id=? AND usuario=?",
                 (json.dumps(datos, ensure_ascii=False), area["id"], usuario))
    else:
        ejecutar("""INSERT INTO ruta_extra(usuario,area,datos,actualizado) VALUES(?,?,?,?)
                    ON CONFLICT(usuario,area) DO UPDATE SET datos=excluded.datos, actualizado=excluded.actualizado""",
                 (usuario, area["id"], json.dumps(datos, ensure_ascii=False), time.time()))
    # ids reales de los temas nuevos (para preparar sus lecciones): se buscan en la ruta ya actualizada
    nueva = cur.areas(usuario)[area["id"]]
    titulos = {_clave(h["t"]) for h in hechos if h["tipo"] == "tema"}
    mods_nuevos = {h["modulo"] for h in hechos if h["tipo"] == "modulo"}
    for m in nueva["modulos"]:
        for t in m["temas_obj"]:
            if _clave(t["t"]) in titulos or m["t"] in mods_nuevos:
                for h in hechos:
                    if (h["tipo"] == "tema" and _clave(h["t"]) == _clave(t["t"])) or (h["tipo"] == "modulo" and h["modulo"] == m["t"]):
                        h.setdefault("ids", []).append(t["id"])
    return hechos


def estado(usuario, area_id):
    return kv_get(f"revision:{usuario}:{area_id}")


def vencida(usuario, area_id, dias):
    r = kv_get(f"revision:{usuario}:{area_id}")
    return not r or time.time() - r["fecha"] > dias * 86400 - 3600
