"""Nivel profesional frente a lo que el mercado pide HOY.

El nivel de la ruta (adaptacion._nivel_de) mide cuánto dominas del currículo,
que es fijo. Pero lo que se le exige a un junior o a un senior cambia cada año
(herramientas nuevas, prácticas que se volvieron estándar, otras que caducan).

1. referente(ctx, area): busca en la web lo que hoy piden las ofertas, los
   informes de habilidades (WEF, OCDE, ACM/IEEE, O*NET…) y los marcos del
   sector; la IA arma, para cada nivel 1-5, las competencias actuales con su
   tendencia (nueva, en alza, estable, en declive) y las enlaza con módulos
   del currículo. Se guarda en kv mercado:<area> y se renueva cada 30 días.
2. evaluar(usuario, area): cruza esas competencias con tu dominio real de
   los temas → nivel según el mercado de hoy, brechas y lo emergente.
   Una competencia sin módulo en el currículo cuenta como 0 % (brecha que
   la Academia todavía no enseña: se avisa).
"""
import json
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

import curriculo as cur
import ia
from base import kv_get, kv_set

VIGENCIA_DIAS = 30
UMBRAL = 0.7
ROLES = {1: "Técnico", 2: "Tecnólogo · universitario", 3: "Profesional junior", 4: "Profesional senior · especialista",
         5: "Experto · referente"}


def _esquema(refs):
    comp = {"type": "object", "properties": {
        "competencia": {"type": "string"},
        "tipo": {"type": "string", "enum": ["fundamento", "herramienta", "práctica", "habilidad transversal", "emergente"]},
        "tendencia": {"type": "string", "enum": ["nueva", "en alza", "estable", "en declive"]},
        "modulos": {"type": "array", "maxItems": 3, "items": {"type": "string", "enum": refs}},
        "fuente": {"type": "integer", "minimum": -1, "maximum": 30}},
        "required": ["competencia", "tipo", "tendencia", "modulos", "fuente"]}
    return {"type": "object", "properties": {
        "resumen_mercado": {"type": "string"},
        "cambios_5_anios": {"type": "array", "minItems": 2, "maxItems": 6, "items": {"type": "string"}},
        "niveles": {"type": "array", "minItems": 5, "maxItems": 5, "items": {"type": "object", "properties": {
            "nivel": {"type": "integer", "minimum": 1, "maximum": 5},
            "rol": {"type": "string"},
            "competencias": {"type": "array", "minItems": 3, "maxItems": 8, "items": comp}},
            "required": ["nivel", "rol", "competencias"]}}},
        "required": ["resumen_mercado", "cambios_5_anios", "niveles"]}


def _evidencia(area):
    anio = datetime.now().year
    nombre = area["nombre"]
    consultas = [f"{nombre} perfil profesional competencias requeridas {anio}",
                 f"{nombre} skills in demand {anio} job requirements junior senior",
                 f"{nombre} ofertas de empleo requisitos {anio} vacantes",
                 f"{nombre} future of jobs skills report {anio - 1} {anio}"]
    vistos, res = set(), []
    for q in consultas:
        for r in ia.buscar_web(q, n=6):
            if r["url"] not in vistos:
                vistos.add(r["url"])
                res.append(r)
    res = res[:12]
    from noticias import _texto_articulo
    with ThreadPoolExecutor(4) as ex:
        textos = list(ex.map(lambda r: _texto_articulo(r["url"], 2200), res[:4]))
    for r, t in zip(res, textos):
        if t:
            r["texto"] = t
    return res


def referente(ctx, area_id, usuario=None):
    from lecciones import SISTEMA_BASE
    area = cur.areas(usuario)[area_id]
    ctx.fase(f"Buscando qué pide hoy el mercado: {area['nombre']}")
    fuentes = _evidencia(area)
    refs = [m["ref"] for m in area["modulos"]] + [r for r, _ in cur.catalogo_modulos(usuario) if not r.startswith(area_id + ".")]
    modulos = "\n".join(f"{m['ref']} = {m['t']} (nivel {m['nivel']}): {', '.join(t['t'] for t in m['temas_obj'][:6])}"
                        for m in area["modulos"])
    otros = "\n".join(f"{r} = {d}" for r, d in cur.catalogo_modulos(usuario) if not r.startswith(area_id + "."))
    bloque = "\n\n".join(f"[{i}] {f['titulo']} — {f['url']}\n{f['texto']}" for i, f in enumerate(fuentes))
    previo = kv_get(f"mercado:{area_id}")
    estable = ("\nREFERENTE ANTERIOR (" + datetime.fromtimestamp(previo["fecha"]).strftime("%Y-%m-%d") + "): "
               + " | ".join(f"N{n['nivel']}: " + "; ".join(c["competencia"] for c in n["competencias"])
                            for n in previo["niveles"])
               + "\nConsérvalo salvo que la evidencia de hoy muestre un cambio real (renovarlo seguido no debe hacer "
                 "saltar el nivel de un día a otro por azar).\n") if previo else ""
    prompt = (
        f"Fecha de hoy: {datetime.now():%Y-%m-%d}.\nÁrea: {area['nombre']}. {area.get('descripcion', '')}\n\n"
        "Construye el REFERENTE ACTUAL del mercado laboral y profesional de esta área: qué se le exige HOY a cada nivel, "
        "no lo que se pedía hace 5 años. Niveles: 1 Técnico, 2 Tecnólogo/universitario, 3 Profesional junior (recién "
        "egresado contratable), 4 Senior/especialista, 5 Experto/referente.\n"
        "- niveles: exactamente 5 (nivel 1 a 5), cada uno con el rol típico hoy y 3-8 competencias CONCRETAS y "
        "verificables (p. ej. 'diseñar y sintonizar lazos PID en un PLC', 'desplegar servicios en contenedores con CI/CD', "
        "no 'saber programación'). tipo y tendencia de cada una ('nueva' = casi no se pedía hace 5 años; 'en declive' = "
        "se pide cada vez menos). modulos = 0-3 módulos del currículo que la enseñan (refs exactas; [] si el currículo "
        "no la cubre). fuente = índice de la evidencia web que la respalda, o -1 si es conocimiento general del sector.\n"
        "- cambios_5_anios: qué cambió en lo que se exige respecto a hace 5 años (concreto).\n"
        "- resumen_mercado: 2-3 frases sobre cómo está hoy la demanda del área.\n"
        "Básate en la evidencia; no inventes cifras ni nombres de informes. JSON compacto.\n\n"
        f"{estable}EVIDENCIA WEB DE HOY:\n{bloque or '(sin resultados: usa conocimiento general reciente y dilo)'}\n\n"
        f"MÓDULOS DE ESTA ÁREA:\n{modulos}\n\nOTROS MÓDULOS DEL CURRÍCULO (también valen):\n{otros[:9000]}")
    ctx.fase(f"Armando el referente actual: {area['nombre']}")
    r = ctx.chat([{"role": "system", "content": SISTEMA_BASE}, {"role": "user", "content": prompt}],
                 max_tokens=5000, temperatura=0.3, esquema=_esquema(refs))
    r["niveles"] = sorted(r["niveles"], key=lambda n: n["nivel"])
    for i, n in enumerate(r["niveles"]):
        n["nivel"] = i + 1
    r["fuentes"] = [{"titulo": f["titulo"], "url": f["url"]} for f in fuentes]
    r["fecha"] = time.time()
    kv_set(f"mercado:{area_id}", r)
    return {"area": area_id, "competencias": sum(len(n["competencias"]) for n in r["niveles"])}


