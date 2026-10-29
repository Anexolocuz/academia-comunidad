"""API de IA opcional (en la nube): más rápida y, a veces, de mayor calidad que la IA local.

Es OPCIONAL y viene APAGADA. Lo local sigue siendo el camino principal y suficiente. Reglas (docs/PROPOSITO.md §8):

* la clave la pone el administrador (datos/secretos.json, permiso 600) y nunca sale por la API;
* cada persona decide si la usa, para qué grupos de tareas, con qué tope de gasto al mes y si manda sus metas;
* solo sale contenido técnico del estudio: el nombre se quita siempre, y las metas y la situación solo si la persona
  lo permite; lo personal (tutor, apuntes, entregas, tus ideas, cartera y pronósticos) NUNCA se manda;
* se avisa del gasto, hay tope por persona y global, y si la API falla o se acaba el tope la tarea sigue sola en la IA local.

Habla con cualquier servicio compatible con la API de OpenAI (OpenAI, Gemini, OpenRouter, Groq, Together, DeepSeek,
Mistral, xAI, Fireworks, Cerebras…, o uno propio) y con la API de Anthropic.
"""
import json
import re
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime

import base
import config
import red
import secretos

# id → ficha. `tipo`: "openai" (compatible con /chat/completions) o "anthropic". `modelos`: sugerencias (cambian con
# frecuencia: «Ver modelos» pregunta al servicio cuáles hay de verdad). `clave_url`: dónde se crea la clave.
PROVEEDORES = {
    "anthropic": {"nombre": "Anthropic (Claude)", "tipo": "anthropic", "url": "https://api.anthropic.com",
                  "modelos": ["claude-sonnet-5-5", "claude-opus-5-5", "claude-haiku-5-5"],
                  "clave_url": "https://console.anthropic.com/settings/keys"},
    "openai": {"nombre": "OpenAI", "tipo": "openai", "url": "https://api.openai.com/v1", "modelos": [],
               "razonamiento": ["low", "medium", "high"], "clave_url": "https://platform.openai.com/api-keys"},
    # Gemini 3.x: no admite temperature (obsoleto); el esfuerzo de razonamiento se manda como reasoning_effort
    # (low | medium | high; «minimal» no existe en 3.8 Flash; por defecto medium). Precios de lanzamiento de 3.8 Flash
    # (USD por millón: 0,75 entrada / 3,75 salida hasta el 2026-12-31; luego 1,50 / 7,50). Los tokens de razonamiento
    # se cobran como salida.
    "google": {"nombre": "Google Gemini", "tipo": "openai",
               "url": "https://generativelanguage.googleapis.com/v1beta/openai", "modelos": ["gemini-3.8-flash"],
               "razonamiento": ["low", "medium", "high"], "sin_temperatura": True, "precio": (0.75, 3.75),
               "respaldo": "gemini-3.5-flash",     # si el modelo nuevo está saturado o no responde, se prueba este antes de pasar a la IA local
               "clave_url": "https://aistudio.google.com/apikey"},
    "openrouter": {"nombre": "OpenRouter (muchos modelos, una sola clave)", "tipo": "openai",
                   "url": "https://openrouter.ai/api/v1", "modelos": [], "clave_url": "https://openrouter.ai/keys"},
    "groq": {"nombre": "Groq (muy rápido)", "tipo": "openai", "url": "https://api.groq.com/openai/v1", "modelos": [],
             "clave_url": "https://console.groq.com/keys"},
    "cerebras": {"nombre": "Cerebras (muy rápido)", "tipo": "openai", "url": "https://api.cerebras.ai/v1",
                 "modelos": [], "clave_url": "https://cloud.cerebras.ai"},
    "together": {"nombre": "Together AI", "tipo": "openai", "url": "https://api.together.xyz/v1", "modelos": [],
                 "clave_url": "https://api.together.ai/settings/api-keys"},
    "fireworks": {"nombre": "Fireworks AI", "tipo": "openai", "url": "https://api.fireworks.ai/inference/v1",
                  "modelos": [], "clave_url": "https://fireworks.ai/account/api-keys"},
    "deepseek": {"nombre": "DeepSeek (económico)", "tipo": "openai", "url": "https://api.deepseek.com/v1",
                 "modelos": [], "clave_url": "https://platform.deepseek.com/api_keys"},
    "mistral": {"nombre": "Mistral AI", "tipo": "openai", "url": "https://api.mistral.ai/v1", "modelos": [],
                "clave_url": "https://console.mistral.ai/api-keys"},
    "xai": {"nombre": "xAI (Grok)", "tipo": "openai", "url": "https://api.x.ai/v1", "modelos": [],
            "clave_url": "https://console.x.ai"},
    "sambanova": {"nombre": "SambaNova", "tipo": "openai", "url": "https://api.sambanova.ai/v1", "modelos": [],
                  "clave_url": "https://cloud.sambanova.ai/apis"},
    "nvidia": {"nombre": "NVIDIA NIM", "tipo": "openai", "url": "https://integrate.api.nvidia.com/v1", "modelos": [],
               "clave_url": "https://build.nvidia.com"},
    # Ollama Cloud: modelos grandes abiertos alojados por Ollama; misma API que OpenAI, clave en ollama.com/settings/keys
    "ollama": {"nombre": "Ollama Cloud (modelos abiertos grandes)", "tipo": "openai", "url": "https://ollama.com/v1",
               "modelos": ["gpt-oss:120b", "nemotron-3-super", "gemma4:31b"],
               "razonamiento": ["low", "medium", "high"], "respaldo": "nemotron-3-super",   # en la cuenta gratuita solo algunos modelos están incluidos (los demás dan 402)
               "clave_url": "https://ollama.com/settings/keys"},
    "otro": {"nombre": "Otro servicio compatible con OpenAI (pon su dirección)", "tipo": "openai", "url": "",
             "modelos": [], "clave_url": ""},
}

