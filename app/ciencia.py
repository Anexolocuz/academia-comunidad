"""Documentos científicos reales para lecciones y áreas (OpenAlex).

OpenAlex (https://openalex.org) indexa >250 millones de artículos, libros,
preprints (arXiv incluido) y revisiones, con citas y resumen. No pide clave.
Las búsquedas funcionan mejor en inglés: las lecciones piden a la IA una
consulta en inglés y los módulos del currículo se traducen una sola vez
(kv consulta_en:<ref>).

Selección: de los ~25 trabajos más relevantes se toman los más citados
(lo clásico, lo que el campo aceptó) más 1-2 recientes (lo nuevo), y se
prefieren revisiones (review) porque resumen un campo entero.
"""
import json
import math
import re
import time
import urllib.parse
import urllib.request

import config
from datetime import datetime

from base import kv_get, kv_set

API = "https://api.openalex.org/works"
CAMPOS = ("id,title,relevance_score,publication_year,cited_by_count,doi,type,primary_location,"
          "authorships,abstract_inverted_index,open_access")
CACHE_DIAS = 30


def _resumen(inv, largo=900):
    if not inv:
        return ""
    pos = sorted((p, w) for w, ps in inv.items() for p in ps)
    return " ".join(w for _, w in pos)[:largo]


def _fmt(w):
    loc = w.get("primary_location") or {}
    fuente = (loc.get("source") or {}).get("display_name") or ""
    autores = [a["author"]["display_name"] for a in (w.get("authorships") or [])[:3] if a.get("author")]
    if len(w.get("authorships") or []) > 3:
        autores.append("et al.")
    doi = w.get("doi") or ""
    return {"titulo": (w.get("title") or "").strip(), "autores": ", ".join(autores),
            "anio": w.get("publication_year"), "revista": fuente, "citas": w.get("cited_by_count") or 0,
            "tipo": w.get("type") or "", "doi": doi, "url": doi or loc.get("landing_page_url") or w.get("id"),
            "abierto": (w.get("open_access") or {}).get("oa_url"),
            "resumen": _resumen(w.get("abstract_inverted_index"))}


def _raiz(p):
    return p[:6]   # «units»/«unit», «metrology»/«metrological»: misma raíz


