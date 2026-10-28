"""Noticias mundiales para las áreas que estudias.

1. descargar(): lee las fuentes RSS/Atom de config/fuentes.json (sin IA).
2. agrupar(): junta la misma historia contada por varios medios; la cobertura
   (cuántas fuentes distintas la cuentan) es la mejor señal de importancia
   que no depende de la IA.
3. analizar(): la IA local resume en español las más importantes y estima su
   impacto en cada área, los actores/organizaciones y qué estudiar para
   entenderla.
4. ranking()/impacto_por_area()/organizaciones(): vistas diaria, semanal,
   mensual y anual, todas calculadas de lo guardado.
"""
import email.utils
import html
import ipaddress
import json
import math
import re
import socket
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from xml.etree import ElementTree as ET

import curriculo as cur
from base import DATOS, ejecutar, fila, filas, kv_get, kv_set

CONFIG = Path(__file__).resolve().parent.parent / "config" / "fuentes.json"
PERIODOS = {"dia": 1, "semana": 7, "mes": 30, "anio": 365}
AREAS_NOTICIAS = ["sistemas", "ciberseguridad", "mecatronica", "mecanica", "matematicas", "fisica", "quimica", "biologia",
                  "filosofia", "etica", "psicologia", "tecnologia", "finanzas", "administracion"]
UA = "Mozilla/5.0 (X11; Linux x86_64) Academia/1 (lector RSS personal; software libre)"
VACIAS = set("""the and for with from that this have has are was were will into over after about their they
than more what when where which while your just also been being said says could would should among
para como pero sobre entre desde hasta tras ante este esta estos estas porque cuando donde quien
según sus los las del una uno unos unas más muy sin con por que han hay ser fue son será""".split())


PROPIAS = DATOS / "regiones.json"     # regiones y fuentes que agrega/quita el administrador (no van a git)
GLOBAL = "global"