# Precio por millón de tokens (USD) si el administrador no puso el suyo: una ESTIMACIÓN ALTA para que el tope proteja.
PRECIO_DEFECTO = (3.0, 15.0)

# Grupos de tareas que una persona puede mandar a la API. Lo que no está aquí (tutor, apuntes con foto, entregas, tus
# propias ideas y respuestas, cartera y pronósticos de acciones, reportes, lo estudiado fuera) NUNCA sale del equipo.
GRUPOS = {
    "lecciones": {"nombre": "📖 Lecciones con sus fuentes (escribirlas, contrastar fuentes y papers, ruta rápida, reexplicar)",
                  "tipos": {"leccion", "rapida", "reexplicar", "ciencia"}},
    "rutas": {"nombre": "🗺️ Rutas, metas, frontera y mercado",
              "tipos": {"objetivo", "area", "ruta", "frontera", "ramas", "mercado", "paper"}},
    "noticias": {"nombre": "📰 Noticias y síntesis", "tipos": {"noticias", "a_fondo", "sintesis", "lectura", "noticia"}},
    "pruebas": {"nombre": "📝 Pruebas, quizzes y verificación",
                "tipos": {"prueba", "tarea", "chequeo", "verificar", "ideas", "presentacion"}},
}
NUNCA = {"aportada", "tutor", "apunte", "entrega", "corregir", "aporte", "externo", "reporte", "pronostico", "relaciones"}

_candado = threading.Lock()
_perfil_de = None          # servidor.py lo enlaza: usuario → perfil (para quitar el nombre y las metas)
_admin_de = None           # servidor.py lo enlaza: () → cuenta del administrador (a quien se le cargan las tareas comunes)
_enfriar = {}              # (proveedor, modelo) → hasta cuándo no insistir tras un error de clave/cuota
_esquema_ok = {}           # (proveedor, modelo) → «json_schema» | «json_object» | «ninguno» (lo que sí acepta)


def enlazar(perfil_de, admin_de):
    global _perfil_de, _admin_de
    _perfil_de, _admin_de = perfil_de, admin_de


class ErrorNube(Exception):
    pass


# ------------------------------------------------------------------ configuración
def proveedor_actual():
    pid = config.C.get("nube_proveedor") or ""
    p = PROVEEDORES.get(pid)
    if not p:
        return None
    url = (config.C.get("nube_url") or p["url"] or "").rstrip("/")
    return {"id": pid, "nombre": p["nombre"], "tipo": p["tipo"], "url": url,
            "modelo": config.C.get("nube_modelo") or (p["modelos"][0] if p["modelos"] else "")}


def plan_gratuito():
    return config.C.get("nube_plan_gratuito") is not False


def precios():
    if plan_gratuito():
        return (0.0, 0.0), False
    a, b = config.C.get("nube_precio_in"), config.C.get("nube_precio_out")
    try:
        a, b = float(a or 0), float(b or 0)
    except (TypeError, ValueError):
        a = b = 0.0
    if a > 0 and b > 0:
        return (a, b), False
    oficial = (PROVEEDORES.get(config.C.get("nube_proveedor") or "") or {}).get("precio")
    return (oficial, False) if oficial else (PRECIO_DEFECTO, True)


def lista_publica():
    return [{"id": k, **{x: v[x] for x in ("nombre", "tipo", "url", "modelos", "clave_url")},
             "razonamiento": v.get("razonamiento", []), "precio": v.get("precio")}
            for k, v in PROVEEDORES.items()]


def configurada():
    p = proveedor_actual()
    return bool(p and p["url"] and p["modelo"] and secretos.obtener("claves_ia", p["id"]))


def config_admin():
    p = proveedor_actual()
    clave = secretos.obtener("claves_ia", p["id"]) if p else ""
    (pin, pout), estimado = precios()
    return {"activa": bool(config.C.get("nube_activa")), "proveedor": (p or {}).get("id", ""),
            "url": (p or {}).get("url", ""), "modelo": (p or {}).get("modelo", ""),
            "tiene_clave": bool(clave), "pista_clave": secretos.pista(clave),
            "precio_in": pin, "precio_out": pout, "precio_estimado": estimado,
            "tope_global_usd": float(config.C.get("nube_tope_global_usd") or 0), "plan_gratuito": plan_gratuito(),
            "razonamiento": config.C.get("nube_razonamiento") or "", "modelo_respaldo": modelo_respaldo(),
            "proveedor2": config.C.get("nube_proveedor2") or "", "modelo2": config.C.get("nube_modelo2") or "",
            "modelo2_respaldo": config.C.get("nube_modelo2_respaldo") or "",
            "tiene_clave2": bool(secretos.obtener("claves_ia", config.C.get("nube_proveedor2") or "")),
            "reintento_mensual_dias": _dias_mensual(), "pausas": pausas(),
            "configurada": configurada(), "proveedores": lista_publica(),
            "grupos": {k: v["nombre"] for k, v in GRUPOS.items()}}


