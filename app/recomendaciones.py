"""📚 Lecturas y 📰 noticias recomendadas para una ruta (área) o una lección (tema).

Se calcula solo con lo que ya está en la base y en el currículo: sin IA ni búsquedas web al abrir la vista.

Lecturas, en este orden y sin repetir enlaces:
1. Las del módulo (`lecturas` opcional en el JSON del currículo: [{"t": título, "u": url, "tipo": "libro|curso|web"}]).
2. Documentos científicos y libros citados por las OTRAS lecciones ya escritas del mismo módulo (o del área, si se
   pide la ruta), solo de lecciones con fuentes verificadas una por una (las del taller de lecciones externas:
   modelos `claude-*` y `gemini-*`); las fuentes que la IA local toma de búsquedas automáticas a veces no tratan el
   tema y no se recomiendan. Amplían sin repetir lo que la lección actual ya lista en sus «Fuentes».
3. Los recursos verificados del área (`recursos` del currículo).

Noticias: las del último mes que tocan el área, con la misma regla de perfiles que la vista de Noticias (solo áreas
de la persona y sus regiones); para una lección, primero las que comparten palabras con el tema.
"""
import json
import re
import unicodedata

import curriculo as cur
import noticias as nt
from base import filas

MAX_LECTURAS = 8
MAX_NOTICIAS = 5
_VACIAS = set("""para como pero sobre entre desde hasta este esta estos estas porque cuando donde según sus los las
del una uno unos unas más muy sin con por que han hay ser fue son será introduccion fundamentos basico basicos the and
for with from that this into what""".split())


def _palabras(texto):
    t = unicodedata.normalize("NFKD", str(texto or "").lower())
    t = "".join(c for c in t if not unicodedata.combining(c))
    return {w for w in re.findall(r"[a-z0-9]{4,}", t) if w not in _VACIAS}


VERIFICADAS = ("claude-%", "gemini-%")   # modelos cuyas fuentes se comprobaron una por una al importar


def _fuentes_de(usuario, temas, solo_verificadas=False):
    """Fuentes (lista de dicts) de las lecciones guardadas de esos temas."""
    if not temas:
        return []
    marcas = ",".join("?" * len(temas))
    filtro = " AND (modelo LIKE ? OR modelo LIKE ?)" if solo_verificadas else ""
    out = []
    for r in filas(f"SELECT tema, fuentes FROM leccion WHERE usuario=? AND tema IN ({marcas}) AND fuentes IS NOT NULL{filtro}",
                   (usuario, *temas, *(VERIFICADAS if solo_verificadas else ()))):
        try:
            for f in json.loads(r["fuentes"] or "[]"):
                if isinstance(f, dict) and str(f.get("url") or "").startswith(("http://", "https://")) \
                        and not (solo_verificadas and f.get("agregada")):   # agregada al actualizar: sin comprobar a mano
                    out.append(f | {"_tema": r["tema"]})
        except ValueError:
            continue
    return out


def _lectura(t, u, tipo, origen, detalle=""):
    return {"t": str(t)[:300], "u": str(u)[:500], "tipo": tipo, "origen": origen, "detalle": str(detalle)[:200]}


def _lecturas(usuario, area, modulos, excluir_urls, excluir_tema=None, con_recursos=True):
    vistos, out = set(excluir_urls), []

    def poner(x):
        if x["u"] in vistos or len(out) >= MAX_LECTURAS:
            return
        vistos.add(x["u"])
        out.append(x)

    for m in modulos:                                            # 1. curadas del módulo
        for l in m.get("lecturas") or []:
            if isinstance(l, dict) and str(l.get("u", "")).startswith(("http://", "https://")):
                poner(_lectura(l.get("t") or l["u"], l["u"], l.get("tipo") or "web", "módulo", m["t"]))
    temas = [t["id"] for m in modulos for t in m["temas_obj"] if t["id"] != excluir_tema]
    nombres = {t["id"]: t["t"] for m in modulos for t in m["temas_obj"]}
    fuentes = _fuentes_de(usuario, temas, solo_verificadas=True)  # 2. de otras lecciones (papers y libros primero)
    orden = {"paper": 0, "libro": 1, "informe": 2, "norma": 3}
    for f in sorted(fuentes, key=lambda f: orden.get(f.get("tipo"), 5)):
        tipo = f.get("tipo") if f.get("tipo") in orden else "web"
        detalle = ", ".join(str(x) for x in (f.get("autores"), f.get("anio")) if x)
        poner(_lectura(f.get("titulo") or f["url"], f["url"], tipo, "lección", f"{detalle} · citado en «{nombres.get(f['_tema'], '')}»"
                       if detalle else f"citado en «{nombres.get(f['_tema'], '')}»"))
    for r in (area.get("recursos") or []) if con_recursos else []:   # 3. recursos del área
        if str(r.get("u", "")).startswith(("http://", "https://")):
            poner(_lectura(r.get("t") or r["u"], r["u"], "curso", "área"))
    return out


