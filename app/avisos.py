"""Avisos opcionales: un recordatorio corto de «tu sesión de hoy» al celular de cada persona.

Todo APAGADO por defecto y por persona: nadie recibe nada hasta que él mismo lo configure en Ajustes.
Canales (sin cuentas ni pagos):

* Telegram: el administrador crea un bot una vez (@BotFather) y cada persona lo vincula enviándole un código;
* ntfy: una app gratuita (iPhone y Android); basta un nombre de «tema» largo y secreto, sin número ni cuenta;
* webhook: una dirección propia (Home Assistant, Zapier, un puente a WhatsApp, etc.) que recibe el texto en JSON.

WhatsApp no tiene una puerta gratuita y oficial para esto: se puede llegar con un webhook hacia un puente que cada
persona elija, pero la Academia no manda nada a WhatsApp por sí sola.

Qué sale: solo cantidades («12 tarjetas por repasar, 1 lección») y, si la persona lo activa, el título de lo siguiente.
Nunca el contenido de lo que estudia, su perfil ni su progreso.
"""
import json
import re
import secrets as _sec
import time
import urllib.error
import urllib.request
from datetime import datetime

import base
import config
import red
import secretos

CANALES = {"telegram": "Telegram", "ntfy": "ntfy (app gratuita)", "webhook": "Dirección propia (webhook)"}
RE_TOKEN = re.compile(r"^\d{5,}:[A-Za-z0-9_-]{30,}$")


def _por_defecto():
    return {"activo": False, "canal": "", "destino": "", "hora": "08:00", "con_titulos": False, "ultimo": ""}


def ajustes(u):
    a = _por_defecto()
    a.update(base.kv_get(f"avisos:{u}") or {})
    return a


def _publica(url):
    import noticias
    return noticias.url_publica(url)


def guardar(u, d):
    a = ajustes(u)
    for k in ("canal", "destino", "hora"):
        if k in d:
            a[k] = str(d[k] or "").strip()
    if "con_titulos" in d:
        a["con_titulos"] = bool(d["con_titulos"])
    if a["canal"] and a["canal"] not in CANALES:
        raise ValueError("canal desconocido")
    if not re.match(r"^([01]?\d|2[0-3]):[0-5]\d$", a["hora"]):
        raise ValueError("hora inválida (usa HH:MM)")
    if a["destino"]:
        if a["canal"] == "telegram" and not re.match(r"^-?\d{3,20}$", a["destino"]):
            raise ValueError("el número de chat de Telegram solo lleva dígitos; usa «Vincular»")
        if a["canal"] == "ntfy" and not re.match(r"^[A-Za-z0-9_-]{8,64}$", a["destino"]):
            raise ValueError("el tema de ntfy: 8-64 letras, números, - o _ (mejor largo y difícil de adivinar)")
        if a["canal"] == "webhook" and not _publica(a["destino"]):
            raise ValueError("la dirección debe ser http(s) y pública (no una de tu casa)")
    if "activo" in d:
        if d["activo"] and not (a["canal"] and a["destino"]):
            raise ValueError("primero elige el canal y completa a dónde llegan los avisos")
        a["activo"] = bool(d["activo"])
    base.kv_set(f"avisos:{u}", a)
    return a


def nuevo_tema_ntfy():
    return "academia-" + _sec.token_urlsafe(12).replace("=", "")


# ------------------------------------------------------------------ administración
def admin_publico():
    tok = secretos.obtener("telegram_token")
    return {"tiene_token": bool(tok), "pista_token": secretos.pista(tok), "bot": _nombre_bot() if tok else "",
            "ntfy_url": config.C.get("ntfy_url") or "https://ntfy.sh", "url_publica": config.C.get("url_publica") or ""}


def guardar_admin(d):
    if "telegram_token" in d:
        t = str(d["telegram_token"] or "").strip()
        if t and not RE_TOKEN.match(t):
            raise ValueError("ese token no tiene la forma de uno de @BotFather (123456:ABC…)")
        secretos.guardar("telegram_token", t)
        _cache_bot.clear()
    c = {}
    if "ntfy_url" in d:
        u = str(d["ntfy_url"] or "").strip().rstrip("/") or "https://ntfy.sh"
        if not re.match(r"^https?://[^\s]+$", u):
            raise ValueError("ntfy: dirección inválida")
        c["ntfy_url"] = u
    if "url_publica" in d:
        u = str(d["url_publica"] or "").strip().rstrip("/")
        if u and not re.match(r"^https?://[^\s]+$", u):
            raise ValueError("la dirección pública debe empezar con http:// o https://")
        c["url_publica"] = u
    if c:
        config.C = config.guardar(c)
    return admin_publico()


# ------------------------------------------------------------------ Telegram
_cache_bot = {}