def _coinciden(claves, w):
    """Al menos la mitad de los términos de la consulta aparecen en título + resumen."""
    if not claves:
        return True
    texto = (w.get("title") or "") + " " + " ".join((w.get("abstract_inverted_index") or {}).keys())
    raices = {_raiz(x) for x in re.findall(r"[a-z]{4,}", texto.lower())}
    hits = sum(1 for c in claves if _raiz(c) in raices)
    en_titulo = any(_raiz(c) in {_raiz(x) for x in re.findall(r"[a-z]{4,}", (w.get("title") or "").lower())} for c in claves)
    return en_titulo and hits >= max(1, (len(claves) + 1) // 2)


def _consultar(params):
    url = API + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": "Academia/" + config.VERSION + " (estudio personal; software libre)"})
    with urllib.request.urlopen(req, timeout=25) as r:
        return json.loads(r.read()).get("results", [])


def buscar(consulta, n=4):
    """[{titulo, autores, anio, revista, citas, tipo, doi, url, abierto, resumen}] o [] si no hay red."""
    consulta = (consulta or "").strip()
    if not consulta:
        return []
    clave = "papers:" + consulta.lower()[:200]
    c = kv_get(clave)
    if c and time.time() - c["fecha"] < CACHE_DIAS * 86400:
        return c["lista"][:n]
    try:
        res = _consultar({"search": consulta, "per-page": 25, "select": CAMPOS,
                          "filter": "has_abstract:true,is_retracted:false"})
        # las revisiones resumen un campo entero: búsqueda aparte para que no queden enterradas
        res += _consultar({"search": consulta, "per-page": 10, "select": CAMPOS,
                           "filter": "has_abstract:true,is_retracted:false,type:review"})
    except Exception:
        return []
    ahora = datetime.now().year
    ws, ids = [], set()
    for w in res:
        if (w.get("title") and w["id"] not in ids and w.get("type") in
                ("article", "review", "preprint", "book-chapter", "book", "conference-paper", "proceedings-article")):
            ids.add(w["id"])
            ws.append(w)
    if not ws:
        return []
    # relevancia como filtro (lo no relacionado no entra por muchas citas que tenga), citas para ordenar;
    # lo poco citado solo entra si es reciente (aún no tuvo tiempo de ser citado)
    tope = max(w.get("relevance_score") or 0 for w in ws) or 1
    claves = set(re.findall(r"[a-z]{4,}", consulta.lower())) - {"about", "using", "between", "based", "versus", "with", "from", "into"}
    ws = [w for w in ws if (w.get("relevance_score") or 0) / tope >= 0.35
          and _coinciden(claves, w)
          and ((w.get("cited_by_count") or 0) >= 10 or (w.get("publication_year") or 0) >= ahora - 2)]
    for w in ws:
        w["_p"] = (1.5 * (w.get("relevance_score") or 0) / tope + math.log10(1 + (w.get("cited_by_count") or 0))
                   + (0.6 if w.get("type") == "review" else 0))
    clasicos = sorted(ws, key=lambda w: -w["_p"])
    recientes = [w for w in ws if (w.get("publication_year") or 0) >= ahora - 3]
    elegidos, vistos = [], set()
    for w in clasicos[:max(1, n - 1)] + recientes[:2] + clasicos[n - 1:]:
        if w["id"] in vistos:
            continue
        vistos.add(w["id"])
        elegidos.append(_fmt(w))
    kv_set(clave, {"fecha": time.time(), "lista": elegidos[:8]})
    return elegidos[:n]


def bloque_prompt(papers, desde=1):
    """Texto para el prompt: [P1] Autores (año). Título. Revista. Citas. Resumen."""
    return "\n".join(
        f"[P{desde + i}] {p['autores']} ({p['anio']}). «{p['titulo']}». {p['revista'] or p['tipo']}. "
        f"{p['citas']} citas. Resumen: {p['resumen']}" for i, p in enumerate(papers))


def para_modulo(ref, n=6):
    """Papers de un módulo del currículo (necesita la consulta en inglés ya traducida)."""
    q = kv_get(f"consulta_en:{ref}")
    return {"consulta": q, "papers": buscar(q, n) if q else []}


def traducir_modulos(ctx, usuario=None, area_id=None):
    """Consulta académica en inglés para cada módulo (una llamada por área, solo los que faltan)."""
    import curriculo as cur
    from lecciones import SISTEMA_BASE
    hechos = 0
    for a in cur.areas(usuario).values():
        if a.get("idioma") or (area_id and a["id"] != area_id):
            continue
        faltan = [m for m in a["modulos"] if not kv_get(f"consulta_en:{m['ref']}")]
        if not faltan:
            continue
        ctx.fase(f"Preparando búsquedas científicas: {a['nombre']}")
        esquema = {"type": "object", "properties": {"consultas": {
            "type": "array", "minItems": len(faltan), "maxItems": len(faltan), "items": {"type": "string"}}},
            "required": ["consultas"]}
        lista = "\n".join(f"{i}. {m['t']} — temas: {', '.join(t['t'] for t in m['temas_obj'][:6])}"
                          for i, m in enumerate(faltan))
        r = ctx.chat([{"role": "system", "content": SISTEMA_BASE}, {"role": "user", "content": (
            f"Área: {a['nombre']}. Para cada módulo, escribe una consulta de búsqueda académica en INGLÉS (3-7 palabras, "
            "términos técnicos que usarían los artículos científicos y revisiones del campo; nada de 'introduction to'). "
            f"Una por módulo, en el mismo orden:\n{lista}\nJSON compacto.")}],
            max_tokens=60 * len(faltan) + 200, temperatura=0.2, esquema=esquema, mostrar=False)
        for m, q in zip(faltan, r["consultas"]):
            if q.strip():
                kv_set(f"consulta_en:{m['ref']}", q.strip())
                hechos += 1
    return {"traducidos": hechos}
