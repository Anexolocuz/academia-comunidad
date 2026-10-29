"""Fuentes verificadas y comparador de fuentes (lecciones, noticias y cualquier afirmación).

1. fiabilidad(url): de qué tipo es una fuente y cuánto pesa (4 = primaria/académica/oficial, 3 = referencia, medio de
   calidad o verificador de datos, 2 = general, 1 = baja, 0 = no se usa: redes sociales y similares).
2. buscar_fuentes(...): búsqueda AGRESIVA: varias consultas en español e inglés, dirigidas a .edu/.gov/Wikipedia y a
   verificadores de datos, más documentos científicos (OpenAlex); máximo 2 por dominio, diversidad de tipos y lectura
   del texto completo de cada página.
3. comparar(...): por cada afirmación, qué fuentes la apoyan y cuáles la contradicen, un veredicto (confirmada, con
   matices, en disputa, contradicha, sin evidencia), el respaldo ponderado por fiabilidad y las diferencias concretas
   (cifras, fechas, definiciones) entre fuentes.
4. verificar_leccion / verificar_texto: extraen las afirmaciones verificables y las contrastan. Se guardan en la
   tabla `verificacion` (por persona).
"""
import hashlib
import json
import re
import time
import urllib.parse
from concurrent.futures import ThreadPoolExecutor

import unicodedata
import ciencia
import ia
from base import ejecutar, fila, filas

ejecutar("""CREATE TABLE IF NOT EXISTS verificacion (
  usuario TEXT, clave TEXT, titulo TEXT, datos TEXT, creada REAL, PRIMARY KEY (usuario, clave))""")

# ------------------------------------------------------------------ fiabilidad
ACADEMICAS = ("doi.org", "arxiv.org", "nature.com", "science.org", "sciencedirect.com", "springer.com", "wiley.com",
              "ieee.org", "acm.org", "aps.org", "iop.org", "pnas.org", "cell.com", "thelancet.com", "nejm.org", "bmj.com",
              "plos.org", "jstor.org", "ncbi.nlm.nih.gov", "pubmed", "openalex.org", "semanticscholar.org",
              "tandfonline.com", "sagepub.com", "oup.com", "cambridge.org/core", "annualreviews.org", "aip.org",
              "rsc.org", "acs.org", "frontiersin.org", "biorxiv.org", "medrxiv.org", "ssrn.com", "nber.org")
OFICIALES = (".gov", ".gob.", ".gouv.", ".gc.ca", "europa.eu", "who.int", "un.org", "oecd.org", "imf.org",
             "worldbank.org", "bis.org", "federalreserve.gov", "banrep.gov.co", "dane.gov.co", "nist.gov", "iso.org",
             "ietf.org", "w3.org", "nasa.gov", "esa.int", "cern.ch", "ipcc.ch", "unesco.org", "iea.org", "wto.org",
             "cepal.org", "iadb.org", "ilo.org", "wipo.int", "itu.int", "nih.gov", "cdc.gov", "bcrp.gob.pe", "bcentral.cl",
             "banxico.org.mx", "bcra.gob.ar", "bde.es", "ine.es", "inegi.org.mx")
UNIVERSIDADES = (".edu", ".ac.", ".edu.", "unal.edu.co", "unam.mx", "ethz.ch", "epfl.ch", "mpg.de", "csic.es",
                 "uba.ar", "uchile.cl", "usp.br", "uniandes.edu.co")
VERIFICADORES = ("snopes.com", "factcheck.org", "politifact.com", "fullfact.org", "maldita.es", "newtral.es",
                 "colombiacheck.com", "chequeado.com", "factual.afp.com", "verificado.com.mx", "efe.com/efe-verifica",
                 "lasillavacia.com/detector", "reuters.com/fact-check", "apnews.com/ap-fact-check", "healthfeedback.org",
                 "climatefeedback.org", "sciencefeedback.co", "leadstories.com", "factchecker", "verificat.cat",
                 "animalpolitico.com/sabueso", "ecuadorchequea.com", "fastcheck.cl")