def evaluar(usuario, area_id, avs=None):
    ref = kv_get(f"mercado:{area_id}")
    if not ref:
        return None
    avs = avs if avs is not None else cur.avances(usuario)

    def dominio_modulo(r):
        m = cur.modulo(r, usuario)
        if not m or not m["temas_obj"]:
            return None
        return sum(cur.dominio_tema(avs.get(t["id"])) for t in m["temas_obj"]) / len(m["temas_obj"])

    por_nivel, brechas, fuera = {}, [], []
    for n in ref["niveles"]:
        vals = []
        for c in n["competencias"]:
            ds = [x for x in (dominio_modulo(r) for r in c["modulos"]) if x is not None]
            c["cobertura"] = round(sum(ds) / len(ds), 3) if ds else None
            vals.append(c["cobertura"] or 0)
            if c["cobertura"] is None:
                fuera.append({"nivel": n["nivel"], "competencia": c["competencia"], "tendencia": c["tendencia"]})
            elif c["cobertura"] < UMBRAL:
                brechas.append({"nivel": n["nivel"], "competencia": c["competencia"], "tendencia": c["tendencia"],
                                "cobertura": c["cobertura"], "modulos": [{"ref": r, "t": (cur.modulo(r, usuario) or {}).get("t", r)}
                                                                         for r in c["modulos"]]})
        por_nivel[n["nivel"]] = sum(vals) / len(vals) if vals else 0
    alcanzado = 0
    for k in range(1, 6):
        if por_nivel.get(k, 0) >= UMBRAL:
            alcanzado = k
        else:
            break
    sig = alcanzado + 1 if alcanzado < 5 else None
    orden = {"nueva": 0, "en alza": 1, "estable": 2, "en declive": 3}
    brechas.sort(key=lambda b: (b["nivel"], orden[b["tendencia"]], b["cobertura"]))
    return {"nivel": alcanzado, "etiqueta": ROLES.get(alcanzado, "Aprendiz") if alcanzado else "Aprendiz",
            "siguiente": sig, "rol_siguiente": ref["niveles"][sig - 1]["rol"] if sig else None,
            "progreso_siguiente": round(por_nivel.get(sig, 0) / UMBRAL, 3) if sig else 1.0,
            "por_nivel": {k: round(v, 3) for k, v in por_nivel.items()},
            "brechas": brechas[:8], "fuera_del_curriculo": fuera[:8],
            "emergentes": [c["competencia"] for n in ref["niveles"] for c in n["competencias"] if c["tendencia"] in ("nueva", "en alza")][:8],
            "en_declive": [c["competencia"] for n in ref["niveles"] for c in n["competencias"] if c["tendencia"] == "en declive"][:5],
            "cambios_5_anios": ref["cambios_5_anios"], "resumen": ref["resumen_mercado"],
            "fuentes": ref.get("fuentes", [])[:8], "fecha": ref["fecha"], "referente": ref["niveles"]}


def pendientes(usuario, perfil, n=2):
    """Áreas cuyo referente falta o caducó, primero las de más prioridad."""
    pesos = perfil.get("pesos", {})
    out = []
    for a in cur.areas(usuario).values():
        if a.get("idioma") or a.get("grupo") == "Idiomas" or a.get("objetivo"):
            continue
        w = cur.peso(a, pesos, usuario, cur.areas_de_metas(usuario))
        r = kv_get(f"mercado:{a['id']}")
        if w > 0 and (not r or time.time() - r["fecha"] > VIGENCIA_DIAS * 86400):
            out.append((-w, r["fecha"] if r else 0, a["id"]))
    return [x[2] for x in sorted(out)[:n]]
