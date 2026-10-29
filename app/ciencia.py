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
API_CROSSREF = "https://api.crossref.org/works"      # respaldo y complemento de OpenAlex (API pública, sin clave)
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


def _sin_etiquetas(x):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", x or "")).replace("Abstract", "", 1).strip()


def _crossref(consulta, n):
    """Artículos de Crossref con resumen, en el mismo formato que `_fmt`. [] si falla. Crossref es la base de los DOI:
    sirve cuando OpenAlex no responde o trae pocos resultados."""
    url = API_CROSSREF + "?" + urllib.parse.urlencode({
        "query.bibliographic": consulta, "rows": 25, "filter": "has-abstract:true,type:journal-article",
        "select": "title,author,issued,container-title,DOI,type,is-referenced-by-count,abstract,URL,score"})
    req = urllib.request.Request(url, headers={"User-Agent": "Academia/" + config.VERSION + " (estudio personal; software libre)"})
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            items = json.loads(r.read()).get("message", {}).get("items", [])
    except Exception:
        return []
    ahora = datetime.now().year
    claves = set(re.findall(r"[a-z]{4,}", consulta.lower())) - {"about", "using", "between", "based", "versus", "with", "from", "into"}
    tope = max((i.get("score") or 0) for i in items) or 1 if items else 1
    out = []
    for i in items:
        titulo = _sin_etiquetas(" ".join(i.get("title") or []))
        resumen = _sin_etiquetas(i.get("abstract"))
        anio = ((i.get("issued") or {}).get("date-parts") or [[None]])[0][0]
        citas = i.get("is-referenced-by-count") or 0
        if not titulo or not resumen or (i.get("score") or 0) / tope < 0.45:
            continue
        if not _coinciden(claves, {"title": titulo, "abstract_inverted_index": {w: 1 for w in resumen.split()}}):
            continue
        if citas < 10 and (anio or 0) < ahora - 2:
            continue
        aut = [(a.get("family") or a.get("name") or "") for a in (i.get("author") or [])[:3]]
        if len(i.get("author") or []) > 3:
            aut.append("et al.")
        doi = "https://doi.org/" + i["DOI"] if i.get("DOI") else i.get("URL", "")
        out.append({"titulo": titulo, "autores": ", ".join(a for a in aut if a), "anio": anio,
                    "revista": " ".join(i.get("container-title") or []), "citas": citas, "tipo": "article",
                    "doi": doi, "url": doi, "abierto": None, "resumen": resumen[:900],
                    "_p": 1.5 * (i.get("score") or 0) / tope + math.log10(1 + citas)})
    out.sort(key=lambda w: -w["_p"])
    for w in out:
        w.pop("_p")
    return out[:n]


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
        # OpenAlex no respondió: Crossref como respaldo (se guarda en caché solo si trajo algo)
        extra = _crossref(consulta, n)
        if extra:
            kv_set(clave, {"fecha": time.time(), "lista": extra})
        return extra
    ahora = datetime.now().year
    ws, ids = [], set()
    for w in res:
        if (w.get("title") and w["id"] not in ids and w.get("type") in
                ("article", "review", "preprint", "book-chapter", "book", "conference-paper", "proceedings-article")):
            ids.add(w["id"])
            ws.append(w)
    if not ws:
        return _crossref(consulta, n)
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
    if len(elegidos) < n:       # OpenAlex trajo pocos: Crossref completa (sin repetir DOI ni título)
        vistos_doi = {(e["doi"] or "").lower() for e in elegidos} | {e["titulo"].lower() for e in elegidos}
        for e in _crossref(consulta, n):
            if (e["doi"] or "").lower() not in vistos_doi and e["titulo"].lower() not in vistos_doi:
                elegidos.append(e)
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


ARXIV = "S4306400194"   # fuente arXiv en OpenAlex


def _sobre_el_tema(claves, w):
    """Más laxo que _coinciden: basta con que la mitad de los términos esté en el título o el resumen."""
    if not claves:
        return True
    texto = (w.get("title") or "") + " " + " ".join((w.get("abstract_inverted_index") or {}).keys())
    raices = {_raiz(x) for x in re.findall(r"[a-z]{4,}", texto.lower())}
    return sum(1 for c in claves if _raiz(c) in raices) >= max(1, (len(claves) + 1) // 2)


def _relevantes(ws, corte=0.45):
    """De lo que OpenAlex considera relevante (≥ corte del máximo), lo más citado primero."""
    if not ws:
        return []
    tope = max(w.get("relevance_score") or 0 for w in ws) or 1
    ws = [w for w in ws if (w.get("relevance_score") or 0) / tope >= corte]
    return sorted(ws, key=lambda w: -(w.get("cited_by_count") or 0))


def frontera(consulta, n=8):
    """Lo más vivo de un tema para el mapa de la frontera: revisiones de los últimos 4 años (lo que el campo ya
    ordenó), trabajos de los últimos 2 años más citados (lo que está pegando) y preprints recientes (lo que viene).
    Caché 7 días: la frontera se mira cada mes, no hace falta más."""
    consulta = (consulta or "").strip()
    if not consulta:
        return []
    clave = "frontera:" + consulta.lower()[:200]
    c = kv_get(clave)
    if c and time.time() - c["fecha"] < 7 * 86400:
        return c["lista"][:n]
    anio = datetime.now().year
    base = "has_abstract:true,is_retracted:false"
    try:
        grupos = [
            _relevantes(_consultar({"search": consulta, "per-page": 20, "select": CAMPOS,
                                    "filter": f"{base},type:review,from_publication_date:{anio - 4}-01-01"})),
            _relevantes(_consultar({"search": consulta, "per-page": 25, "select": CAMPOS,
                                    "filter": f"{base},from_publication_date:{anio - 2}-01-01"})),
            # preprints solo de arXiv (moderado): en otros repositorios abiertos se cuela mucho texto sin revisar
            _consultar({"search": consulta, "per-page": 15, "select": CAMPOS, "sort": "relevance_score:desc",
                        "filter": f"{base},type:preprint,primary_location.source.id:{ARXIV},"
                                  f"from_publication_date:{anio - 1}-01-01"}),
        ]
    except Exception:
        return []
    claves = set(re.findall(r"[a-z]{4,}", consulta.lower())) - {"about", "using", "between", "based", "with", "from"}
    out, ids = [], set()
    for k, g in enumerate(grupos):
        for w in g:
            if w["id"] in ids or not w.get("title") or not _sobre_el_tema(claves, w):
                continue
            if k < 2 and (w.get("cited_by_count") or 0) < 5:   # «muy citado» y revisiones: con algo de aval
                continue
            ids.add(w["id"])
            p = _fmt(w)
            p["clase"] = ("revisión", "reciente muy citado", "preprint nuevo")[k]
            p["openalex"] = w["id"]
            out.append(p)
    # intercalar las tres clases para que ninguna se coma el cupo
    orden = sorted(out, key=lambda p: ({"revisión": 0, "reciente muy citado": 1, "preprint nuevo": 2}[p["clase"]],
                                        -(p["citas"] or 0)))
    por = {}
    for p in orden:
        por.setdefault(p["clase"], []).append(p)
    mezcla = []
    while any(por.values()):
        for cl in ("revisión", "reciente muy citado", "preprint nuevo"):
            if por.get(cl):
                mezcla.append(por[cl].pop(0))
    kv_set(clave, {"fecha": time.time(), "lista": mezcla[:12]})
    return mezcla[:n]