REFERENCIA = ("wikipedia.org", "britannica.com", "openstax.org", "libretexts.org", "khanacademy.org",
              "mathworld.wolfram.com", "developer.mozilla.org", "docs.python.org", "learn.microsoft.com", "docs.oracle.com",
              "investopedia.com", "quantamagazine.org", "scientificamerican.com", "newscientist.com", "plato.stanford.edu",
              "iep.utm.edu", "physics.info", "hyperphysics", "feynmanlectures.caltech.edu", "ocw.mit.edu", "rae.es",
              "technologyreview.com", "spectrum.ieee.org", "arstechnica.com", "nationalgeographic")
MEDIOS = ("reuters.com", "apnews.com", "afp.com", "bbc.", "nytimes.com", "washingtonpost.com", "theguardian.com",
          "ft.com", "economist.com", "wsj.com", "bloomberg.com", "elpais.com", "elmundo.es", "lemonde.fr", "dw.com",
          "france24.com", "aljazeera.com", "npr.org", "elespectador.com", "eltiempo.com", "lanacion.com.ar",
          "clarin.com", "infobae.com", "eluniversal.com.mx", "emol.com", "larepublica.co", "portafolio.co",
          "valoraanalitik.com", "axios.com", "politico.com", "theverge.com", "wired.com", "efe.com", "europapress.es",
          "cnn.com", "nature.com/articles/d", "science.org/content/article", "lasillavacia.com", "semana.com",
          "elcomercio.pe", "latercera.com", "milenio.com", "eldiario.es", "elconfidencial.com", "cincodias")
BAJA = ("medium.com", "blogspot.", "wordpress.com", "wikihow.com", "answers.", "ehow.", "monografias.com",
        "rincondelvago", "buenastareas", "prezi.com", "studocu", "coursehero", "chegg", "brainly", "lifeder.com",
        "significados.com", "concepto.de", "ejemplos.co", "sutori", "steemit", "substack.com", "zenodo.org")
NOMBRE_NIVEL = {4: "🏛️ primaria", 3: "📚 confiable", 2: "🌐 general", 1: "⚠️ baja", 0: "⛔ no se usa"}


def dominio(url):
    try:
        h = urllib.parse.urlparse(url).hostname or ""
    except ValueError:
        return ""
    return h[4:] if h.startswith("www.") else h


def fiabilidad(url):
    """{nivel 0-4, tipo, dominio}. Por tipo de fuente, no por si la página en concreto tiene razón."""
    u = (url or "").lower()
    d = dominio(u)
    if any(e in u for e in ia.EVITAR):
        return {"nivel": 0, "tipo": "red social o foro", "dominio": d}
    if any(v in u for v in VERIFICADORES):
        return {"nivel": 3, "tipo": "verificador de datos", "dominio": d}
    if any(a in u for a in ACADEMICAS):
        return {"nivel": 4, "tipo": "académica", "dominio": d}
    if any(o in d or o in u for o in OFICIALES):
        return {"nivel": 4, "tipo": "oficial", "dominio": d}
    if any(b in u for b in BAJA):
        return {"nivel": 1, "tipo": "blog o contenido sin revisión", "dominio": d}
    if any(x in d for x in UNIVERSIDADES):
        return {"nivel": 3, "tipo": "universidad", "dominio": d}
    if any(r in u for r in REFERENCIA):
        return {"nivel": 3, "tipo": "referencia", "dominio": d}
    if any(m in u for m in MEDIOS):
        return {"nivel": 3, "tipo": "medio de calidad", "dominio": d}
    return {"nivel": 2, "tipo": "general", "dominio": d}


# ------------------------------------------------------------------ relevancia de lo encontrado
_VACIAS = {"para", "como", "sobre", "entre", "desde", "hacia", "cual", "cuales", "that", "with", "from", "this", "what",
           "which", "into", "about", "site", "edu", "gov", "wikipedia", "org", "los", "las", "una", "unos", "del"}