def guardar_admin(d):
    """Aplica lo que manda el administrador. Devuelve el diccionario público. La clave solo se cambia si viene."""
    c = {}
    if "proveedor" in d:
        pid = str(d["proveedor"] or "")
        if pid and pid not in PROVEEDORES:
            raise ValueError("proveedor desconocido")
        c["nube_proveedor"] = pid
        if pid != config.C.get("nube_proveedor"):       # al cambiar de proveedor, su dirección y modelo propios
            c["nube_url"], c["nube_modelo"] = "", ""
    if "url" in d:
        u = str(d["url"] or "").strip().rstrip("/")
        if u and not re.match(r"^https?://[^\s]+$", u):
            raise ValueError("la dirección debe empezar con http:// o https://")
        c["nube_url"] = u
    if "modelo" in d:
        c["nube_modelo"] = str(d["modelo"] or "").strip()[:120]
    for k, dest in (("precio_in", "nube_precio_in"), ("precio_out", "nube_precio_out"),
                    ("tope_global_usd", "nube_tope_global_usd")):
        if k in d:
            try:
                c[dest] = max(0.0, min(100000.0, float(d[k] or 0)))
            except (TypeError, ValueError):
                raise ValueError(f"{k}: número inválido") from None
    if "modelo_respaldo" in d:
        c["nube_modelo_respaldo"] = str(d["modelo_respaldo"] or "").strip()[:120]
    if "plan_gratuito" in d:
        c["nube_plan_gratuito"] = bool(d["plan_gratuito"])
    if "proveedor2" in d:
        pid2 = str(d["proveedor2"] or "")
        if pid2 and pid2 not in PROVEEDORES:
            raise ValueError("proveedor de reserva desconocido")
        c["nube_proveedor2"] = pid2
        if pid2 != config.C.get("nube_proveedor2"):
            c["nube_modelo2"], c["nube_modelo2_respaldo"], c["nube_url2"] = "", "", ""
    for k, dest in (("modelo2", "nube_modelo2"), ("modelo2_respaldo", "nube_modelo2_respaldo")):
        if k in d:
            c[dest] = str(d[k] or "").strip()[:120]
    if "reintento_mensual_dias" in d:
        try:
            c["nube_reintento_mensual_dias"] = max(1, min(60, int(d["reintento_mensual_dias"] or 15)))
        except (TypeError, ValueError):
            raise ValueError("días: número inválido") from None
    if "razonamiento" in d:
        r = str(d["razonamiento"] or "")
        if r not in ("", "low", "medium", "high"):
            raise ValueError("razonamiento: usa low, medium o high (o vacío)")
        c["nube_razonamiento"] = r
    if "activa" in d:
        c["nube_activa"] = bool(d["activa"])
    if c:
        config.C = config.guardar(c)
    if "clave" in d:
        pid = d.get("proveedor") or config.C.get("nube_proveedor")
        if pid not in PROVEEDORES:
            raise ValueError("elige primero el proveedor")
        k = str(d["clave"] or "").strip()
        if k and not re.match(r"^[\x21-\x7e]{8,400}$", k):
            raise ValueError("la clave tiene caracteres que no son válidos (¿espacios o saltos de línea?)")
        secretos.guardar("claves_ia", k, pid)
        _enfriar.clear()
    if "clave2" in d:
        pid2 = config.C.get("nube_proveedor2") or ""
        k = str(d["clave2"] or "").strip()
        if not pid2:
            raise ValueError("elige primero el proveedor de reserva")
        if k and not re.match(r"^[\x21-\x7e]{8,400}$", k):
            raise ValueError("la clave tiene caracteres que no son válidos (¿espacios o saltos de línea?)")
        if k:
            secretos.guardar("claves_ia", k, pid2)
    return config_admin()


# ------------------------------------------------------------------ preferencias de cada persona
def _por_defecto():
    # Por defecto SOLO las lecciones con sus fuentes (lo que más tarda y menos datos personales lleva); el resto, a mano
    return {"usar": False, "grupos": ["lecciones"], "tope_usd": 5.0, "enviar_metas": False,
            "usar_reserva": True,        # si la principal llega a su límite, pasar a la API de reserva del administrador
            "reintento_dias": 0}         # cada cuántos días reintenta un modelo de límite mensual (0 = lo que fije el administrador)


def ajustes_persona(u):
    a = _por_defecto()
    a.update(base.kv_get(f"nube:{u}") or {})
    a["grupos"] = [g for g in a["grupos"] if g in GRUPOS]
    return a


def guardar_persona(u, d):
    a = ajustes_persona(u)
    if "usar" in d:
        a["usar"] = bool(d["usar"])
    if "grupos" in d:
        a["grupos"] = [g for g in (d["grupos"] or []) if g in GRUPOS]
    if "tope_usd" in d:
        try:
            a["tope_usd"] = max(0.0, min(10000.0, float(d["tope_usd"] or 0)))
        except (TypeError, ValueError):
            raise ValueError("tope: número inválido") from None
    if "enviar_metas" in d:
        a["enviar_metas"] = bool(d["enviar_metas"])
    if "usar_reserva" in d:
        a["usar_reserva"] = bool(d["usar_reserva"])
    if "reintento_dias" in d:
        try:
            a["reintento_dias"] = max(0, min(60, int(d["reintento_dias"] or 0)))
        except (TypeError, ValueError):
            raise ValueError("días: número inválido") from None
    base.kv_set(f"nube:{u}", a)
    return a


# ------------------------------------------------------------------ gasto
def _mes():
    return datetime.now().strftime("%Y-%m")


def uso_mes():
    return base.kv_get(f"nube_uso:{_mes()}") or {"usuarios": {}}