def _noticias(usuario, area_id, mias, regiones, palabras=None):
    if area_id not in (mias & set(nt.AREAS_NOTICIAS)):
        nombres = cur.areas()
        return [], ("Esta área todavía no recibe noticias: el análisis diario de noticias cubre "
                    + ", ".join(sorted(nombres[a]["nombre"] for a in nt.AREAS_NOTICIAS if a in nombres)) + "."
                    if area_id not in nt.AREAS_NOTICIAS
                    else "Agrega esta área a tus prioridades para ver sus noticias.")
    lista = nt.ranking("mes", area_id, limite=40, areas=mias, solo_a_fondo=True, regiones=regiones)
    def puntos(n):   # palabras del tema que aparecen en la noticia; con menos de 2 no se considera relacionada
        if not palabras:
            return 0
        k = len(palabras & _palabras(f"{(n.get('analisis') or {}).get('titulo_es') or n['titulo']} {n.get('resumen') or ''}"))
        return k if k >= 2 else 0
    def impacto(n):   # 1-5: cuánto toca esta área según el análisis de la noticia (0 si no hay análisis)
        return max((i.get("nivel") or 0 for i in (n.get("analisis") or {}).get("impactos", []) if i.get("area") == area_id),
                   default=0)
    lista = [n for n in lista if impacto(n) >= 3 or puntos(n)]   # fuera las que solo rozan el área
    lista.sort(key=lambda n: (-puntos(n), -impacto(n)))   # estable: a igualdad conserva el orden del ranking
    out = []
    for n in lista[:MAX_NOTICIAS]:
        a = n.get("analisis") or {}
        como = next((i.get("como") for i in a.get("impactos", []) if i.get("area") == area_id), "")
        out.append({"id": n["id"], "titulo": a.get("titulo_es") or n["titulo"], "fuente": n["fuente"], "url": n["url"],
                    "publicada": n["publicada"], "relacionada": puntos(n) > 0, "impacto": impacto(n), "como": como})
    return out, None


def para_area(usuario, area_id, regiones):
    areas = cur.areas(usuario)
    mias = cur.areas_de(usuario)
    if area_id not in areas or area_id not in mias:
        return {"error": "área desconocida"}
    a = areas[area_id]
    noticias, aviso = _noticias(usuario, area_id, mias, regiones)
    # la vista de la ruta ya muestra los recursos del área en su propio bloque: aquí no se repiten
    return {"lecturas": _lecturas(usuario, a, a["modulos"], set(), con_recursos=False), "noticias": noticias,
            "aviso_noticias": aviso}


def para_tema(usuario, tid, regiones):
    t = cur.tema(tid, usuario)
    mias = cur.areas_de(usuario)
    if not t or t["area"] not in mias:
        return {"error": "tema desconocido"}
    a = cur.areas(usuario)[t["area"]]
    m = cur.modulo(t["modulo"], usuario)
    propias = {f["url"] for f in _fuentes_de(usuario, [tid])}     # lo que la lección ya lista en «Fuentes»
    palabras = _palabras(f"{t['t']} {t['d']} {m['t']}")
    noticias, aviso = _noticias(usuario, t["area"], mias, regiones, palabras)
    return {"lecturas": _lecturas(usuario, a, [m], propias, excluir_tema=tid), "noticias": noticias,
            "aviso_noticias": aviso}