def _lista(texto):
    """Palabras de contenido (≥4 letras, sin tildes, minúsculas) en orden de aparición, cortadas a 6 letras para tolerar
    plurales y género."""
    t = unicodedata.normalize("NFKD", (texto or "").lower())
    t = "".join(c for c in t if not unicodedata.combining(c))
    out = []
    for w in re.findall(r"[a-z0-9]{4,}", t):
        if w not in _VACIAS and w[:6] not in out:
            out.append(w[:6])
    return out


def relevancia(r, consultas):
    """0-1: qué tanto habla de lo buscado. Vale 1 si trae las dos primeras palabras de alguna consulta (el tema mismo) y,
    si no, la parte de sus palabras que aparece en el título, la dirección o el resumen. Descarta lo que el buscador
    trae por una sola palabra suelta (p. ej. «cambio de paradigma» al buscar Zero Trust)."""
    listas = [_lista(re.sub(r"site:\S+", "", q)) for q in consultas[:2] if q]
    listas = [l for l in listas if l]
    if not listas:
        return 1.0
    hay = set(_lista(f"{r.get('titulo', '')} {r.get('url', '')} {r.get('texto', '')}"))
    mejor = 0.0
    for l in listas:
        if all(a in hay for a in l[:2]):
            return 1.0
        mejor = max(mejor, len(set(l) & hay) / min(len(l), 5))
    return mejor


def _portada(url):
    try:
        return urllib.parse.urlparse(url).path.strip("/") == ""
    except ValueError:
        return False


# ------------------------------------------------------------------ búsqueda agresiva
def buscar_fuentes(consultas, consultas_en=(), n=12, verificadores=False, academicas=True, leer=True, largo=3000,
                   excluir=()):
    """Junta fuentes para un tema o unas afirmaciones. `consultas` en español, `consultas_en` en inglés."""
    crudas = []
    def lanzar(q, idioma):
        return [dict(r, idioma=idioma) for r in ia.buscar_web(q, 8, idioma)]
    # Pocas consultas bien elegidas (van en fila, una cada 1,2 s, con caché): las principales en español e inglés y
    # UNA dirigida a cada tipo de fuente de calidad (Wikipedia, .edu, .gov, verificadores) con la consulta principal.
    es, en = list(consultas)[:3], list(consultas_en)[:3]
    tareas = [(q, "es") for q in es] + [(q, "en") for q in en]
    if es:
        tareas.append((f"{es[0]} site:wikipedia.org", "es"))
    if en:
        tareas += [(f"{en[0]} site:edu", "en"), (f"{en[0]} site:gov", "en")]
    if verificadores:
        if es:
            tareas.append((f"{es[0]} verificación falso o verdadero", "es"))
        if en:
            tareas.append((f"{en[0]} fact check", "en"))
    with ThreadPoolExecutor(2) as ex:
        for lote in ex.map(lambda t: lanzar(*t), tareas):
            crudas += lote
    vistos, por_dom, cand = set(excluir), {}, []
    for r in crudas:
        u = r["url"].split("#")[0]
        if u in vistos:
            continue
        vistos.add(u)
        f = fiabilidad(u)
        if f["nivel"] == 0 or por_dom.get(f["dominio"], 0) >= 2 or _portada(u):
            continue
        por_dom[f["dominio"]] = por_dom.get(f["dominio"], 0) + 1
        cand.append({"titulo": r["titulo"], "url": u, "texto": r["texto"], "fiabilidad": f, "clase": "web",
                     "relevancia": relevancia(r, es[:1] + en[:1])})
    # lo que no habla del tema (solo comparte una palabra) se descarta; si quedara casi nada, se conservan las mejores
    buenas = [c for c in cand if c["relevancia"] >= 0.6]
    cand = buenas if len(buenas) >= 3 else sorted(cand, key=lambda c: -c["relevancia"])[:max(3, len(buenas))]
    papers = []
    if academicas:
        for q in list(consultas_en)[:3] or list(consultas)[:2]:
            for p in ciencia.buscar(q, 3):
                if p["url"] not in vistos and p.get("resumen"):
                    vistos.add(p["url"])
                    papers.append({"titulo": p["titulo"], "url": p["url"], "texto": p["resumen"],
                                   "fiabilidad": {"nivel": 4, "tipo": "académica", "dominio": dominio(p["url"]) or "doi.org"},
                                   "clase": "paper", "autores": p["autores"], "anio": p["anio"], "citas": p["citas"]})
    # diversidad: primero lo mejor de cada tipo, luego por fiabilidad (estable: dentro de cada nivel manda el buscador)
    cand.sort(key=lambda c: (-c["fiabilidad"]["nivel"], -c["relevancia"]))
    elegidas, tipos = [], set()
    for c in cand:
        if c["fiabilidad"]["tipo"] not in tipos and c["fiabilidad"]["nivel"] >= 2:
            tipos.add(c["fiabilidad"]["tipo"])
            elegidas.append(c)
    elegidas += papers[:3]
    for c in cand:
        if len(elegidas) >= n:
            break
        if c not in elegidas and c["fiabilidad"]["nivel"] >= 2:
            elegidas.append(c)
    elegidas = elegidas[:n]
    if leer:
        from noticias import _texto_articulo
        web = [c for c in elegidas if c["clase"] == "web"]
        with ThreadPoolExecutor(6) as ex:
            textos = list(ex.map(lambda c: _texto_articulo(c["url"], largo), web))
        for c, t in zip(web, textos):
            c["leido"] = bool(t)
            if t:
                c["texto"] = t
    return elegidas