def _propias():
    try:
        return json.loads(PROPIAS.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def guardar_propias(d):
    PROPIAS.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")


def config():
    """Catálogo de config/fuentes.json + lo que el administrador agregó o quitó (datos/regiones.json)."""
    c = json.loads(CONFIG.read_text(encoding="utf-8"))
    p = _propias()
    regiones = dict(c.get("regiones") or {})
    regiones.update(p.get("regiones") or {})
    for r in p.get("quitar_regiones") or []:
        if r != GLOBAL:
            regiones.pop(r, None)
    regiones.setdefault(GLOBAL, {"nombre": "Global", "icono": "🌍", "descripcion": ""})
    quitar = set(p.get("quitar_fuentes") or [])
    fuentes = []
    for f in (c["fuentes"] + [dict(x, propia=True) for x in p.get("fuentes") or []]):
        if f["u"] in quitar:
            continue
        if f.get("tipo") != "lectura":
            f["region"] = f.get("region") if f.get("region") in regiones else GLOBAL
        fuentes.append(f)
    c["regiones"], c["fuentes"] = regiones, fuentes
    return c


def region_de_fuente(cfg=None):
    return {f["n"]: f.get("region", GLOBAL) for f in (cfg or config())["fuentes"] if f.get("tipo") != "lectura"}


def _regiones_de_grupos(desde):
    """grupo → regiones de todas las fuentes que cuentan esa historia."""
    rf = region_de_fuente()
    out = {}
    for r in filas("SELECT grupo, fuente FROM noticia WHERE tipo='noticia' AND publicada>?", (desde,)):
        out.setdefault(r["grupo"], set()).add(rf.get(r["fuente"], GLOBAL))
    return out


def _limpiar(t):
    t = re.sub(r"<[^>]+>", " ", html.unescape(t or ""))
    return re.sub(r"\s+", " ", t).strip()


def _fecha(t):
    if not t:
        return None
    try:
        return email.utils.parsedate_to_datetime(t).timestamp()
    except (TypeError, ValueError):
        pass
    try:
        return datetime.fromisoformat(t.strip().replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def _hijo(el, *nombres):
    for h in el:
        tag = h.tag.rsplit("}", 1)[-1].lower()
        if tag in nombres:
            return h
    return None


def _items(xml):
    raiz = ET.fromstring(xml)
    out = []
    for el in raiz.iter():
        tag = el.tag.rsplit("}", 1)[-1].lower()
        if tag not in ("item", "entry"):
            continue
        tit = _hijo(el, "title")
        lnk = _hijo(el, "link")
        url = None
        if lnk is not None:
            url = (lnk.text or "").strip() or lnk.get("href")
        if not url:
            g = _hijo(el, "guid", "id")
            url = (g.text or "").strip() if g is not None else None
        desc = _hijo(el, "description", "summary", "content", "encoded")
        fec = _hijo(el, "pubdate", "published", "updated", "date")
        if tit is None or not url or not url.startswith("http"):
            continue
        out.append({"titulo": _limpiar(tit.text)[:300], "url": url,
                    "resumen": _limpiar(desc.text if desc is not None else "")[:600],
                    "fecha": _fecha(fec.text if fec is not None else None)})
    return out


def _bajar(f):
    try:
        req = urllib.request.Request(f["u"], headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=25) as r:
            return f, _items(r.read())
    except Exception as e:
        return f, e


def etiquetar(texto, base_areas, palabras):
    t = f" {texto.lower()} "
    areas = set(base_areas)
    for a, ps in palabras.items():
        # la palabra clave debe empezar en inicio de palabra ("cell" no casa con "excellent")
        if any(re.search(r"(?<![\w])" + re.escape(p.strip()), t) for p in ps):
            areas.add(a)
    return sorted(areas)


def descargar(regiones=None):
    """regiones = las que alguien usa (prioridad > 0); None = todas. Las de lectura (idiomas) siempre."""
    cfg = config()
    if regiones is not None:
        cfg["fuentes"] = [f for f in cfg["fuentes"] if f.get("tipo") == "lectura" or f.get("region") in regiones]
    palabras = cfg["palabras"]
    ahora = time.time()
    nuevas, errores = 0, []
    with ThreadPoolExecutor(12) as ex:
        for f, items in ex.map(_bajar, cfg["fuentes"]):
            if isinstance(items, Exception):
                errores.append(f"{f['n']}: {type(items).__name__}")
                continue
            items = sorted(items, key=lambda x: -(x["fecha"] or ahora))[:60]  # una vez al día: más por fuente
            for it in items:
                pub = it["fecha"] or ahora
                if pub < ahora - 4 * 86400 or pub > ahora + 86400:
                    continue  # viejas (o fechas absurdas): no se importan
                lectura = f.get("tipo") == "lectura"
                areas = [f["area"]] if lectura else etiquetar(
                    it["titulo"] + " " + it["resumen"], f.get("areas", []), palabras)
                cur_ = ejecutar("""INSERT OR IGNORE INTO noticia(url,titulo,resumen,fuente,idioma,tipo,peso,
                                   publicada,vista,areas) VALUES(?,?,?,?,?,?,?,?,?,?)""",
                                (it["url"], it["titulo"], it["resumen"], f["n"], f.get("idioma"),
                                 "lectura" if lectura else "noticia", f.get("peso", 1), pub, ahora,
                                 json.dumps(areas)))
                nuevas += cur_.rowcount
    agrupar()
    kv_set("noticias_ultima", {"fecha": ahora, "nuevas": nuevas, "errores": errores})
    podar()
    return {"nuevas": nuevas, "errores": errores}


def _tokens(t):
    return {w for w in re.findall(r"[\wáéíóúñü]{4,}", t.lower()) if w not in VACIAS}


def agrupar():
    """Agrupa por similitud de títulos (Jaccard) las noticias de 3 días."""
    desde = time.time() - 3 * 86400
    ns = filas("SELECT id,titulo,resumen,fuente,peso,areas,grupo FROM noticia "
               "WHERE tipo='noticia' AND publicada>? ORDER BY publicada", (desde,))
    cabezas = []  # (id, tokens, fuentes set)
    asign = {}
    for n in ns:
        tk = _tokens(n["titulo"])
        mejor, sim = None, 0
        for c in cabezas:
            inter = len(tk & c[1])
            if inter < 2:
                continue
            j = inter / len(tk | c[1])
            if j > sim:
                mejor, sim = c, j
        if mejor and sim >= 0.3:
            mejor[2].add(n["fuente"])
            mejor[1].update(tk)
            asign[n["id"]] = mejor[0]
        else:
            cabezas.append((n["id"], set(tk), {n["fuente"]}, n))
            asign[n["id"]] = n["id"]
    for c in cabezas:
        n = c[3]
        cob = len(c[2])
        nareas = len([a for a in json.loads(n["areas"] or "[]") if a in AREAS_NOTICIAS])
        puntaje = n["peso"] + 1.6 * (cob - 1) + 0.4 * min(nareas, 3)
        ejecutar("UPDATE noticia SET grupo=?, cobertura=?, puntaje=? WHERE id=?", (c[0], cob, puntaje, c[0]))
    for nid, g in asign.items():
        if nid != g:
            ejecutar("UPDATE noticia SET grupo=? WHERE id=?", (g, nid))


def podar():
    limite = time.time() - 400 * 86400
    ejecutar("DELETE FROM noticia WHERE publicada<? AND analisis IS NULL", (limite,))
    ejecutar("DELETE FROM noticia WHERE tipo='lectura' AND publicada<?", (time.time() - 14 * 86400,))


# -------------------------------------------------------------- análisis IA
def esquema_analisis():
    refs = [r for r, _ in cur.catalogo_modulos()]
    return {"type": "object", "properties": {
        "titulo_es": {"type": "string"},
        "resumen_es": {"type": "string"},
        "importancia": {"type": "integer", "minimum": 1, "maximum": 10},
        "tipo_hecho": {"type": "string", "enum": ["hecho confirmado", "anuncio oficial", "estudio científico revisado",
                                                  "estudio preliminar", "análisis u opinión", "sin confirmar"]},
        "impactos": {"type": "array", "minItems": 1, "maxItems": 5, "items": {"type": "object", "properties": {
            "area": {"type": "string", "enum": AREAS_NOTICIAS},
            "nivel": {"type": "integer", "minimum": 1, "maximum": 5},
            "como": {"type": "string"}}, "required": ["area", "nivel", "como"]}},
        "organizaciones": {"type": "array", "maxItems": 6, "items": {"type": "string"}},
        "plazo": {"type": "string", "enum": ["inmediato", "meses", "años", "décadas"]},
        "contexto": {"type": "string"},
        "por_que_importa": {"type": "string"},
        "conceptos": {"type": "array", "maxItems": 5, "items": {"type": "object", "properties": {
            "concepto": {"type": "string"}, "explicacion": {"type": "string"}}, "required": ["concepto", "explicacion"]}},
        "consecuencias": {"type": "array", "maxItems": 4, "items": {"type": "string"}},
        "preguntas": {"type": "array", "maxItems": 3, "items": {"type": "string"}},
        "consulta_cientifica": {"type": "string"},
        "estudiar": {"type": "string", "enum": refs},
        "estudiar_extra": {"type": "array", "maxItems": 2, "items": {"type": "string", "enum": refs}}},
        "required": ["titulo_es", "resumen_es", "importancia", "tipo_hecho", "impactos", "organizaciones",
                     "plazo", "contexto", "por_que_importa", "conceptos", "consecuencias", "preguntas", "consulta_cientifica",
                     "estudiar", "estudiar_extra"]}


def pendientes_analisis(n=12):
    """Sin analizar, o analizadas con el formato corto antiguo (sin «contexto»): se rehacen a fondo."""
    return filas("""SELECT * FROM noticia WHERE tipo='noticia' AND grupo=id
                    AND (analisis IS NULL OR analisis NOT LIKE '%"contexto"%')
                    AND publicada>? ORDER BY (analisis IS NOT NULL), puntaje DESC LIMIT ?""",
                 (time.time() - 48 * 3600, n))


def analizar(ctx, n=12, ids=None):
    from lecciones import SISTEMA_BASE
    esquema = esquema_analisis()
    hechos = 0
    lista = [fila("SELECT * FROM noticia WHERE id=?", (i,)) for i in ids] if ids else pendientes_analisis(n)
    lista = [x for x in lista if x]
    ctx.fase("Leyendo los artículos completos")
    with ThreadPoolExecutor(6) as ex:  # el texto real del artículo, no solo el resumen del RSS
        cuerpos = dict(zip([x["id"] for x in lista], ex.map(lambda x: _texto_articulo(x["url"], 5000), lista)))
    for no in lista:
        otras = filas("SELECT fuente, titulo, resumen FROM noticia WHERE grupo=? AND id!=? LIMIT 5", (no["id"], no["id"]))
        ctx.fase(f"Analizando: {no['titulo'][:60]}")
        cuerpo = cuerpos.get(no["id"]) or ""
        prompt = (
            _hoy() +
            "Analiza A FONDO esta noticia para un estudiante de ingeniería de sistemas y mecatrónica que también estudia "
            "ciencias, filosofía, ética, finanzas y administración. Quiere entenderla de verdad, no solo el titular.\n"
            f"Fuente: {no['fuente']} · Fecha: {datetime.fromtimestamp(no['publicada'], timezone.utc):%Y-%m-%d}\n"
            f"Título: {no['titulo']}\nResumen RSS: {no['resumen']}\n"
            + (f"Texto del artículo:\n{cuerpo}\n" if cuerpo else "")
            + (("Otras fuentes con la misma historia: " + "; ".join(f"{o['fuente']}: {o['titulo']} — {o['resumen'][:200]}"
                                                                     for o in otras) + "\n") if otras else "") +
            "\nDevuelve JSON: titulo_es (título claro en español), resumen_es (4-6 frases: qué pasó, quién, cifras clave, "
            "solo lo que dicen las fuentes, sin inventar datos, nombres ni cifras), "
            "contexto (3-5 frases de antecedentes: qué hay que saber para entenderla, cómo se llegó aquí; puedes usar "
            "conocimiento general bien establecido, sin cifras inventadas), por_que_importa (2-3 frases: el mecanismo de "
            "fondo y por qué cambia algo), conceptos (2-5 conceptos técnicos, económicos o científicos que hay que "
            "dominar para entenderla, cada uno explicado en 1-2 frases claras), consecuencias (cadena causa→efecto "
            "probable, 2-4 pasos), preguntas (2-3 preguntas abiertas para pensar críticamente), consulta_cientifica (3-6 "
            "términos técnicos EN INGLÉS sobre el tema de fondo, para buscar artículos científicos; p. ej. 'high-energy "
            "neutrino astronomy detector'), importancia 1-10 a escala mundial (10 = histórico), "
            "tipo_hecho ('hecho confirmado' = suceso reportado por medios; 'anuncio oficial' = comunicado de gobierno, "
            "banco central o empresa; 'estudio científico revisado' SOLO si es un artículo científico publicado; "
            "'estudio preliminar' = preprint o resultado sin revisión; 'análisis u opinión'; 'sin confirmar'), "
            "impactos (solo áreas con efecto real y directo, no conexiones forzadas: nivel 1-5 y una frase concreta; "
            "si la noticia casi no toca ninguna área, un solo impacto de nivel 1), organizaciones (empresas, gobiernos, "
            "instituciones involucradas que aparecen en el texto), plazo del impacto, estudiar (el módulo del "
            "currículo más útil para entender la noticia) y estudiar_extra (hasta 2 módulos más que ayuden).")
        try:
            a = ctx.chat([{"role": "system", "content": SISTEMA_BASE}, {"role": "user", "content": prompt}],
                         max_tokens=2200, temperatura=0.2, esquema=esquema)
        except ValueError:
            continue
        ejecutar("UPDATE noticia SET analisis=?, importancia=? WHERE id=?",
                 (json.dumps(a, ensure_ascii=False), a.get("importancia"), no["id"]))
        hechos += 1
    return {"analizadas": hechos}


# ------------------------------------------------------------------ vistas
def _ventana(periodo):
    return time.time() - PERIODOS.get(periodo, 1) * 86400


def _fmt(n):
    a = json.loads(n["analisis"]) if n.get("analisis") else None
    m = cur.modulo(a["estudiar"]) if a and a.get("estudiar") else None
    extra = [cur.modulo(r) for r in (a or {}).get("estudiar_extra", [])]
    pr = json.loads(n["profundo"]) if n.get("profundo") else {}
    return {"extra": [{"ref": x["ref"], "t": x["t"]} for x in extra if x],
            "tiene": {"explicacion": "explicacion" in pr, "comparacion": "comparacion" in pr},"id": n["id"], "url": n["url"], "fuente": n["fuente"], "titulo": n["titulo"], "resumen": n["resumen"],
            "publicada": n["publicada"], "cobertura": n["cobertura"], "areas": json.loads(n["areas"] or "[]"),
            "importancia": n["importancia"], "puntaje": n["puntaje"], "analisis": a,
            "estudiar": {"ref": m["ref"], "t": m["t"]} if m else None}


def _rango(n):
    imp = n["importancia"] if n["importancia"] is not None else min(10, (n["puntaje"] or 1) * 1.5)
    return imp + 1.2 * math.log2(max(1, n["cobertura"] or 1))


def a_fondo(n):
    """Lista para mostrarse: analizada con el artículo completo, comparada entre medios y explicada a fondo."""
    if not n["analisis"] or '"contexto"' not in n["analisis"] or not n.get("profundo"):
        return False
    pr = json.loads(n["profundo"])
    return "explicacion" in pr and "comparacion" in pr


def ranking(periodo="dia", area=None, limite=30, areas=None, solo_a_fondo=False, regiones=None):
    """areas = las de la persona: solo noticias que tocan alguna (vacío/None = todas).
    regiones = {región: prioridad 0-3} de la persona: 0 = no la ve; más prioridad = más arriba (None = todas igual).
    solo_a_fondo: lo que se le muestra a la gente (cada noticia, siempre a la máxima profundidad)."""
    desde = _ventana(periodo)
    ns = filas("SELECT * FROM noticia WHERE tipo='noticia' AND grupo=id AND publicada>?", (desde,))
    extra = {}
    rg = _regiones_de_grupos(desde)
    if regiones is not None:
        ns = [n for n in ns if max((regiones.get(r, 0) for r in rg.get(n["id"], {GLOBAL})), default=0) > 0]
        for n in ns:
            prio = max(regiones.get(r, 0) for r in rg.get(n["id"], {GLOBAL}))
            extra[n["id"]] = 1.5 * (prio - 2)          # prioridad 3 sube, 1 baja (la importancia va de 1 a 10)
    if solo_a_fondo:
        ns = [n for n in ns if a_fondo(n)]
    if areas and not area:
        def de_las_suyas(n):
            if n["analisis"]:
                return any(i["area"] in areas for i in json.loads(n["analisis"]).get("impactos", []))
            return bool(areas & set(json.loads(n["areas"] or "[]")))
        ns = [n for n in ns if de_las_suyas(n)]
    if area:
        def toca(n):
            if n["analisis"]:
                return any(i["area"] == area for i in json.loads(n["analisis"]).get("impactos", []))
            return area in json.loads(n["areas"] or "[]")
        ns = [n for n in ns if toca(n)]
    if periodo != "dia":  # en semana/mes/año pesa más lo que la IA ya juzgó
        ns = [n for n in ns if n["importancia"] is not None] or ns
    ns.sort(key=lambda n: _rango(n) + extra.get(n["id"], 0), reverse=True)
    return [_fmt(n) | {"regiones": sorted(rg.get(n["id"], {GLOBAL}))} for n in ns[:limite]]


def impacto_por_area(periodo="semana", por_area=5):
    ns = filas("SELECT * FROM noticia WHERE tipo='noticia' AND grupo=id AND analisis IS NOT NULL AND publicada>?",
               (_ventana(periodo),))
    out = {a: [] for a in AREAS_NOTICIAS}
    for n in ns:
        a = json.loads(n["analisis"])
        for i in a.get("impactos", []):
            if i["area"] in out:
                out[i["area"]].append((i["nivel"] * (n["importancia"] or 1), i, n, a))
    res = []
    nombres = cur.areas()
    for area, lista in out.items():
        lista.sort(key=lambda x: -x[0])
        res.append({"area": area, "nombre": nombres[area]["nombre"], "icono": nombres[area].get("icono"),
                    "color": nombres[area].get("color"), "total": len(lista),
                    "presion": round(sum(x[1]["nivel"] for x in lista) / max(1, len(lista)), 2) if lista else 0,
                    "top": [{"id": n["id"], "titulo": a.get("titulo_es") or n["titulo"], "nivel": i["nivel"],
                             "como": i["como"], "url": n["url"], "importancia": n["importancia"]}
                            for _, i, n, a in lista[:por_area]]})
    res.sort(key=lambda r: -sum(t["nivel"] * (t["importancia"] or 1) for t in r["top"]))
    return res


def organizaciones(periodo="semana", limite=15):
    ns = filas("SELECT analisis, importancia FROM noticia WHERE analisis IS NOT NULL AND grupo=id AND publicada>?",
               (_ventana(periodo),))
    cuenta = {}
    for n in ns:
        a = json.loads(n["analisis"])
        for o in a.get("organizaciones", []):
            k = o.strip()
            if not k:
                continue
            c = cuenta.setdefault(k.lower(), {"nombre": k, "menciones": 0, "peso": 0, "areas": {}})
            c["menciones"] += 1
            c["peso"] += n["importancia"] or 1
            for i in a.get("impactos", []):
                c["areas"][i["area"]] = c["areas"].get(i["area"], 0) + i["nivel"]
    out = sorted(cuenta.values(), key=lambda c: -c["peso"])[:limite]
    for c in out:
        c["areas"] = [a for a, _ in sorted(c["areas"].items(), key=lambda x: -x[1])[:3]]
    return out


def lecturas(idioma_area=None, limite=12):
    sql = "SELECT * FROM noticia WHERE tipo='lectura'"
    args = []
    if idioma_area:
        sql += " AND areas LIKE ?"
        args.append(f'%"{idioma_area}"%')
    sql += " ORDER BY publicada DESC LIMIT ?"
    args.append(limite)
    return [{"id": n["id"], "titulo": n["titulo"], "resumen": n["resumen"][:200], "fuente": n["fuente"],
             "url": n["url"], "idioma": n["idioma"], "area": json.loads(n["areas"])[0], "publicada": n["publicada"]}
            for n in filas(sql, args)]


def clave_periodo(periodo, t=None):
    d = datetime.fromtimestamp(t or time.time())
    return {"dia": f"{d:%Y-%m-%d}", "semana": f"{d:%G-S%V}", "mes": f"{d:%Y-%m}", "anio": f"{d:%Y}"}[periodo]


def sintesis(ctx, periodo):
    from lecciones import SISTEMA_BASE
    top = ranking(periodo, limite=25, regiones={GLOBAL: 2})   # la síntesis es común a todos: solo el segmento global
    analizadas = [n for n in top if n["analisis"]]
    if len(analizadas) < 3:
        return {"texto": None, "motivo": "Aún no hay suficientes noticias analizadas en este periodo."}
    nombre = {"dia": "del día", "semana": "de la semana", "mes": "del mes", "anio": "del año"}[periodo]
    lineas = "\n".join(
        f"- [{n['analisis']['importancia']}/10] {n['analisis']['titulo_es']} ({n['fuente']}, {n['cobertura']} fuentes): "
        f"{n['analisis']['resumen_es']} Contexto: {n['analisis'].get('contexto', '')} "
        f"Por qué importa: {n['analisis'].get('por_que_importa', '')} "
        f"Consecuencias: {' → '.join(n['analisis'].get('consecuencias', []))} "
        f"Impactos: " + "; ".join(f"{i['area']} {i['nivel']}/5 {i['como']}" for i in n["analisis"]["impactos"])
        for n in analizadas)
    prompt = (_hoy() + f"Escribe la síntesis {nombre} para el estudiante (markdown, 900-1400 palabras). Que la entienda a fondo, "
              "no un listado de titulares:\n"
              "## Lo esencial (5-7 viñetas ordenadas por importancia, cada una con el porqué en una frase)\n"
              "## Las historias de fondo (las 2-3 más importantes explicadas: contexto, mecanismo, qué está en juego)\n"
              "## Qué cambia en cada área (solo las áreas afectadas, con el cómo concreto)\n"
              "## Tendencias y conexiones entre noticias (qué patrón aparece si se miran juntas)\n"
              "## Conceptos para dominar (los 3-5 conceptos que más se repiten, explicados)\n"
              "## Qué deberías estudiar o vigilar\n"
              "Usa SOLO la información de estas noticias y conocimiento general bien establecido (no inventes datos):\n" + lineas)
    ctx.fase(f"Escribiendo la síntesis {nombre}")
    texto = ctx.chat([{"role": "system", "content": SISTEMA_BASE}, {"role": "user", "content": prompt}],
                     max_tokens=3200, temperatura=0.4)
    ejecutar("INSERT OR REPLACE INTO sintesis(periodo,clave,texto,creada,n) VALUES(?,?,?,?,?)",
             (periodo, clave_periodo(periodo), texto, time.time(), len(analizadas)))
    return {"texto": texto}


def sintesis_guardada(periodo):
    return fila("SELECT * FROM sintesis WHERE periodo=? AND clave=?", (periodo, clave_periodo(periodo)))


def _sin_tildes(t):
    import unicodedata
    return unicodedata.normalize("NFKD", t).encode("ascii", "ignore").decode().lower()


SECCIONES_POR_AREA = ("## que cambia", "## que deberias estudiar")


def sintesis_para(texto, nombres, todos):
    """La síntesis se escribe una vez para todos; en «Qué cambia en cada área» y «Qué deberías estudiar»
    cada persona solo ve los puntos de SUS áreas (nombres) o los que no nombran ningún área (todos = nombres
    de todas). Si una sección queda vacía, se quita."""
    if not texto:
        return texto
    claves = [_sin_tildes(n) for n in nombres]
    ajenas = [_sin_tildes(n) for n in todos if n not in nombres]
    # «Sistemas» suelto también nombra «Ingeniería de Sistemas»: se compara la primera palabra significativa
    corto = lambda n: re.sub(r"^ingenieria (de )?", "", _sin_tildes(n)).split(" y ")[0]
    claves += [corto(n) for n in nombres]
    ajenas += [corto(n) for n in todos if n not in nombres]
    out, dentro, bloque, guardados = [], False, [], []

    def cerrar():
        t = _sin_tildes("\n".join(bloque))
        nombra = lambda n: re.search(rf"\b{re.escape(n)}\b", t)   # palabra completa: «ética» ≠ «energética»
        if bloque and (any(nombra(c) for c in claves) or not any(nombra(a) for a in ajenas)):
            guardados.extend(bloque)
        bloque.clear()

    for linea in texto.splitlines():
        if linea.startswith("## "):
            if dentro:
                cerrar()
                if guardados:
                    out.extend(guardados + [""])
                elif out and out[-1].startswith("## "):
                    out.pop()
            dentro = _sin_tildes(linea).startswith(SECCIONES_POR_AREA)
            guardados = []
            out.append(linea)
            continue
        if not dentro:
            out.append(linea)
        elif re.match(r"\s*([-*]|\d+\.)\s", linea) or not linea.strip():
            cerrar()
            if linea.strip():
                bloque.append(linea)
        else:
            bloque.append(linea)
    if dentro:
        cerrar()
        if guardados:
            out.extend(guardados)
        elif out and out[-1].startswith("## "):
            out.pop()
    return "\n".join(out)


# ------------------------------------------------- lectura en otros idiomas
ESQUEMA_LECTURA = {"type": "object", "properties": {
    "texto": {"type": "string"}, "traduccion": {"type": "string"},
    "vocabulario": {"type": "array", "minItems": 5, "maxItems": 12, "items": {"type": "object", "properties": {
        "palabra": {"type": "string"}, "pronunciacion": {"type": "string"}, "significado": {"type": "string"}},
        "required": ["palabra", "pronunciacion", "significado"]}},
    "gramatica": {"type": "string"}},
    "required": ["texto", "traduccion", "vocabulario", "gramatica"]}


def url_publica(url):
    """Solo http(s) hacia direcciones públicas de internet: un enlace de RSS o de búsqueda no puede hacer que
    este PC abra el router, otros equipos de la casa ni servicios locales (SSRF)."""
    u = urllib.parse.urlparse(url or "")
    if u.scheme not in ("http", "https") or not u.hostname:
        return False
    try:
        ips = {i[4][0] for i in socket.getaddrinfo(u.hostname, u.port or (443 if u.scheme == "https" else 80))}
    except OSError:
        return False
    return bool(ips) and all(ipaddress.ip_address(ip.split("%")[0]).is_global for ip in ips)


class _SoloPublicas(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not url_publica(newurl):
            raise urllib.error.URLError("redirección a una dirección no pública")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


_abrir_publica = urllib.request.build_opener(_SoloPublicas).open


def _texto_articulo(url, largo=1800):
    if not url_publica(url):
        return ""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with _abrir_publica(req, timeout=20) as r:
            h = r.read(800_000).decode(r.headers.get_content_charset() or "utf-8", "ignore")
    except Exception:
        return ""
    cuerpo = re.search(r"<article[^>]*>(.*?)</article>", h, re.S)   # si hay <article>, solo eso (menos menú y pie)
    ps = [_limpiar(p) for p in re.findall(r"<p[^>]*>(.*?)</p>", cuerpo.group(1) if cuerpo else h, re.S)]
    if cuerpo and sum(len(p) for p in ps) < 400:
        ps = [_limpiar(p) for p in re.findall(r"<p[^>]*>(.*?)</p>", h, re.S)]
    return "\n".join(p for p in ps if len(p) > 25)[:largo]


def estudiar_lectura(ctx, nid):
    from lecciones import SISTEMA_BASE
    n = fila("SELECT * FROM noticia WHERE id=?", (nid,))
    area = cur.areas()[json.loads(n["areas"])[0]]
    ctx.fase("Descargando el artículo")
    cuerpo = _texto_articulo(n["url"]) or n["resumen"]
    prompt = (f"Texto real en {area['nombre']} para práctica de lectura de un hispanohablante.\n"
              f"Título: {n['titulo']}\n{cuerpo}\n\n"
              "texto = los primeros 4-6 enunciados del artículo (título incluido) tal cual, separados por saltos de "
              "línea, con la romanización debajo de cada línea si el idioma no usa alfabeto latino; "
              "traduccion = traducción al español línea por línea; vocabulario = palabras útiles del texto; "
              "gramatica = 1-2 estructuras gramaticales que aparecen, explicadas brevemente. JSON compacto.")
    ctx.fase("Preparando la lectura")
    return ctx.chat([{"role": "system", "content": SISTEMA_BASE}, {"role": "user", "content": prompt}],
                    max_tokens=2200, temperatura=0.2, esquema=ESQUEMA_LECTURA) | {
        "idioma": area.get("idioma"), "area": area["id"], "titulo": n["titulo"], "url": n["url"]}


# ------------------------------------------- una noticia a fondo (vista propia)
def _hoy():
    return (f"Fecha de hoy: {datetime.now():%Y-%m-%d}. Las noticias son de estos días: fechas recientes (incluido este año) "
            "son normales, no errores.\n")


def _dominio(url):
    m = re.match(r"https?://(?:www\.)?([^/]+)", url or "")
    return m.group(1).lower() if m else ""


def _guardar_profundo(nid, clave, valor):
    n = fila("SELECT profundo FROM noticia WHERE id=?", (nid,))
    pr = json.loads(n["profundo"]) if n and n["profundo"] else {}
    pr[clave] = valor
    ejecutar("UPDATE noticia SET profundo=? WHERE id=?", (json.dumps(pr, ensure_ascii=False), nid))


MIN_FUENTES = 5   # con menos medios que esto, se buscan más (antes 3)


def fuentes_de(nid, buscar_mas=True, largo=2600):
    """Cada medio que cuenta la historia, con el texto de su artículo. Si el grupo
    tiene menos de 3 medios, busca la misma historia en otros medios con SearXNG."""
    import ia
    cab = fila("SELECT * FROM noticia WHERE id=?", (nid,))
    if not cab:
        raise ValueError("noticia desconocida")
    grupo = filas("SELECT * FROM noticia WHERE grupo=? ORDER BY (id!=?), publicada", (cab["grupo"] or nid, nid))
    vistos, out = set(), []
    for g in grupo or [cab]:
        d = _dominio(g["url"])
        if g["fuente"] in vistos or d in vistos:
            continue
        vistos.update({g["fuente"], d})
        out.append({"fuente": g["fuente"], "titulo": g["titulo"], "url": g["url"], "resumen": g["resumen"], "origen": "rss"})
        if len(out) >= 6:
            break
    if buscar_mas and len(out) < MIN_FUENTES:
        # búsqueda agresiva (verificacion.py): la misma historia en español e inglés, fuentes primarias
        # (oficiales/académicas) y verificadores de datos; máximo 2 por dominio, sin redes sociales
        import verificacion as vf
        a = json.loads(cab["analisis"]) if cab["analisis"] else {}
        es = [cab["titulo"]] + ([a["titulo_es"]] if a.get("titulo_es") and a["titulo_es"] != cab["titulo"] else [])
        en = [cab["titulo"]] if cab["titulo"].isascii() else []
        clave = _tokens(cab["titulo"]) | (_tokens(a["titulo_es"]) if a.get("titulo_es") else set())
        for f in vf.buscar_fuentes(es, en, n=8, verificadores=True, academicas=False, leer=False,
                                   excluir={g["url"] for g in out}):
            d = f["fiabilidad"]["dominio"]
            if d in vistos or len(out) >= 7:
                continue
            # que sea la MISMA historia y no una parecida: comparte una buena parte de las palabras del titular
            comunes = clave & (_tokens(f["titulo"]) | _tokens(f["texto"][:400]))
            if len(comunes) < max(2, round(len(clave) * 0.35)):
                continue
            vistos.add(d)
            out.append({"fuente": d, "titulo": f["titulo"], "url": f["url"], "resumen": f["texto"], "origen": "web"})
    with ThreadPoolExecutor(6) as ex:
        textos = list(ex.map(lambda f: _texto_articulo(f["url"], largo), out))
    for f, t in zip(out, textos):
        f["texto"] = t or f["resumen"]
        f["leido"] = bool(t)
    import verificacion as vf
    vf.marcar_fuentes(out)
    return cab, out


def esquema_comparacion(k):
    idx = {"type": "integer", "minimum": 0, "maximum": max(0, k - 1)}
    return {"type": "object", "properties": {
        "afirmaciones": {"type": "array", "minItems": 4, "maxItems": 18, "items": {"type": "object", "properties": {
            "texto": {"type": "string"},
            "tipo": {"type": "string", "enum": ["hecho", "cifra", "cita", "interpretación", "predicción"]},
            "fuentes": {"type": "array", "minItems": 1, "maxItems": k, "items": idx}},
            "required": ["texto", "tipo", "fuentes"]}},
        "diferencias": {"type": "array", "maxItems": 6, "items": {"type": "object", "properties": {
            "aspecto": {"type": "string"}, "detalle": {"type": "string"}}, "required": ["aspecto", "detalle"]}},
        "enfoques": {"type": "array", "minItems": k, "maxItems": k, "items": {"type": "object", "properties": {
            "fuente": idx, "angulo": {"type": "string"},
            "tono": {"type": "string", "enum": ["neutral", "técnico", "crítico", "optimista", "alarmista", "oficialista"]},
            "omite": {"type": "string"}}, "required": ["fuente", "angulo", "tono", "omite"]}},
        "contradicciones": {"type": "array", "maxItems": 4, "items": {"type": "string"}},
        "conclusion": {"type": "string"}},
        "required": ["afirmaciones", "diferencias", "enfoques", "contradicciones", "conclusion"]}


def comparar(ctx, nid):
    """Qué dice cada medio de la misma historia: afirmaciones ordenadas de la más
    común (todas las fuentes la dicen) a la menos común (solo una), diferencias de
    cifras o enfoque, lo que cada una omite y contradicciones."""
    from lecciones import SISTEMA_BASE
    ctx.fase("Reuniendo los artículos de cada medio")
    cab, fs = fuentes_de(nid)
    if len(fs) < 2:
        _guardar_profundo(nid, "comparacion", {"fuentes": fs and [{k: fs[0][k] for k in ("fuente", "titulo", "url", "origen")}],
                                              "solo_una": True, "creado": time.time()})
        return {"solo_una": True}
    k = len(fs)
    bloque = "\n\n".join(f"### FUENTE {i}: {f['fuente']} ({f['fiabilidad']['tipo']}, fiabilidad "
                         f"{f['fiabilidad']['nivel']}/4)\nTítulo: {f['titulo']}\n{f['texto']}" for i, f in enumerate(fs))
    prompt = (
        _hoy() +
        f"La misma noticia contada por {k} medios distintos. Compáralos con rigor de verificador de datos.\n\n{bloque}\n\n"
        "Devuelve JSON:\n- afirmaciones: las afirmaciones concretas de la historia (hechos, cifras, citas, interpretaciones, "
        "predicciones), cada una escrita en español y con 'fuentes' = índices de TODAS las fuentes cuyo texto la dice "
        "explícitamente (no supongas: si una fuente no la menciona, no la incluyas). Incluye tanto lo que comparten como "
        "lo que solo cuenta una.\n- diferencias: cifras distintas, fechas, nombres o encuadres que no coinciden, "
        "citando qué fuente dice qué.\n- enfoques: uno por fuente (fuente = índice): su ángulo en una frase, su tono y "
        "qué omite que otras sí cuentan.\n- contradicciones: afirmaciones incompatibles entre fuentes (si no hay, []).\n"
        "- conclusion: 2-3 frases: qué está bien establecido, qué es dudoso y qué falta saber. Pesa más lo que dicen "
        "las fuentes oficiales, académicas y los verificadores de datos (fiabilidad 3-4) que un medio general. JSON compacto.")
    ctx.fase(f"Comparando {k} fuentes")
    r = ctx.chat([{"role": "system", "content": SISTEMA_BASE}, {"role": "user", "content": prompt}],
                 max_tokens=3500, temperatura=0.2, esquema=esquema_comparacion(k))
    for a in r["afirmaciones"]:
        a["fuentes"] = sorted({i for i in a["fuentes"] if 0 <= i < k})
        n = len(a["fuentes"])
        a["nivel"] = "todas" if n == k else "varias" if n >= 2 else "una"
        niv = [fs[i]["fiabilidad"]["nivel"] for i in a["fuentes"]]
        # respaldo: cuántas fuentes y de qué calidad (una oficial/académica pesa más que tres blogs)
        a["respaldo"] = "alto" if (n >= 3 and max(niv or [0]) >= 3) or (n >= 2 and max(niv or [0]) >= 4) else \
            "medio" if niv and max(niv) >= 3 else "bajo"
    r["afirmaciones"] = [a for a in r["afirmaciones"] if a["fuentes"]]
    r["afirmaciones"].sort(key=lambda a: -len(a["fuentes"]))   # de lo más común a lo menos común
    r["fuentes"] = [{x: f[x] for x in ("fuente", "titulo", "url", "origen", "fiabilidad")} | {"leido": f.get("leido", bool(f["texto"]))}
                    for f in fs]
    r["creado"] = time.time()
    _guardar_profundo(nid, "comparacion", r)
    return r


ESQUEMA_TARJETAS_NOTICIA = {"type": "object", "properties": {"tarjetas": {
    "type": "array", "minItems": 3, "maxItems": 8, "items": {"type": "object", "properties": {
        "frente": {"type": "string"}, "reverso": {"type": "string"}}, "required": ["frente", "reverso"]}}},
    "required": ["tarjetas"]}


def explicar(ctx, nid):
    """Explicación a fondo de una noticia: hechos, antecedentes, conceptos, mecanismo,
    perspectivas, qué significa por área y qué vigilar, con fuentes web y papers."""
    import ciencia
    import ia
    from lecciones import SISTEMA_BASE
    ctx.fase("Leyendo el artículo y buscando antecedentes")
    cab, fs = fuentes_de(nid, buscar_mas=False, largo=4500)
    a = json.loads(cab["analisis"]) if cab["analisis"] else {}
    titulo = a.get("titulo_es") or cab["titulo"]
    urls = {f["url"] for f in fs}
    fondo = [r for r in ia.buscar_web(f"{titulo} antecedentes explicación", n=6) if r["url"] not in urls][:4]
    papers = ciencia.buscar(a.get("consulta_cientifica") or (a.get("conceptos") or [{}])[0].get("concepto") or titulo, 4)
    papers = [p for p in papers if p["resumen"]]
    bloque_f = "\n\n".join(f"### {f['fuente']}: {f['titulo']}\n{f['texto']}" for f in fs[:3])
    bloque_w = "\n".join(f"[{i + 1}] {r['titulo']} — {r['url']}\n{r['texto']}" for i, r in enumerate(fondo))
    prompt = (
        _hoy() +
        f"Explica A FONDO esta noticia a un estudiante de ingeniería (sistemas y mecatrónica) y administración que quiere "
        f"entender cosas complejas, no el titular.\nNoticia: {titulo}\n"
        + (f"Análisis previo: {json.dumps({k: a.get(k) for k in ('resumen_es', 'contexto', 'por_que_importa', 'conceptos')}, ensure_ascii=False)}\n" if a else "")
        + f"\nARTÍCULOS:\n{bloque_f}\n\nANTECEDENTES (web, cita como [n]):\n{bloque_w or '(ninguno)'}\n"
        + (f"\nDOCUMENTOS CIENTÍFICOS (OpenAlex; cita como [Pn] solo si de verdad aplican):\n{ciencia.bloque_prompt(papers)}\n" if papers else "")
        + "\nMarkdown, 1500-2200 palabras, exactamente estos títulos:\n"
        "## 📰 Qué pasó (hechos y cifras tal como los dan las fuentes)\n"
        "## 🕰️ Antecedentes: cómo se llegó aquí\n"
        "## 🧠 Los conceptos que necesitas (cada concepto explicado de verdad, con un ejemplo; fórmulas en LaTeX si aplica)\n"
        "## ⚙️ El mecanismo (la cadena causa → efecto, paso a paso: por qué ocurre y qué provoca)\n"
        "## ⚖️ Perspectivas y debate (quién gana, quién pierde, qué dicen los distintos actores; dilemas éticos si hay)\n"
        "## 🎓 Qué significa para tus áreas (ingeniería, tecnología, finanzas, administración… solo las que aplican)\n"
        "## 🔭 Qué vigilar después (señales concretas que confirmarían o desmentirían el rumbo)\n"
        "## 🔬 Lo que dice la investigación (solo si hay documentos científicos que apliquen)\n"
        "## 📚 Fuentes (enlaces usados)\n"
        "Empieza directo con el primer título: sin saludo ni presentación. "
        "Distingue siempre lo confirmado de lo especulativo. No inventes cifras, fechas ni citas.")
    msgs = [{"role": "system", "content": SISTEMA_BASE}, {"role": "user", "content": prompt}]
    ctx.fase("Escribiendo la explicación a fondo")
    texto = ctx.chat(msgs, max_tokens=4500, temperatura=0.4)
    ctx.fase("Creando tarjetas de repaso")
    try:
        tj = ctx.chat(msgs + [{"role": "assistant", "content": texto}, {"role": "user", "content":
                      "Crea 4-8 tarjetas de repaso espaciado con los conceptos y mecanismos clave (no datos efímeros como "
                      "cifras del día): pregunta concreta al frente, respuesta corta al reverso. JSON compacto."}],
                      max_tokens=1200, temperatura=0.3, esquema=ESQUEMA_TARJETAS_NOTICIA, mostrar=False)["tarjetas"]
    except ValueError:
        tj = []
    r = {"texto": texto, "tarjetas": tj, "creado": time.time(),
         "fuentes": [{"titulo": f["titulo"], "url": f["url"]} for f in fs[:3]] + [{"titulo": x["titulo"], "url": x["url"]} for x in fondo],
         "papers": [{k: p[k] for k in ("titulo", "autores", "anio", "revista", "citas", "url", "abierto")} for p in papers]}
    _guardar_profundo(nid, "explicacion", r)
    return r


def detalle(nid):
    n = fila("SELECT * FROM noticia WHERE id=?", (nid,))
    if not n:
        return None
    out = _fmt(n)
    out["profundo"] = json.loads(n["profundo"]) if n["profundo"] else {}
    out["grupo"] = [{"fuente": g["fuente"], "titulo": g["titulo"], "url": g["url"]}
                    for g in filas("SELECT fuente,titulo,url FROM noticia WHERE grupo=? AND id!=?", (n["grupo"] or nid, nid))]
    return out


def a_profundizar(areas, n, regiones=None):
    """Las n noticias de hoy que más pesan en estas áreas y regiones (las que esta persona verá) y que aún no están a fondo."""
    return [x["id"] for x in ranking("dia", limite=n * 3, areas=areas, regiones=regiones) if not (x["tiene"]["explicacion"] and
            x["tiene"]["comparacion"] and x["analisis"] and "contexto" in x["analisis"])][:n]


def a_fondo_completo(ctx, nid):
    """Una noticia a la máxima profundidad: análisis con el artículo completo → comparación entre medios →
    explicación a fondo. Cada paso se guarda; si ya estaba hecho, se salta."""
    n = fila("SELECT analisis, profundo FROM noticia WHERE id=?", (nid,))
    if not n:
        return {"error": "no existe"}
    if not n["analisis"] or '"contexto"' not in n["analisis"]:
        analizar(ctx, ids=[nid])
    pr = json.loads((fila("SELECT profundo FROM noticia WHERE id=?", (nid,)) or {}).get("profundo") or "{}")
    if "comparacion" not in pr:
        comparar(ctx, nid)
    pr = json.loads((fila("SELECT profundo FROM noticia WHERE id=?", (nid,)) or {}).get("profundo") or "{}")
    if "explicacion" not in pr:
        explicar(ctx, nid)
    return {"id": nid}


def para_profundizar(n_explicar=3, n_comparar=5):
    """Las de hoy que merecen vista a fondo (para la actualización diaria)."""
    hoy = ranking("dia", limite=30)
    exp = [x["id"] for x in hoy if x["analisis"] and not x["tiene"]["explicacion"]][:n_explicar]
    comp = [x["id"] for x in hoy if x["analisis"] and (x["cobertura"] or 1) >= 2 and not x["tiene"]["comparacion"]][:n_comparar]
    return exp, comp
