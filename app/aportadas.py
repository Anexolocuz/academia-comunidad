"""Fuentes aportadas por la persona: el texto de una página que bloquea a las IA (o de un PDF, un libro, un apunte de
clase) que ella misma abre, copia con el modo lector y pega en la lección.

Qué se hace con él:
* se guarda por persona y por tema (máximo 30; 40.000 caracteres cada una);
* se analiza en el equipo: resumen, afirmaciones clave, referencias que cita y contraste de esas afirmaciones con
  fuentes externas verificadas (el mismo contraste de `verificacion.py`);
* cuando se escribe o reescribe la lección de ese tema, entra como fuente de partida (la primera, marcada con 📎).

El análisis nunca sale a la API en la nube (el tipo «aportada» no pertenece a ningún grupo); solo la lección, si la persona
permitió ese grupo, recibe un extracto del texto como cualquier otra fuente.
"""
import hashlib
import re
import time
import urllib.parse

import base
import verificacion as vf

MAX_POR_PERSONA = 30
MAX_CARACTERES = 40000
MIN_CARACTERES = 200
ESQUEMA = {"type": "object", "properties": {
    "resumen": {"type": "string"},
    "afirmaciones": {"type": "array", "minItems": 3, "maxItems": 12, "items": {"type": "string"}},
    "referencias": {"type": "array", "maxItems": 20, "items": {"type": "string"}},
    "consultas": {"type": "array", "minItems": 2, "maxItems": 4, "items": {"type": "string"}},
    "consultas_en": {"type": "array", "minItems": 2, "maxItems": 4, "items": {"type": "string"}}},
    "required": ["resumen", "afirmaciones", "referencias", "consultas", "consultas_en"]}
_RE_ENLACE = re.compile(r"https?://[^\s)\]>\"']+|\b10\.\d{4,9}/[^\s)\]>\"']+")


def _clave(usuario):
    return f"aportadas:{usuario}"


def lista(usuario, tema=None):
    out = base.kv_get(_clave(usuario)) or []
    return [x for x in out if tema is None or x["tema"] == tema]


def publico(x):
    return {k: x[k] for k in ("id", "tema", "titulo", "url", "creado")} | {"caracteres": len(x["texto"])}


def guardar(usuario, tema, titulo, url, texto):
    texto = re.sub(r"\n{3,}", "\n\n", str(texto or "").replace("\r", "")).strip()
    if len(texto) < MIN_CARACTERES:
        raise ValueError(f"el texto es muy corto (al menos {MIN_CARACTERES} caracteres): pega el artículo completo")
    url = str(url or "").strip()
    if url and urllib.parse.urlparse(url).scheme not in ("http", "https"):
        raise ValueError("la dirección debe empezar con http:// o https://")
    titulo = str(titulo or "").strip()[:160] or (urllib.parse.urlparse(url).hostname or "Texto aportado")
    todas = base.kv_get(_clave(usuario)) or []
    ident = hashlib.sha1(f"{tema}|{titulo}|{texto[:200]}".encode(), usedforsecurity=False).hexdigest()[:12]
    todas = [x for x in todas if x["id"] != ident]
    todas.append({"id": ident, "tema": str(tema or "")[:120], "titulo": titulo, "url": url,
                  "texto": texto[:MAX_CARACTERES], "creado": time.time()})
    base.kv_set(_clave(usuario), todas[-MAX_POR_PERSONA:])
    return ident


def borrar(usuario, ident):
    todas = base.kv_get(_clave(usuario)) or []
    base.kv_set(_clave(usuario), [x for x in todas if x["id"] != ident])


def obtener(usuario, ident):
    return next((x for x in lista(usuario) if x["id"] == ident), None)


def fuentes_de(usuario, tema):
    """Como las demás fuentes de una lección (`titulo`, `url`, `texto`, `fiabilidad`), para entrar primero en el prompt."""
    out = []
    for x in lista(usuario, tema):
        f = vf.fiabilidad(x["url"]) if x["url"] else {"nivel": 2, "tipo": "aportada por ti", "dominio": ""}
        out.append({"titulo": "📎 " + x["titulo"], "url": x["url"] or "#aportada", "texto": x["texto"][:3000],
                    "fiabilidad": f, "clase": "web", "aportada": True})
    return out


def analizar(ctx, usuario, ident):
    from lecciones import SISTEMA_BASE
    x = obtener(usuario, ident)
    if not x:
        raise ValueError("esa fuente ya no existe")
    ctx.fase("Leyendo el texto aportado")
    r = ctx.chat([{"role": "system", "content": SISTEMA_BASE}, {"role": "user", "content": (
        f"El estudiante te pasa el texto de una página «{x['titulo']}». Devuelve JSON compacto:\n"
        "- resumen: 120-180 palabras, fiel al texto (no añadas nada que el texto no diga).\n"
        "- afirmaciones: las 3-12 afirmaciones verificables más importantes (hechos, cifras, fechas, definiciones, "
        "atribuciones), cada una autocontenida y tal como la sostiene el texto.\n"
        "- referencias: las fuentes que el texto cita (autores, título, año, enlace), copiadas tal cual; [] si no cita.\n"
        "- consultas / consultas_en: 2-4 búsquedas cortas (2-6 palabras) en español y en inglés para encontrar fuentes "
        f"que respalden o contradigan esas afirmaciones.\n\nTEXTO:\n{x['texto'][:16000]}")}],
        max_tokens=2500, temperatura=0.2, esquema=ESQUEMA, mostrar=False)
    enlaces = list(dict.fromkeys(_RE_ENLACE.findall(x["texto"])))[:30]
    ctx.fase("Buscando fuentes para contrastarlo")
    fs = vf.buscar_fuentes(r["consultas"], r["consultas_en"], n=10, excluir=(x["url"],) if x["url"] else ())
    res = vf.comparar(ctx, r["afirmaciones"], fs, f"Texto aportado por el estudiante: «{x['titulo']}».")
    res["aportada"] = {"id": ident, "titulo": x["titulo"], "url": x["url"], "resumen": r["resumen"],
                       "referencias": r["referencias"], "enlaces": enlaces}
    return vf._guardar(usuario, f"aportada:{ident}", x["titulo"], res)