# ------------------------------------------------------------------ comparador
VEREDICTOS = ["confirmada", "confirmada con matices", "en disputa", "contradicha", "sin evidencia"]


def _esquema(k, n_af=None):
    idx = {"type": "integer", "minimum": 0, "maximum": max(0, k - 1)}
    return {"type": "object", "properties": {
        "resultados": {"type": "array", "minItems": 1, "maxItems": 16, "items": {"type": "object", "properties": {
            "afirmacion": {"type": "string"}, "veredicto": {"type": "string", "enum": VEREDICTOS},
            "apoyan": {"type": "array", "maxItems": k, "items": idx},
            "contradicen": {"type": "array", "maxItems": k, "items": idx},
            "matiz": {"type": "string"}}, "required": ["afirmacion", "veredicto", "apoyan", "contradicen", "matiz"]}},
        "diferencias": {"type": "array", "maxItems": 8, "items": {"type": "object", "properties": {
            "aspecto": {"type": "string"}, "detalle": {"type": "string"},
            "fuentes": {"type": "array", "maxItems": k, "items": idx}}, "required": ["aspecto", "detalle", "fuentes"]}},
        "conclusion": {"type": "string"}},
        "required": ["resultados", "diferencias", "conclusion"]}


def _confianza(apoyan, contradicen, fs):
    """alta / media / baja según cuántas fuentes independientes y de qué fiabilidad respaldan."""
    niv = [fs[i]["fiabilidad"]["nivel"] for i in apoyan]
    contra = [fs[i]["fiabilidad"]["nivel"] for i in contradicen]
    peso = sum(niv) - sum(contra)
    if contra and max(contra) >= max(niv or [0]):
        return "baja", peso
    if (len(niv) >= 3 and max(niv) >= 3) or (len(niv) >= 2 and max(niv) >= 4):
        return "alta", peso
    if niv and max(niv) >= 3:
        return "media", peso
    return "baja", peso