def gastado(u=None):
    uso = uso_mes()
    if u is None:
        return round(sum(x.get("usd", 0) for x in uso["usuarios"].values()), 4)
    return round(uso["usuarios"].get(u, {}).get("usd", 0), 4)


def registrar_uso(u, tin, tout):
    (pin, pout), _ = precios()
    usd = tin / 1e6 * pin + tout / 1e6 * pout
    with _candado:
        uso = uso_mes()
        x = uso["usuarios"].setdefault(u, {"in": 0, "out": 0, "usd": 0.0, "n": 0})
        x["in"] += tin
        x["out"] += tout
        x["usd"] = round(x["usd"] + usd, 6)
        x["n"] += 1
        base.kv_set(f"nube_uso:{_mes()}", uso)
    return usd


def resumen_persona(u):
    a = ajustes_persona(u)
    g = float(config.C.get("nube_tope_global_usd") or 0)
    return {**a, "gastado_usd": gastado(u), "gastado_global_usd": gastado(), "tope_global_usd": g,
            "mes": _mes(), "plan_gratuito": plan_gratuito(), "tokens": uso_mes()["usuarios"].get(u, {}).get("in", 0) + uso_mes()["usuarios"].get(u, {}).get("out", 0),
            "llamadas": uso_mes()["usuarios"].get(u, {}).get("n", 0),
            "disponible": bool(config.C.get("nube_activa")) and configurada()}


# ------------------------------------------------------------------ ¿esta tarea va a la nube?
def _dueno(usuario):
    """Las tareas comunes (noticias del día) se cargan a la cuenta del administrador."""
    return usuario or (_admin_de() if _admin_de else None)


def grupo_de(tipo, etiqueta=""):
    """El grupo de tareas al que pertenece (o None). Contrastar las fuentes de una lección (`verificar` con etiqueta
    «tema:…») es parte de preparar la lección; verificar un texto pegado por la persona no."""
    if tipo == "verificar" and str(etiqueta).startswith("tema:"):
        return "lecciones"
    return next((g for g, v in GRUPOS.items() if tipo in v["tipos"]), None)


def aplicable(tipo, usuario, etiqueta=""):
    """(dueño, None) si la tarea puede usar la API; (None, motivo) si no."""
    if not config.C.get("nube_activa") or not configurada():
        return None, "la API no está activada"
    if tipo in NUNCA:
        return None, "esta tarea usa datos personales y siempre se queda en tu equipo"
    grupo = grupo_de(tipo, etiqueta)
    if not grupo:
        return None, "este tipo de tarea no sale del equipo"
    dueno = _dueno(usuario)
    if not dueno:
        return None, "sin cuenta a quien cargar el gasto"
    a = ajustes_persona(dueno)
    if not a["usar"] or grupo not in a["grupos"]:
        return None, "esa persona no la usa para este grupo"
    if not plan_gratuito():          # en el plan gratuito no hay gasto: el límite lo pone el proveedor (429) y se pasa a lo local
        if a["tope_usd"] <= 0 or gastado(dueno) >= a["tope_usd"]:
            return None, "se llegó a su tope mensual"
        tg = float(config.C.get("nube_tope_global_usd") or 0)
        if tg <= 0 or gastado() >= tg:
            return None, "se llegó al tope mensual global"
    if not libres(dueno):
        return None, "la API falló o llegó a su límite; se reintenta más tarde"
    return dueno, None


def sana():
    """¿La API responde ahora? (activada, con clave y algún modelo de la cadena sin pausa por límite o fallo)"""
    return bool(config.C.get("nube_activa") and configurada() and libres())


# ------------------------------------------------------------------ privacidad
MARCA_I, MARCA_F = "[[PERFIL]]", "[[/PERFIL]]"
_RE_PERFIL = re.compile(re.escape(MARCA_I) + r".*?" + re.escape(MARCA_F), re.S)


def sin_marcas(mensajes):
    """Para la IA local: el perfil completo, sin las marcas."""
    out = []
    for m in mensajes:
        c = m.get("content")
        if isinstance(c, str) and MARCA_I in c:
            m = {**m, "content": c.replace(MARCA_I, "").replace(MARCA_F, "")}
        out.append(m)
    return out


def limpiar(mensajes, usuario):
    """Para la API: el perfil se cambia por una versión mínima (sin nombre; con metas solo si la persona lo permitió)
    y cualquier otra aparición del nombre se borra."""
    a = ajustes_persona(usuario)
    p = (_perfil_de(usuario) if _perfil_de else {}) or {}
    minimo = "Estudiante anónimo."
    if a["enviar_metas"]:
        trozos = [f"{k}: {p[c]}" for k, c in (("Situación", "situacion"), ("Metas", "metas"), ("Prefiere", "estilo"))
                  if p.get(c)]
        if trozos:
            minimo = "Estudiante anónimo. " + " ".join(trozos)
    nombre = (p.get("nombre") or "").strip()
    out = []
    for m in mensajes:
        c = m.get("content")
        if isinstance(c, list):                       # contenido con imágenes: no sale (no debería llegar aquí)
            c = " ".join(x.get("text", "") for x in c if isinstance(x, dict) and x.get("type") == "text")
        if isinstance(c, str):
            c = _RE_PERFIL.sub(minimo, c)
            if len(nombre) >= 3:
                c = re.sub(re.escape(nombre), "el estudiante", c, flags=re.I)
        out.append({**m, "content": c})
    return out


# ------------------------------------------------------------------ llamadas
def _cabeceras(p, clave):
    if p["tipo"] == "anthropic":
        return {"x-api-key": clave, "anthropic-version": "2023-06-01", "Content-Type": "application/json"}
    return {"Authorization": f"Bearer {clave}", "Content-Type": "application/json"}