def _tg(metodo, datos=None, timeout=15):
    tok = secretos.obtener("telegram_token")
    if not tok:
        raise RuntimeError("el administrador aún no conectó un bot de Telegram")
    req = urllib.request.Request(f"https://api.telegram.org/bot{tok}/{metodo}",
                                 data=json.dumps(datos).encode() if datos is not None else None,
                                 headers={"Content-Type": "application/json"})
    try:
        with red.abrir(req, timeout=timeout) as r:
            j = json.loads(r.read())
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"Telegram respondió {e.code}") from None
    if not j.get("ok"):
        raise RuntimeError(str(j.get("description") or "Telegram rechazó la petición")[:200])
    return j["result"]


def _nombre_bot():
    if "n" not in _cache_bot:
        try:
            _cache_bot["n"] = _tg("getMe").get("username", "")
        except Exception:
            return ""
    return _cache_bot["n"]


def codigo_vinculo(u):
    """Código que la persona le escribe al bot para que la Academia sepa cuál es SU chat (y no el de otra)."""
    c = "ACAD-" + _sec.token_hex(3).upper()
    base.kv_set(f"aviso_codigo:{u}", {"codigo": c, "hasta": time.time() + 1800})
    return {"codigo": c, "bot": _nombre_bot()}


def vincular_telegram(u):
    v = base.kv_get(f"aviso_codigo:{u}")
    if not v or v["hasta"] < time.time():
        raise ValueError("el código venció: pide uno nuevo")
    for up in reversed(_tg("getUpdates", {"limit": 100, "timeout": 0})):
        m = up.get("message") or {}
        if v["codigo"] in (m.get("text") or ""):
            chat = str(m["chat"]["id"])
            guardar(u, {"canal": "telegram", "destino": chat})
            base.kv_set(f"aviso_codigo:{u}", None)
            return {"destino": chat}
    raise ValueError(f"No veo tu mensaje. Escríbele a @{_nombre_bot() or 'tu bot'} exactamente «{v['codigo']}» y pulsa de nuevo.")


# ------------------------------------------------------------------ envío
def _enviar_a(a, texto, url=""):
    canal, destino = a["canal"], a["destino"]
    if canal == "telegram":
        _tg("sendMessage", {"chat_id": destino, "text": texto + (f"\n{url}" if url else ""),
                            "disable_web_page_preview": True})
    elif canal == "ntfy":
        cab = {"Title": "Academia", "Tags": "mortar_board"}
        if url:
            cab["Click"] = url
        req = urllib.request.Request(f"{config.C.get('ntfy_url') or 'https://ntfy.sh'}/{destino}",
                                     data=texto.encode("utf-8"), headers=cab)
        red.abrir(req, timeout=15).read()
    elif canal == "webhook":
        import noticias
        if not noticias.url_publica(destino):
            raise RuntimeError("la dirección ya no es pública")
        req = urllib.request.Request(destino, data=json.dumps({"texto": texto, "text": texto, "url": url}).encode(),
                                     headers={"Content-Type": "application/json"})
        noticias._abrir_publica(req, timeout=15).read()
    else:
        raise RuntimeError("canal sin configurar")


def enviar_prueba(u):
    a = ajustes(u)
    if not (a["canal"] and a["destino"]):
        raise ValueError("completa el canal y el destino primero")
    _enviar_a(a, "✅ Prueba de la Academia: así te llegará el recordatorio de tu sesión de hoy.",
              config.C.get("url_publica") or "")
    return {"ok": True}


def texto_aviso(r, con_titulos):
    """r: {minutos, vencidas, nuevas, lecciones, siguiente}"""
    partes = []
    if r.get("vencidas") or r.get("nuevas"):
        partes.append(f"🔁 {r['vencidas'] + r['nuevas']} tarjetas por repasar")
    if r.get("lecciones"):
        partes.append(f"📖 {r['lecciones']} lección{'es' if r['lecciones'] != 1 else ''} para hoy")
    if not partes:
        return ""
    t = f"🎓 Tu sesión de hoy ({r['minutos']} min): " + " · ".join(partes) + "."
    if con_titulos and r.get("siguiente"):
        t += f"\n👉 {r['siguiente']}"
    return t


def enviar_pendientes(resumen_de, personas):
    """Una vez al día, a la hora de cada persona que lo activó y solo si hay algo que hacer. `resumen_de(u)` arma el
    resumen; `personas` son las cuentas con perfil. Un fallo de una persona no detiene a las demás."""
    ahora = datetime.now()
    hoy = ahora.strftime("%Y-%m-%d")
    for u in personas:
        a = ajustes(u)
        if not (a["activo"] and a["canal"] and a["destino"]) or a["ultimo"] == hoy:
            continue
        h, m = (int(x) for x in a["hora"].split(":"))
        if (ahora.hour, ahora.minute) < (h, m):
            continue
        a["ultimo"] = hoy                 # se marca antes: si falla, no se repite cada minuto
        base.kv_set(f"avisos:{u}", a)
        try:
            texto = texto_aviso(resumen_de(u), a["con_titulos"])
            if texto:
                _enviar_a(a, texto, config.C.get("url_publica") or "")
        except Exception as e:  # noqa: BLE001
            base.kv_set(f"aviso_error:{u}", {"cuando": time.time(), "mensaje": str(e)[:200]})