def comparar(ctx, afirmaciones, fuentes, contexto=""):
    from lecciones import SISTEMA_BASE
    k = len(fuentes)
    bloque = "\n\n".join(
        f"### FUENTE {i} · {f['fiabilidad']['dominio']} ({f['fiabilidad']['tipo']}, fiabilidad {f['fiabilidad']['nivel']}/4)"
        f"\n{f['titulo']}\n{f['texto'][:2600]}" for i, f in enumerate(fuentes))
    lista = "\n".join(f"{i + 1}. {a}" for i, a in enumerate(afirmaciones))
    ctx.fase(f"Contrastando {len(afirmaciones)} afirmaciones con {k} fuentes")
    r = ctx.chat([{"role": "system", "content": SISTEMA_BASE}, {"role": "user", "content": (
        f"{contexto}\nVerifica cada afirmación contra las fuentes, con rigor de verificador de datos.\n"
        "- apoyan / contradicen: índices de las fuentes cuyo TEXTO lo dice explícitamente (no supongas; si una fuente no "
        "lo trata, no la pongas).\n- veredicto: confirmada (varias fuentes la apoyan y ninguna la contradice), "
        "confirmada con matices (en lo esencial sí, pero con precisiones), en disputa (fuentes fiables no coinciden), "
        "contradicha (las fuentes más fiables dicen otra cosa), sin evidencia (ninguna fuente la trata).\n"
        "- matiz: la precisión, la cifra exacta o qué dice la fuente que contradice (una o dos frases).\n"
        "- diferencias: cifras, fechas, definiciones o enfoques que difieren ENTRE las fuentes (aunque no estén en la "
        "lista), diciendo qué fuente dice qué.\n- conclusion: 2-3 frases: qué está bien establecido y qué no.\n"
        "Pesa más las fuentes de mayor fiabilidad. Todo en español. JSON compacto.\n\n"
        f"AFIRMACIONES:\n{lista}\n\nFUENTES:\n{bloque}")}],
        max_tokens=4500, temperatura=0.2, esquema=_esquema(k))
    for x in r["resultados"]:
        x["apoyan"] = sorted({i for i in x["apoyan"] if 0 <= i < k})
        x["contradicen"] = sorted({i for i in x["contradicen"] if 0 <= i < k and i not in x["apoyan"]})
        x["confianza"], x["peso"] = _confianza(x["apoyan"], x["contradicen"], fuentes)
        if not x["apoyan"] and not x["contradicen"]:
            x["veredicto"] = "sin evidencia"
    for dif in r["diferencias"]:
        dif["fuentes"] = sorted({i for i in dif["fuentes"] if 0 <= i < k})
    orden = {v: i for i, v in enumerate(VEREDICTOS)}
    r["resultados"].sort(key=lambda x: (orden[x["veredicto"]] if x["veredicto"] in ("contradicha", "en disputa") else 9,
                                        -x["peso"]))
    r["fuentes"] = [{"titulo": f["titulo"], "url": f["url"], "fiabilidad": f["fiabilidad"], "clase": f["clase"],
                     "leido": f.get("leido", f["clase"] == "paper")} for f in fuentes]
    r["resumen"] = {v: sum(1 for x in r["resultados"] if x["veredicto"] == v) for v in VEREDICTOS}
    return r


# ------------------------------------------------------------------ casos de uso
ESQUEMA_EXTRAER = {"type": "object", "properties": {
    "afirmaciones": {"type": "array", "minItems": 3, "maxItems": 14, "items": {"type": "string"}},
    "consultas": {"type": "array", "minItems": 2, "maxItems": 5, "items": {"type": "string"}},
    "consultas_en": {"type": "array", "minItems": 2, "maxItems": 5, "items": {"type": "string"}}},
    "required": ["afirmaciones", "consultas", "consultas_en"]}


def _extraer(ctx, texto, que):
    from lecciones import SISTEMA_BASE
    ctx.fase("Eligiendo qué verificar")
    return ctx.chat([{"role": "system", "content": SISTEMA_BASE}, {"role": "user", "content": (
        f"{que}\nExtrae las afirmaciones VERIFICABLES más importantes (hechos, cifras, fechas, definiciones, atribuciones "
        "de descubrimientos, resultados): cada una autocontenida, en una frase, tal como la sostiene el texto. Prioriza "
        "lo que más importa entender bien y lo que tiene más riesgo de estar mal o desactualizado. Además, consultas de "
        "búsqueda (2-6 palabras) en español y en inglés que encuentren fuentes sobre esas afirmaciones. JSON compacto."
        f"\n\nTEXTO:\n{texto[:16000]}")}], max_tokens=1500, temperatura=0.2, esquema=ESQUEMA_EXTRAER, mostrar=False)