def _error_http(e):
    try:
        cuerpo = e.read().decode("utf-8", "ignore")[:600]
    except Exception:
        cuerpo = ""
    for k in (secretos.obtener("claves_ia") or {}).values():      # un servicio puede repetir la clave en su error
        if k:
            cuerpo = cuerpo.replace(k, "***")
    return ErrorNube(f"HTTP {e.code}: {cuerpo}"), e.code, cuerpo.lower()


def _con_esquema(mensajes, esquema):
    instr = ("Responde SOLO con un objeto JSON válido, sin texto antes ni después ni bloques de código, que cumpla "
             "este esquema JSON:\n" + json.dumps(esquema, ensure_ascii=False))
    if mensajes and mensajes[0].get("role") == "system":
        return [{**mensajes[0], "content": mensajes[0]["content"] + "\n\n" + instr}] + mensajes[1:]
    return [{"role": "system", "content": instr}] + mensajes


# Espera máxima entre dos trozos de la respuesta. Con razonamiento alto el primer trozo puede tardar un par de minutos; si el
# servicio se cuelga más que eso, la tarea sigue en la IA local en vez de esperar 15 minutos.
TIEMPO_LECTURA_S = 240
ESPERAS_TRANSITORIAS = (3, 10, 30)     # segundos entre reintentos cuando el servicio está saturado (500, 502, 503, 504)


def modelo_respaldo():
    p = proveedor_actual() or {}
    r = config.C.get("nube_modelo_respaldo") or (PROVEEDORES.get(p.get("id")) or {}).get("respaldo") or ""
    return r if r and r != p.get("modelo") else ""


_caido = {}               # (proveedor, modelo) → hasta cuándo no se intenta (falló, no contestó o llegó a su límite)
PAUSA_MODELO_S = 600
PAUSA_LIMITE_S = 900
PAUSA_DIARIA_S = 3 * 3600
PAUSA_CLAVE_S = 3600
_pausas_cargadas = []


def _es_limite(e):
    t = str(e).lower()
    return getattr(e, "code", 0) == 429 or any(x in t for x in ("quota", "rate limit", "resource_exhausted", "exceeded"))


def _dias_mensual():
    try:
        return max(1, min(60, int(config.C.get("nube_reintento_mensual_dias") or 15)))
    except (TypeError, ValueError):
        return 15


def duracion_limite(e):
    """Cuánto descansa un modelo que llegó a su límite: mensual (o falta de créditos, 402) → cada
    `nube_reintento_mensual_dias` (15) días; diario → 3 h; si el mensaje no dice el periodo → 15 min.
    Ojo: «billing details» aparece en los avisos de cuota diaria de Google, así que no cuenta como mensual."""
    t = str(e).lower()
    plano = re.sub(r"[\s_-]+", "", t)
    if getattr(e, "code", 0) == 402 or any(x in t for x in ("monthly", "mensual", "per month", "usage credits")):
        return _dias_mensual() * 86400
    if any(x in plano for x in ("perday", "daily", "resourceexhausted", "requestsperday", "tokensperday")) or "per day" in t:
        return PAUSA_DIARIA_S
    return PAUSA_LIMITE_S


_mensual = {}             # (proveedor, modelo) → cuándo se supo que su límite era mensual (cada persona fija cada cuántos días reintenta)


def _pausar(pid, modelo, segundos, mensual=False):
    """Deja de intentar ese modelo un tiempo. Las pausas de una hora o más se guardan: sobreviven a un reinicio."""
    _caido[(pid, modelo)] = time.time() + segundos
    if mensual:
        _mensual[(pid, modelo)] = time.time()
    else:
        _mensual.pop((pid, modelo), None)
    if segundos >= 3600:
        try:
            g = base.kv_get("nube_pausas") or {}
            g[f"{pid}|{modelo}"] = [_caido[(pid, modelo)], _mensual.get((pid, modelo), 0)]
            base.kv_set("nube_pausas", {k: v for k, v in g.items() if v[0] > time.time()})
        except Exception:  # noqa: BLE001
            pass


def _hasta(pid, modelo, dueno=None):
    """Hasta cuándo no se intenta ese modelo. Si el límite es mensual, cada persona reintenta con su propia cadencia."""
    if not _pausas_cargadas:
        _pausas_cargadas.append(1)
        try:
            for k, v in (base.kv_get("nube_pausas") or {}).items():
                a, _, b = k.partition("|")
                _caido[(a, b)] = max(_caido.get((a, b), 0), v[0])
                if v[1]:
                    _mensual[(a, b)] = v[1]
        except Exception:  # noqa: BLE001
            pass
    h = _caido.get((pid, modelo), 0)
    desde = _mensual.get((pid, modelo))
    if desde and dueno:
        dias = ajustes_persona(dueno).get("reintento_dias")
        if dias:
            h = desde + dias * 86400
    return h


def reanudar():
    """Quita todas las pausas por límite o fallo (botón «Reintentar ahora» del administrador)."""
    _caido.clear()
    _mensual.clear()
    base.kv_set("nube_pausas", {})
    return {"ok": True}


def pausas():
    """[{proveedor, modelo, hasta}] de lo que está en pausa ahora (para mostrarlo al administrador)."""
    ahora = time.time()
    _hasta("", "")
    return [{"proveedor": a, "modelo": b, "hasta": v, "mensual": (a, b) in _mensual}
            for (a, b), v in sorted(_caido.items()) if v > ahora]