def _guardar(usuario, clave, titulo, datos):
    datos["creado"] = time.time()
    ejecutar("""INSERT INTO verificacion(usuario,clave,titulo,datos,creada) VALUES(?,?,?,?,?)
                ON CONFLICT(usuario,clave) DO UPDATE SET titulo=excluded.titulo, datos=excluded.datos,
                creada=excluded.creada""", (usuario, clave, titulo, json.dumps(datos, ensure_ascii=False), time.time()))
    return datos


def verificar_leccion(ctx, usuario, tid):
    import adaptativo as aa
    import curriculo as cur
    lecc = fila("SELECT contenido, fuentes FROM leccion WHERE usuario=? AND tema=?", (usuario, tid))
    t = cur.tema(tid, usuario)
    if not lecc or not t:
        raise ValueError("lección no encontrada")
    secs = aa._secciones(lecc["contenido"])
    partes = [(ti, aa._recortar_parte(tx, 2200)) for ti, tx in secs if ti.lower().startswith("parte ")] or \
             [("Lección", lecc["contenido"][:14000])]
    texto = "\n\n".join(f"## {ti}\n{tx}" for ti, tx in partes)
    ex = _extraer(ctx, texto, f"Lección «{t['t']}» ({t['d']}).")
    ya = {f.get("url") for f in json.loads(lecc["fuentes"] or "[]")}
    ctx.fase("Buscando fuentes verificadas (académicas, oficiales, referencia)")
    fs = buscar_fuentes(ex["consultas"], ex["consultas_en"], n=12, excluir=())
    r = comparar(ctx, ex["afirmaciones"], fs, f"Lección para un estudiante: «{t['t']}».")
    r["usadas_en_la_leccion"] = sum(1 for f in fs if f["url"] in ya)
    return _guardar(usuario, f"tema:{tid}", t["t"], r)


def verificar_texto(ctx, usuario, texto):
    """Cualquier afirmación o pregunta del estudiante («¿es cierto que…?»)."""
    ex = _extraer(ctx, texto, "El estudiante quiere saber si esto es cierto (si es una pregunta, verifica las "
                              "afirmaciones que habría que comprobar para responderla).")
    ctx.fase("Buscando fuentes verificadas (también verificadores de datos)")
    fs = buscar_fuentes(ex["consultas"], ex["consultas_en"], n=12, verificadores=True)
    r = comparar(ctx, ex["afirmaciones"], fs, f"Pregunta o afirmación del estudiante: «{texto[:800]}».")
    r["pregunta"] = texto
    clave = "texto:" + hashlib.sha1(texto.strip().lower().encode(), usedforsecurity=False).hexdigest()[:16]
    return _guardar(usuario, clave, texto[:120], r)


def de(usuario, clave):
    r = fila("SELECT datos FROM verificacion WHERE usuario=? AND clave=?", (usuario, clave))
    return json.loads(r["datos"]) if r else None


def historial(usuario, n=30):
    return [{"clave": r["clave"], "titulo": r["titulo"], "creada": r["creada"],
             "resumen": json.loads(r["datos"]).get("resumen")}
            for r in filas("SELECT clave, titulo, datos, creada FROM verificacion WHERE usuario=? AND clave LIKE 'texto:%' "
                           "ORDER BY creada DESC LIMIT ?", (usuario, n))]


def marcar_fuentes(fs):
    """Agrega la fiabilidad a una lista de fuentes {url, …} (noticias, lecciones)."""
    for f in fs:
        f["fiabilidad"] = fiabilidad(f.get("url", ""))
    return fs