def candidatos():
    """Cadena de intentos, en orden: modelo principal y de respaldo del proveedor principal y, si se configuró, los del
    proveedor de reserva (`nube_proveedor2`). Solo proveedores con clave."""
    out = []
    p = proveedor_actual()
    if p and p["url"]:
        out += [({**p, "modelo": m}) for m in (p["modelo"], modelo_respaldo()) if m]
    pid2 = config.C.get("nube_proveedor2") or ""
    f2 = PROVEEDORES.get(pid2)
    if f2 and pid2 != (p or {}).get("id") and secretos.obtener("claves_ia", pid2):
        url2 = (config.C.get("nube_url2") or f2["url"] or "").rstrip("/")
        m2 = config.C.get("nube_modelo2") or (f2["modelos"][0] if f2["modelos"] else "")
        r2 = config.C.get("nube_modelo2_respaldo") or f2.get("respaldo") or ""
        out += [{"id": pid2, "nombre": f2["nombre"], "tipo": f2["tipo"], "url": url2, "modelo": m, "reserva": True}
                for m in (m2, r2 if r2 != m2 else "") if m and url2]
    return [c for c in out if secretos.obtener("claves_ia", c["id"])]


def libres(dueno=None):
    """Candidatos sin pausa. Con `dueno`, aplica sus ajustes: si no quiere la API de reserva, esa no entra."""
    ahora = time.time()
    reserva = ajustes_persona(dueno)["usar_reserva"] if dueno else True
    return [c for c in candidatos() if (reserva or not c.get("reserva")) and _hasta(c["id"], c["modelo"], dueno) < ahora]


def chat(ctx, mensajes, max_tokens, temperatura, esquema, mostrar, semilla, dueno):
    """Una respuesta de la API, en streaming. Devuelve (texto, tokens_entrada, tokens_salida).

    Cadena de intentos (`candidatos`): modelo principal, su respaldo y, si hay, el proveedor de reserva. Con
    500/502/503/504 («alta demanda») reintenta con pausas; si un modelo no contesta en `TIEMPO_LECTURA_S` o llegó a su
    límite (429, cuota o créditos) pasa directo al siguiente y ese descansa: 15 min, 3 h si el límite es diario, o
    `nube_reintento_mensual_dias` días si es mensual (se guarda: sobrevive a reinicios). Si todos fallan lanza el error y
    la tarea sigue sola en la IA local (nube.intentar)."""
    cadena = libres(dueno)
    if not cadena:
        raise ErrorNube("todos los modelos de la API están en pausa por su límite o un fallo")
    ultimo = None
    for i, p in enumerate(cadena):
        m = p["modelo"]
        for espera in (*ESPERAS_TRANSITORIAS, None):
            try:
                if i:
                    ctx.fase((getattr(ctx.t, "fase", "") or "").split(" · ☁️")[0] + f" · ☁️ {p['nombre'].split(' (')[0]} · {m}")
                return _chat_una_vez(ctx, p, mensajes, max_tokens, temperatura, esquema, mostrar, semilla, dueno)
            except ErrorNube as e:
                ultimo = e
                code = getattr(e, "code", 0)
                if _es_limite(e) or code == 402:
                    _pausar(p["id"], m, duracion_limite(e), mensual=duracion_limite(e) >= 86400)
                    break
                if code in (401, 403):
                    _pausar(p["id"], m, PAUSA_CLAVE_S)
                    break
                if espera is None or code not in (500, 502, 503, 504):
                    if code in (500, 502, 503, 504):
                        _pausar(p["id"], m, PAUSA_MODELO_S)
                    break
                time.sleep(espera)
            except (TimeoutError, OSError) as e:        # no contestó (colgado): no se insiste con el mismo, cuesta minutos
                ultimo = ErrorNube(f"sin respuesta de {m}: {e}")
                _pausar(p["id"], m, PAUSA_MODELO_S)
                break
    raise ultimo


def _chat_una_vez(ctx, p, mensajes, max_tokens, temperatura, esquema, mostrar, semilla, dueno):
    clave = secretos.obtener("claves_ia", p["id"])
    mensajes = limpiar(mensajes, dueno)
    clave_es = (p["id"], p["modelo"])
    modo = _esquema_ok.get(clave_es, "json_schema") if esquema else "ninguno"
    ficha = PROVEEDORES.get(p["id"]) or {}
    esfuerzo = (config.C.get("nube_razonamiento") or "") if esfuerzo_ok(ficha) else ""
    opciones = {"temperatura": not ficha.get("sin_temperatura"), "semilla": semilla is not None,
                "stream_options": True, "max_completion": False, "razonamiento": esfuerzo}
    if p["tipo"] == "anthropic":
        modo = "ninguno"
    if opciones["razonamiento"]:    # los tokens de razonamiento salen del mismo tope: se amplía para no cortar la respuesta
        max_tokens = min(64000, max_tokens + {"low": 2000, "medium": 6000, "high": 12000}[opciones["razonamiento"]])
    for _ in range(6):
        msgs = _con_esquema(mensajes, esquema) if esquema and modo != "json_schema" else mensajes
        try:
            if p["tipo"] == "anthropic":
                return _anthropic(ctx, p, clave, msgs, max_tokens, temperatura, mostrar, opciones)
            r = _openai(ctx, p, clave, msgs, max_tokens, temperatura, esquema, mostrar, semilla, modo, opciones)
            if esquema:
                _esquema_ok[clave_es] = modo
            return r
        except _Reajustar as e:      # el servicio rechazó un parámetro: se quita y se reintenta
            if e.que == "esquema":
                modo = {"json_schema": "json_object", "json_object": "ninguno"}.get(modo)
                if modo is None:
                    raise ErrorNube(e.detalle) from None
            else:
                opciones[e.que] = e.valor
    raise ErrorNube("el servicio rechazó los parámetros varias veces")


def esfuerzo_ok(ficha):
    return bool(ficha.get("razonamiento")) and ficha.get("tipo", "openai") == "openai"


class _Reajustar(Exception):
    def __init__(self, que, valor, detalle):
        super().__init__(detalle)
        self.que, self.valor, self.detalle = que, valor, detalle


def _interpretar_400(code, cuerpo, esquema_en_uso):
    if code not in (400, 422):
        return None
    if "stream_options" in cuerpo or "include_usage" in cuerpo:
        return _Reajustar("stream_options", False, cuerpo)
    if "max_completion_tokens" in cuerpo:
        return _Reajustar("max_completion", True, cuerpo)
    if "temperature" in cuerpo:
        return _Reajustar("temperatura", False, cuerpo)
    if "reasoning_effort" in cuerpo or "thinking" in cuerpo:
        return _Reajustar("razonamiento", "", cuerpo)
    if "seed" in cuerpo:
        return _Reajustar("semilla", False, cuerpo)
    if esquema_en_uso and any(x in cuerpo for x in ("response_format", "json_schema", "schema", "json_object", "structured")):
        return _Reajustar("esquema", None, cuerpo)
    return None


def _estimar(msgs, texto):
    return int(sum(len(str(m.get("content") or "")) for m in msgs) / 3.5), int(len(texto) / 3.5)


def _openai(ctx, p, clave, msgs, max_tokens, temperatura, esquema, mostrar, semilla, modo, op):
    cuerpo = {"model": p["modelo"], "messages": msgs, "stream": True}
    cuerpo["max_completion_tokens" if op["max_completion"] else "max_tokens"] = max_tokens
    if op["temperatura"]:
        cuerpo["temperature"] = temperatura
    if op["semilla"] and semilla is not None:
        cuerpo["seed"] = semilla
    if op.get("razonamiento"):
        cuerpo["reasoning_effort"] = op["razonamiento"]
    if op["stream_options"]:
        cuerpo["stream_options"] = {"include_usage": True}
    if esquema and modo == "json_schema":
        cuerpo["response_format"] = {"type": "json_schema", "json_schema": {"name": "salida", "schema": esquema}}
    elif esquema and modo == "json_object":
        cuerpo["response_format"] = {"type": "json_object"}
    req = urllib.request.Request(p["url"] + "/chat/completions", data=json.dumps(cuerpo).encode(),
                                 headers=_cabeceras(p, clave))
    salida, tin, tout = [], 0, 0
    if mostrar:
        ctx.t.texto = ""
    try:
        with red.abrir(req, timeout=TIEMPO_LECTURA_S) as r:
            for linea in r:
                linea = linea.strip()
                if not linea.startswith(b"data:"):
                    continue
                dato = linea[5:].strip()
                if dato == b"[DONE]":
                    break
                try:
                    j = json.loads(dato)
                except ValueError:
                    continue
                if j.get("usage"):
                    tin, tout = j["usage"].get("prompt_tokens", 0), j["usage"].get("completion_tokens", 0)
                for ch in j.get("choices") or []:
                    trozo = (ch.get("delta") or {}).get("content") or ""
                    if trozo:
                        salida.append(trozo)
                        if mostrar:
                            ctx.t.texto += trozo
    except urllib.error.HTTPError as e:
        err, code, cuerpo_t = _error_http(e)
        ajuste = _interpretar_400(code, cuerpo_t, bool(esquema) and modo != "ninguno")
        if ajuste:
            raise ajuste from None
        err.code = code
        raise err from None
    texto = "".join(salida).strip()
    if not tin:
        tin, tout = _estimar(msgs, texto)
    return texto, tin, tout


def _anthropic(ctx, p, clave, msgs, max_tokens, temperatura, mostrar, op):
    sistema = "\n\n".join(m["content"] for m in msgs if m.get("role") == "system" and isinstance(m.get("content"), str))
    conv = [{"role": m["role"], "content": m["content"]} for m in msgs
            if m.get("role") in ("user", "assistant") and m.get("content")]
    cuerpo = {"model": p["modelo"], "max_tokens": max_tokens, "messages": conv, "stream": True}
    if sistema:
        cuerpo["system"] = sistema
    if op["temperatura"]:
        cuerpo["temperature"] = min(1.0, temperatura)
    req = urllib.request.Request(p["url"] + "/v1/messages", data=json.dumps(cuerpo).encode(),
                                 headers=_cabeceras(p, clave))
    salida, tin, tout = [], 0, 0
    if mostrar:
        ctx.t.texto = ""
    try:
        with red.abrir(req, timeout=TIEMPO_LECTURA_S) as r:
            for linea in r:
                linea = linea.strip()
                if not linea.startswith(b"data:"):
                    continue
                try:
                    j = json.loads(linea[5:].strip())
                except ValueError:
                    continue
                t = j.get("type")
                if t == "content_block_delta":
                    trozo = (j.get("delta") or {}).get("text") or ""
                    if trozo:
                        salida.append(trozo)
                        if mostrar:
                            ctx.t.texto += trozo
                elif t == "message_start":
                    tin = ((j.get("message") or {}).get("usage") or {}).get("input_tokens", 0)
                elif t == "message_delta":
                    tout = (j.get("usage") or {}).get("output_tokens", tout)
                elif t == "error":
                    raise ErrorNube(str((j.get("error") or {}).get("message") or j)[:300])
    except urllib.error.HTTPError as e:
        err, code, cuerpo_t = _error_http(e)
        if code in (400, 422) and "temperature" in cuerpo_t:
            raise _Reajustar("temperatura", False, cuerpo_t) from None
        err.code = code
        raise err from None
    texto = "".join(salida).strip()
    if not tin:
        tin, tout = _estimar(msgs, texto)
    return texto, tin, tout


def intentar(ctx, mensajes, max_tokens, temperatura, esquema, mostrar, semilla):
    """Lo llama Contexto._chat. Devuelve (True, resultado) si la API respondió, o (False, motivo) si hay que seguir en
    la IA local (no aplica, falló, se acabó el tope…). Nunca lanza."""
    t = ctx.t
    dueno, motivo = aplicable(t.tipo, t.usuario, t.etiqueta)
    if not dueno:
        return False, motivo
    p = proveedor_actual()
    try:
        ctx.fase((t.fase or "").split(" · ☁️")[0] + f" · ☁️ {p['nombre'].split(' (')[0]}")
        texto, tin, tout = chat(ctx, mensajes, max_tokens, temperatura, esquema, mostrar, semilla, dueno)
    except Exception as e:  # noqa: BLE001 — cualquier fallo de la API: se sigue en local, sin perder la tarea
        limite = _es_limite(e) or getattr(e, "code", 0) == 402
        ctx.fase((t.fase or "").split(" · ☁️")[0]
                 + (" · (la API llegó a su límite: sigo en la IA local)" if limite else " · (la API falló: sigo en la IA local)"))
        base.kv_set("nube_ultimo_error", {"cuando": time.time(), "mensaje": str(e)[:300]})
        return False, str(e)
    registrar_uso(dueno, tin, tout)
    t.pedidos = getattr(t, "pedidos", 0) + 1       # si luego hay que seguir en local, se pausa en vez de reiniciar la tarea
    if esquema:
        import ia
        try:
            r = ia.parsear_json(texto)
        except ValueError:
            r = None
        if not _cumple(r, esquema):
            # Algunos servicios (p. ej. Ollama Cloud) aceptan «response_format» pero no lo aplican: el JSON llega con otras
            # claves. Se recuerda para ese modelo y se reintenta una vez con el esquema escrito dentro del prompt.
            _esquema_ok[(p["id"], p["modelo"])] = "json_object"
            try:
                texto, tin, tout = chat(ctx, mensajes, max_tokens, temperatura, esquema, mostrar, semilla, dueno)
                registrar_uso(dueno, tin, tout)
                r = ia.parsear_json(texto)
            except Exception as e:  # noqa: BLE001
                raise ValueError(f"la API no devolvió el JSON pedido: {str(e)[:120]}") from None
            if not _cumple(r, esquema):
                raise ValueError("la API no devolvió las claves del esquema")   # Contexto.chat lo reintenta
        return True, r
    return True, texto


def _cumple(valor, esquema):
    """¿El JSON trae las claves obligatorias y los tipos básicos del esquema (también dentro de listas y objetos)?"""
    t = esquema.get("type")
    if t == "object":
        if not isinstance(valor, dict):
            return False
        if any(k not in valor for k in esquema.get("required", [])):
            return False
        return all(_cumple(valor[k], sub) for k, sub in esquema.get("properties", {}).items() if k in valor)
    if t == "array":
        return isinstance(valor, list) and all(_cumple(v, esquema.get("items", {})) for v in valor)
    if t == "string":
        return isinstance(valor, str)
    return True


def listar_modelos():
    p = proveedor_actual()
    if not p:
        raise ErrorNube("elige un proveedor")
    clave = secretos.obtener("claves_ia", p["id"])
    if not clave:
        raise ErrorNube("pon primero la clave")
    url = p["url"] + ("/v1/models?limit=100" if p["tipo"] == "anthropic" else "/models")
    req = urllib.request.Request(url, headers=_cabeceras(p, clave))
    try:
        with red.abrir(req, timeout=20) as r:
            j = json.loads(r.read())
    except urllib.error.HTTPError as e:
        raise _error_http(e)[0] from None
    ids = [(m.get("id") or m.get("name") or "").removeprefix("models/") for m in (j.get("data") or j.get("models") or [])]
    return sorted(i for i in ids if i)           # Gemini los devuelve como «models/<id>»; la API de chat espera solo <id>


def probar(usuario):
    """Una pregunta mínima para comprobar clave, dirección y modelo; devuelve latencia, tokens y costo."""
    p = proveedor_actual()
    if not p or not p["modelo"]:
        raise ErrorNube("elige proveedor y modelo")
    if not secretos.obtener("claves_ia", p["id"]):
        raise ErrorNube("pon la clave")

    class _Falso:                       # no hay tarea real: solo se necesita .t.texto y .fase()
        class t:
            texto = ""
            fase = ""

        @staticmethod
        def fase(texto):
            pass
    t0 = time.time()
    texto, tin, tout = chat(_Falso, [{"role": "user", "content": "Responde solo con la palabra: listo"}], 30, 0, None,
                            False, None, usuario)
    (pin, pout), _ = precios()
    return {"respuesta": texto[:80], "segundos": round(time.time() - t0, 1), "tokens_in": tin, "tokens_out": tout,
            "usd": round(tin / 1e6 * pin + tout / 1e6 * pout, 6)}
