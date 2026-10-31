#!/usr/bin/env python3
"""Academia — servidor HTTP (solo biblioteca estándar).

Escucha en 127.0.0.1:8092; desde el celular/tablet se entra por
`tailscale serve` (https://<tu-pc>.<tu-tailnet>.ts.net:15443/). Identifica a
cada persona por la cabecera Tailscale-User-Login que pone `serve`; sin esa
cabecera la petición es local (este PC o un agente como Hermes).

Seguridad (ver docs/SEGURIDAD_Y_DATOS.md): solo se confía en peticiones que
llegan desde «redes_locales» (por defecto, este mismo PC); cualquier otro equipo
necesita la «clave_acceso». Las escrituras exigen JSON y mismo origen (contra
CSRF) y el Host debe ser conocido (contra DNS rebinding).
"""
import base64
import gzip
import hashlib
import hmac
import ipaddress
import json
import mimetypes
import os
import re
import subprocess
import sys
import threading
import time
import traceback
import urllib.parse
from datetime import datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import config  # noqa: E402  (antes que todo: decide la carpeta de datos)

for _f in (sys.stdout, sys.stderr):   # Windows: consolas y tuberías sin UTF-8 no pueden imprimir emojis
    try:
        _f.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass
if sys.stdout is None or sys.stderr is None:   # Windows con pythonw: sin consola → a un archivo
    _log = open(config.DATOS / "academia.log", "a", encoding="utf-8", buffering=1)
    sys.stdout = sys.stdout or _log
    sys.stderr = sys.stderr or _log

import base
from base import ejecutar, fila, filas, kv_get, kv_set, registrar

base.iniciar()
import ejecucion as ejc  # noqa: E402
import estados as est  # noqa: E402
import lectura  # noqa: E402
lectura.iniciar()

import curriculo as cur  # noqa: E402  (necesita la base iniciada)
import fsrs  # noqa: E402
import ia  # noqa: E402
import lecciones as lec  # noqa: E402
import noticias as nt  # noqa: E402
import ciencia  # noqa: E402
import mercado  # noqa: E402
import analitica as an  # noqa: E402
import adaptacion as ad  # noqa: E402
import adaptativo as aa  # noqa: E402
import dominio  # noqa: E402
import revision  # noqa: E402
import verificacion as vf  # noqa: E402
import aportadas  # noqa: E402
import escaneo  # noqa: E402
import acciones as ac  # noqa: E402
import avisos  # noqa: E402
import nube  # noqa: E402
import salud  # noqa: E402
import eventos  # noqa: E402
import metricas  # noqa: E402

salud.iniciar_tabla()
metricas.init()   # F1: tablas de eventos y métricas
ia.ganchos.update(poner=salud.anotar, fin=salud.cerrar)   # diario de la cola: lo pendiente sobrevive a un reinicio

RAIZ = Path(__file__).resolve().parent.parent
WEB = RAIZ / "web"
CUADERNO = base.DATOS / "cuaderno"
CUADERNO.mkdir(exist_ok=True)
import config  # noqa: E402
HOST = config.C["host"]
PUERTO = int(config.C["puerto"])
SERVICIOS_PORTAL = RAIZ.parent / "portal" / "servicios.json"
CONFIG = RAIZ / "config" / "academia.json"


def ajustes():
    return config.C


def permitidos():
    """Cuentas de Tailscale que pueden entrar. None en la configuración = las
    del portal personal (../portal/servicios.json, si existe); lista vacía = cualquiera del tailnet."""
    a = config.C.get("usuarios_permitidos")
    if a is not None:
        return a
    try:
        return json.loads(SERVICIOS_PORTAL.read_text(encoding="utf-8")).get("usuarios_permitidos", [])
    except (OSError, ValueError):
        return []


PERFIL_BASE = {   # perfil en blanco: cada persona elige sus áreas y metas en Ajustes
    "nombre": "", "situacion": "", "metas": "", "estilo": "",
    "pesos": {},
    "nuevos_dia": 2, "tarjetas_nuevas_dia": 25, "minutos_dia": 60, "solo_lapiz": False,   # sin lápiz (iPhone): el dedo dibuja
    "dia_maxima": False,   # True = la rutina diaria deja TODAS las lecciones del día listas a máxima profundidad
    "configurado": False,
}


def perfil_de(usuario):
    r = fila("SELECT datos FROM perfil WHERE usuario=?", (usuario,))
    p = dict(PERFIL_BASE)
    p["pesos"] = dict(PERFIL_BASE["pesos"])
    if r:
        d = json.loads(r["datos"])
        p.update({k: v for k, v in d.items() if k != "pesos"})
        p["pesos"].update(d.get("pesos", {}))
    return p


def perfil_ia(usuario):
    """Perfil + lo que dicen sus datos de aprendizaje (para que la IA se adapte)."""
    p = perfil_de(usuario)
    try:
        p["adaptacion"] = ad.plan_adaptativo(usuario, p)["adaptacion"]
    except Exception:
        traceback.print_exc()
    return p


def guardar_perfil(usuario, p):
    ahora = time.time()
    ejecutar("""INSERT INTO perfil(usuario,datos,creado,actualizado) VALUES(?,?,?,?)
                ON CONFLICT(usuario) DO UPDATE SET datos=excluded.datos, actualizado=excluded.actualizado""",
             (usuario, json.dumps(p, ensure_ascii=False), ahora, ahora))


# ---------------------------------------------------------------- tarjetas
def agregar_tarjetas(usuario, tarjetas, tema=None, area=None, idioma=None, origen="leccion"):
    n = 0
    for t in tarjetas:
        fr, rv = (t.get("frente") or "").strip(), (t.get("reverso") or "").strip()
        if not fr or not rv:
            continue
        if fila("SELECT id FROM tarjeta WHERE usuario=? AND frente=? AND IFNULL(tema,'')=IFNULL(?,'')",
                (usuario, fr, tema)):
            continue
        ejecutar("""INSERT INTO tarjeta(usuario,tema,area,frente,reverso,idioma,origen,creada)
                    VALUES(?,?,?,?,?,?,?,?)""", (usuario, tema, area, fr, rv, idioma, origen, time.time()))
        n += 1
    return n


def inicio_dia(t=None):
    d = datetime.fromtimestamp(t or time.time())
    if d.hour < 4:  # el "día de estudio" cambia a las 4 a. m.
        d -= timedelta(days=1)
    return d.replace(hour=4, minute=0, second=0, microsecond=0).timestamp()


def cola_repaso(usuario, perfil, limite=200):
    ahora = time.time()
    vencidas = filas("""SELECT * FROM tarjeta WHERE usuario=? AND suspendida=0 AND estabilidad IS NOT NULL
                        AND vence<=? ORDER BY vence LIMIT ?""", (usuario, ahora, limite))
    hoy_nuevas = fila("""SELECT COUNT(*) n FROM repaso r JOIN tarjeta t ON t.id=r.tarjeta
                         WHERE r.usuario=? AND r.fecha>=? AND r.retenibilidad IS NULL""",
                      (usuario, inicio_dia()))["n"]
    cupo = max(0, perfil.get("tarjetas_nuevas_dia", 25) - hoy_nuevas)
    nuevas = filas("""SELECT * FROM tarjeta WHERE usuario=? AND suspendida=0 AND estabilidad IS NULL
                      ORDER BY creada, id LIMIT ?""", (usuario, cupo))
    # Intercalar: mezclar áreas para que el cerebro tenga que "cambiar de chip".
    por_area = {}
    for t in vencidas + nuevas:
        por_area.setdefault(t["area"] or "", []).append(t)
    mezcla = []
    while any(por_area.values()):
        for k in list(por_area):
            if por_area[k]:
                mezcla.append(por_area[k].pop(0))
    return mezcla, len(vencidas), len(nuevas)


def racha(usuario):
    dias = {datetime.fromtimestamp(inicio_dia(r["fecha"])).date() for r in filas(
        "SELECT fecha FROM actividad WHERE usuario=? AND fecha>?", (usuario, time.time() - 400 * 86400))}
    d = datetime.fromtimestamp(inicio_dia()).date()
    if d not in dias:
        d -= timedelta(days=1)
    n = 0
    while d in dias:
        n += 1
        d -= timedelta(days=1)
    return n


# ---------------------------------------------------------------- seguridad
HOSTS_BASE = {"localhost", "127.0.0.1", "[::1]", "::1"}


def _redes():
    out = []
    for r in config.C.get("redes_locales") or ["127.0.0.0/8", "::1/128"]:
        try:
            out.append(ipaddress.ip_network(r, strict=False))
        except ValueError:
            pass
    return out


def ip_local(ip):
    """¿La petición viene de «este PC» (o de la red interna del contenedor)?"""
    try:
        a = ipaddress.ip_address(ip.split("%")[0])
    except ValueError:
        return False
    if getattr(a, "ipv4_mapped", None):
        a = a.ipv4_mapped
    return any(a in r for r in _redes())


def _firma_clave():
    """Valor de la cookie de acceso: HMAC de la clave (cambia si cambias la clave)."""
    clave = config.C.get("clave_acceso") or ""
    return hmac.new(clave.encode(), b"academia-acceso-v1", hashlib.sha256).hexdigest() if clave else ""


def host_permitido(host):
    if not host:
        return True                     # HTTP/1.0 sin Host: solo clientes locales viejos
    h = host.strip().lower()
    nombre = h.rsplit(":", 1)[0] if not h.endswith("]") else h
    extras = {x.lower() for x in (config.C.get("hosts_permitidos") or [])}
    if nombre in HOSTS_BASE or nombre in extras or nombre.endswith(".ts.net"):
        return True
    try:                                # una IP escrita a mano (p. ej. 192.168.1.20) no es DNS rebinding
        ipaddress.ip_address(nombre.strip("[]"))
        return True
    except ValueError:
        return False


_INTENTOS = threading.Lock()
PAGINA_CLAVE = """<!doctype html><html lang="es"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Academia · acceso</title><style>body{font:16px system-ui;display:grid;place-items:center;min-height:100vh;margin:0;background:#f5f6f8;color:#1c1f26}
@media(prefers-color-scheme:dark){body{background:#111318;color:#e8eaf0}}form{display:grid;gap:.7rem;max-width:320px;width:90%}
input,button{font:inherit;padding:.7rem;border-radius:10px;border:1px solid #8886}button{background:#4f6df5;color:#fff;border:0}</style>
<form method="post" action="/acceso"><h1>🎓 Academia</h1><p>Esta Academia pide clave para entrar desde otro equipo.</p>
<input type="password" name="clave" placeholder="Clave de acceso" autofocus required><button>Entrar</button>{AVISO}</form></html>"""


# ---------------------------------------------------------------- handler
class Manejador(BaseHTTPRequestHandler):
    server_version = "Academia/" + config.VERSION

    def log_message(self, fmt, *args):
        pass

    # ---- utilidades
    def de_confianza(self):
        """Petición de este PC (o de tailscale serve, que también conecta desde aquí)."""
        return ip_local(self.client_address[0])

    def con_clave(self):
        firma = _firma_clave()
        ck = re.search(r"(?:^|;\s*)acceso=([0-9a-f]{64})", self.headers.get("Cookie", ""))
        return bool(firma and ck and hmac.compare_digest(ck.group(1), firma))

    def tailscale(self):
        """Cuenta de Tailscale, solo si la puso `tailscale serve` (que conecta desde este PC)."""
        return self.headers.get("Tailscale-User-Login") if self.de_confianza() else None

    def usuario(self):
        login = self.tailscale()
        perm = permitidos()
        if login:
            return login if (not perm or login in perm) else None
        ck = re.search(r"(?:^|;\s*)perfil=([^;]+)", self.headers.get("Cookie", ""))
        if ck and urllib.parse.unquote(ck.group(1)) in perm:
            return urllib.parse.unquote(ck.group(1))
        return config.C.get("usuario_local") or (perm[0] if perm else "local")

    def end_headers(self):
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "SAMEORIGIN")
        self.send_header("Referrer-Policy", "no-referrer")
        super().end_headers()

    def _comprimir(self, datos, tipo):
        """gzip para texto de más de 2 KB si el navegador lo acepta: el mapa (~300 KB) o app.js llegan en una
        fracción por el celular."""
        if len(datos) < 2048 or "gzip" not in (self.headers.get("Accept-Encoding") or "") or not (
                tipo.startswith("text/") or "json" in tipo or "javascript" in tipo or "svg" in tipo):
            return datos, False
        return gzip.compress(datos, 5), True

    def json(self, obj, codigo=200):
        cuerpo, gz = self._comprimir(json.dumps(obj, ensure_ascii=False).encode(), "json")
        self.send_response(codigo)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        if gz:
            self.send_header("Content-Encoding", "gzip")
        self.send_header("Vary", "Accept-Encoding")
        self.send_header("Content-Length", str(len(cuerpo)))
        self.end_headers()
        self.wfile.write(cuerpo)

    def texto(self, t, tipo="text/plain; charset=utf-8", codigo=200):
        b = t.encode()
        self.send_response(codigo)
        self.send_header("Content-Type", tipo)
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def cuerpo(self):
        n = int(self.headers.get("Content-Length") or 0)
        if n > 60_000_000:
            raise ValueError("demasiado grande")
        return json.loads(self.rfile.read(n) or b"{}") if n else {}

    def archivo(self, ruta, cache=True):
        if not ruta.is_file():
            return self.texto("no existe", codigo=404)
        datos = ruta.read_bytes()
        tipo = mimetypes.guess_type(str(ruta))[0] or "application/octet-stream"
        if ruta.suffix == ".webmanifest":
            tipo = "application/manifest+json"
        datos, gz = self._comprimir(datos, tipo)
        self.send_response(200)
        self.send_header("Content-Type", tipo + ("; charset=utf-8" if tipo.startswith("text/") or tipo.endswith("javascript") else ""))
        if gz:
            self.send_header("Content-Encoding", "gzip")
        self.send_header("Vary", "Accept-Encoding")
        self.send_header("Content-Length", str(len(datos)))
        self.send_header("Cache-Control", "public, max-age=86400" if cache and "vendor" in str(ruta) else "no-cache")
        self.end_headers()
        self.wfile.write(datos)

    def _acceso(self):
        n = min(int(self.headers.get("Content-Length") or 0), 4096)
        datos = urllib.parse.parse_qs(self.rfile.read(n).decode("utf-8", "replace"))
        clave = (datos.get("clave") or [""])[0]
        with _INTENTOS:                 # de a uno y con 1 s cada uno: adivinar a ciegas se vuelve inviable
            time.sleep(1)
        if not hmac.compare_digest(clave.encode(), (config.C.get("clave_acceso") or "").encode()):
            return self.texto(PAGINA_CLAVE.replace("{AVISO}", "<p style='color:#d64545'>Clave incorrecta.</p>"), "text/html; charset=utf-8", 401)
        self.send_response(303)
        self.send_header("Set-Cookie", f"acceso={_firma_clave()}; Path=/; Max-Age=31536000; HttpOnly; SameSite=Strict")
        self.send_header("Location", "/")
        self.send_header("Content-Length", "0")
        self.end_headers()

    # ---- enrutado
    def do_GET(self):
        self._rutear("GET")

    def do_POST(self):
        self._rutear("POST")

    def do_DELETE(self):
        self._rutear("DELETE")

    def _rutear(self, metodo):
        u = urllib.parse.urlparse(self.path)
        q = {k: v[0] for k, v in urllib.parse.parse_qs(u.query).items()}
        ruta = u.path
        # 1) Host conocido (contra DNS rebinding: una web maliciosa que apunte su dominio a 127.0.0.1)
        if not host_permitido(self.headers.get("Host", "")):
            return self.texto("Host no permitido. Añádelo en «hosts_permitidos» si es tuyo.", codigo=421)
        # 2) Equipos que no son este PC: con la clave de acceso o nada
        if not self.de_confianza() and not self.con_clave():
            if ruta == "/acceso" and metodo == "POST" and config.C.get("clave_acceso"):
                return self._acceso()
            if not config.C.get("clave_acceso"):
                return self.texto("Esta Academia solo acepta conexiones desde su propio PC (o por tailscale serve). "
                                  "Para entrar desde la red, define «clave_acceso» (ver docs/SEGURIDAD_Y_DATOS.md).", codigo=403)
            if ruta.startswith("/api/"):
                return self.json({"error": "falta la clave de acceso"}, 401)
            return self.texto(PAGINA_CLAVE.replace("{AVISO}", ""), "text/html; charset=utf-8", 401)
        # 3) Escrituras: solo JSON y del mismo origen (contra CSRF desde otras páginas abiertas en tu navegador)
        if metodo in ("POST", "DELETE") and ruta.startswith("/api/"):
            tipo = (self.headers.get("Content-Type") or "").split(";")[0].strip().lower()
            origen = self.headers.get("Origin")
            if int(self.headers.get("Content-Length") or 0) and tipo != "application/json":
                return self.json({"error": "solo se acepta JSON"}, 415)
            if origen and urllib.parse.urlparse(origen).netloc.lower() != (self.headers.get("Host") or "").lower():
                return self.json({"error": "origen no permitido"}, 403)
        usuario = self.usuario()
        if usuario is None:
            return self.texto("Cuenta de Tailscale no autorizada para la Academia.", codigo=403)
        try:
            if not ruta.startswith("/api/"):
                if metodo != "GET":
                    return self.texto("no", codigo=405)
                rel = ruta.lstrip("/") or "index.html"
                destino = (WEB / rel).resolve()
                if WEB.resolve() not in destino.parents and destino != WEB.resolve():
                    return self.texto("no", codigo=404)
                if not destino.exists() and "." not in rel:
                    destino = WEB / "index.html"
                return self.archivo(destino)
            fn = RUTAS.get((metodo, ruta))
            if fn is None:
                m = re.match(r"^/api/cuaderno/img/(\d+)\.png$", ruta)
                if m and metodo == "GET":
                    return img_cuaderno(self, usuario, int(m.group(1)))
                m = re.match(r"^/api/entrega/img/(\d+)$", ruta)
                if m and metodo == "GET":
                    return img_entrega(self, usuario, int(m.group(1)))
                return self.json({"error": "ruta desconocida"}, 404)
            datos = self.cuerpo() if metodo in ("POST", "DELETE") else {}
            res = fn(usuario, q, datos, self)
            if res is not None:
                self.json(res)
        except (BrokenPipeError, ConnectionResetError):
            return   # la persona cerró la pestaña o cambió de vista antes de recibir la respuesta: no es un fallo
        except Exception as e:
            traceback.print_exc()
            try:
                self.json({"error": f"{type(e).__name__}: {e}"}, 500)
            except Exception:
                pass


RUTAS = {}


def ruta(metodo, camino):
    def deco(fn):
        RUTAS[(metodo, camino)] = fn
        return fn
    return deco


def trabajo_json(t):
    return {"trabajo": t.id, "estado": t.estado}


# ------------------------------------------------------------- perfil/hoy
@ruta("GET", "/api/yo")
def r_yo(usuario, q, d, h):
    return {"usuario": usuario, "perfil": perfil_de(usuario),
            "local": not h.tailscale() and h.de_confianza(), "perfiles": permitidos(),
            "areas": sorted(cur.areas_de(usuario)),
            "prioridad": {a: cur.peso(x, perfil_de(usuario)["pesos"], usuario, cur.areas_de_metas(usuario))
                          for a, x in cur.areas(usuario).items() if a in cur.areas_de(usuario)},
            "hora_diaria": "%02d:%02d" % hora_diaria(), "chequeo_dia": an.dia_chequeo(usuario), "diaria_ultima": kv_get("diaria_ultima", 0),
            "wpm": lectura.wpm_base(usuario)}


@ruta("POST", "/api/perfil")
def r_perfil(usuario, q, d, h):
    p = perfil_de(usuario)
    for k in ("nombre", "situacion", "metas", "estilo", "nuevos_dia", "tarjetas_nuevas_dia", "minutos_dia",
              "solo_lapiz", "dia_maxima", "configurado", "modo_lectura", "paso_a_paso", "diagnostico_previo",
              "sesion_corta"):
        if k in d:
            p[k] = d[k]
    if isinstance(d.get("pesos"), dict):
        p["pesos"].update({k: max(0, min(3, int(v))) for k, v in d["pesos"].items()})
    if isinstance(d.get("regiones"), dict):
        conocidas = nt.config()["regiones"]
        p["regiones"] = {k: max(0, min(3, int(v))) for k, v in d["regiones"].items() if k in conocidas}
    guardar_perfil(usuario, p)
    if "pesos" in d or "nuevos_dia" in d:
        ad.reiniciar_plan_si_no_empezo(usuario)
    return {"ok": True, "perfil": p}


def _tarjeta_tema(tid, usuario, areas, avs, tipo):
    t = cur.tema(tid, usuario)
    if not t:
        return None
    a = areas[t["area"]]
    lecc = fila("SELECT creado, ejercicios IS NOT NULL ej FROM leccion WHERE usuario=? AND tema=?", (usuario, tid))
    av = avs.get(tid) or {}
    hecho = bool(av.get("visto") and av["visto"] >= ad.inicio_hoy()) or (
        tipo == "recuperar" and fila("""SELECT 1 FROM actividad WHERE usuario=? AND tema=? AND tipo IN ('quiz','leccion')
                                        AND fecha>?""", (usuario, tid, ad.inicio_hoy())) is not None)
    preparando = any(x.etiqueta == tid and x.tipo == "leccion" and x.usuario == usuario and x.estado in ("cola", "corriendo")
                     for x in ia.cola.trabajos.values())
    return {"id": tid, "t": t["t"], "d": t["d"], "area": a["nombre"], "icono": a.get("icono"),
            "color": a.get("color"), "nivel": t["nivel"], "nivel_nombre": cur.NIVELES[t["nivel"]],
            "modulo": cur.modulo(t["modulo"], usuario)["t"], "lista": bool(lecc), "preparando": preparando,
            "estado": av.get("estado", "nuevo"), "hecho": hecho, "tipo": tipo}


def _con_motivo(x, plan):
    if x:
        x["motivo"] = (plan.get("motivos") or {}).get(x["id"], "")
    return x


@ruta("GET", "/api/hoy")
def r_hoy(usuario, q, d, h):
    perfil = perfil_de(usuario)
    plan = ad.plan_del_dia(usuario, perfil)
    adapt = ad.plan_adaptativo(usuario, perfil)
    areas = cur.areas(usuario)
    avs = cur.avances(usuario)
    temas = [x for x in ([_con_motivo(_tarjeta_tema(t, usuario, areas, avs, "recuperar"), plan) for t in plan["recuperar"]]
                         + [_tarjeta_tema(t, usuario, areas, avs, "nuevo") for t in plan["temas"]]
                         + [_tarjeta_tema(t, usuario, areas, avs, "extra") for t in plan["extra"]]) if x]
    cola, venc, nuevas = cola_repaso(usuario, perfil)
    ini = inicio_dia()
    hechos = fila("SELECT COUNT(*) n FROM repaso WHERE usuario=? AND fecha>=?", (usuario, ini))["n"]
    seg = fila("SELECT IFNULL(SUM(valor),0) s FROM actividad WHERE usuario=? AND tipo='tiempo' AND fecha>=?",
               (usuario, ini))["s"]
    lecc_hoy = fila("SELECT COUNT(*) n FROM actividad WHERE usuario=? AND tipo='leccion' AND fecha>=?",
                    (usuario, ini))["n"]
    objetivos = [cur.estado_objetivo(usuario, o) for o in
                 filas("SELECT * FROM objetivo WHERE usuario=? AND estado='activo' ORDER BY id DESC LIMIT 3",
                       (usuario,))]
    abierto = fila("SELECT id, creado FROM chequeo WHERE usuario=? AND completado IS NULL ORDER BY id DESC LIMIT 1",
                   (usuario,))
    pulso_hecho = ad.pulso_hecho_hoy(usuario)
    hay_tarjetas = bool(fila("SELECT 1 FROM tarjeta WHERE usuario=? AND estabilidad IS NOT NULL", (usuario,)))
    pendiente = next((t for t in temas if not t["hecho"]), None)
    if abierto:
        sig = {"ir": f"chequeo/{abierto['id']}", "titulo": "🧪 Haz tu chequeo semanal", "por_que": "10-15 min: muestra qué olvidaste para recuperarlo antes de que cueste más."}
    elif not pulso_hecho and hay_tarjetas:
        sig = {"ir": "pulso", "titulo": "⚡ Pulso de 1-2 min", "por_que": "5 tarjetas para calentar: recuperar algo antes de lo nuevo fija ambos."}
    elif venc >= 15:
        sig = {"ir": "repasar", "titulo": f"🔁 Repasa {venc} tarjetas vencidas", "por_que": "Están a punto de olvidarse: repasarlas hoy cuesta segundos; mañana, reaprender."}
    elif pendiente:
        sig = {"ir": f"tema/{pendiente['id']}", "titulo": ("♻️ " if pendiente["tipo"] == "recuperar" else "📖 ") + pendiente["t"],
               "por_que": pendiente.get("motivo") or "El tema que más rinde ahora según tu prioridad, tus metas y lo que desbloquea."}
    elif venc:
        sig = {"ir": "repasar", "titulo": f"🔁 Repasa {venc} tarjetas", "por_que": "Lo nuevo de hoy está hecho: cierra con repaso."}
    elif not temas:
        sig = {"ir": "objetivos", "titulo": "🎯 Crea una meta de aprendizaje",
               "por_que": "Aún no hay temas para ti: escribe qué quieres lograr y la IA arma la ruta con todo lo necesario."}
    else:
        sig = {"ir": "", "titulo": "🎉 Hoy está hecho", "por_que": "Descansar y dormir también consolidan lo aprendido. Si te sobra energía: ➕ Otra sesión."}
    pruebas_listas = fila("SELECT COUNT(*) n FROM prueba_nivel WHERE usuario=? AND estado='lista'", (usuario,))["n"]
    eventos.sugerencia(usuario, sig["ir"], sig["titulo"])   # F1: para medir después si la sigue o la ignora
    return {"temas": temas, "repaso": {"vencidas": venc, "nuevas": nuevas, "hechas_hoy": hechos}, "siguiente": sig,
            "pruebas_listas": pruebas_listas,
            "chequeo": abierto, "adaptacion": {k: adapt[k] for k in ("ajustes", "bloque", "mejor_franja", "nuevos", "base")},
            "pulso_hecho": pulso_hecho,
            "hay_tarjetas": hay_tarjetas,
            "minutos_hoy": round(seg / 60), "meta_minutos": perfil.get("minutos_dia", 60),
            "lecciones_hoy": lecc_hoy, "racha": racha(usuario),
            "objetivos": [{"id": o["id"], "titulo": o["titulo"], "progreso": o["progreso"]} for o in objetivos],
            "noticias": (nt.ranking("dia", limite=3, areas=mias & set(nt.AREAS_NOTICIAS), solo_a_fondo=True,
                                    regiones=regiones_de(usuario))
                         if (mias := cur.areas_de(usuario)) & set(nt.AREAS_NOTICIAS) else []),
            "configurado": perfil.get("configurado"),
            "sesion_corta": _sesion_corta(perfil, venc, nuevas, pendiente, pulso_hecho, hay_tarjetas),
            "ia": estado_ia(usuario)}


def _sesion_corta(perfil, venc, nuevas, pendiente, pulso_hecho, hay_tarjetas):
    """«Tu sesión de N minutos»: pocos pasos que caben en el tiempo que la persona eligió (modo corto, para quien
    estudia poco cada día). Una tarjeta ~25 s; de una lección larga se lee UNA parte."""
    m = int(perfil.get("sesion_corta") or 0)
    if m <= 0:
        return None
    pasos, usado = [], 0
    if not pulso_hecho and hay_tarjetas and m >= 6:
        pasos.append({"ir": "pulso", "titulo": "⚡ Pulso: 5 tarjetas para calentar", "min": 2})
        usado += 2
    reserva = 4 if pendiente and m >= 8 else 0
    n = min(venc + nuevas, max(0, (m - usado - reserva) * 60 // 25))
    if n:
        pasos.append({"ir": "repasar", "titulo": f"🔁 Repasar {n} tarjetas", "min": max(1, round(n * 25 / 60))})
        usado += pasos[-1]["min"]
    if pendiente and m - usado >= 3:
        pasos.append({"ir": f"tema/{pendiente['id']}", "titulo": f"📖 Una parte de «{pendiente['t']}»",
                      "min": m - usado})
        usado = m
    return {"minutos": m, "pasos": pasos, "total": usado}


def _lista(usuario, tid, maxima):
    """¿La lección ya está como se pide? Con «maxima», además a la versión más profunda (las de idiomas tienen
    una sola versión: lista es lista)."""
    v = fila("SELECT version, completa FROM leccion WHERE usuario=? AND tema=? AND ejercicios IS NOT NULL", (usuario, tid))
    if not v:
        return False
    if not maxima or (v["version"] or 1) >= lec.VERSION_MAXIMA:
        return True
    t = cur.tema(tid, usuario)
    return not t or bool(cur.areas(usuario)[t["area"]].get("idioma"))


def _leccion_y_rapida(ctx, tid, usuario, perfil, maxima):
    """Lección del plan; detrás, su vista previa (si la persona no termina las completas) y el contraste de sus
    afirmaciones con fuentes verificadas (`verificar_lecciones`)."""
    r = lec.generar_leccion(ctx, tid, usuario, perfil, False, maxima)
    try:
        if aa.formato(usuario)["recomendado"] == "esencial":
            aa.preparar_rapida(usuario, perfil, tid, 1)
        if config.C.get("verificar_lecciones"):
            encolar_verificacion(usuario, tid, 2)
    except Exception:
        traceback.print_exc()
    return r


def _verif_en_cola(usuario, clave):
    return next((x for x in ia.cola.trabajos.values() if x.tipo == "verificar" and x.usuario == usuario
                 and x.etiqueta == clave and x.estado in ("cola", "corriendo", "conflicto")), None)


def encolar_verificacion(usuario, tid, prioridad):
    t = _verif_en_cola(usuario, f"tema:{tid}")
    if t:
        if prioridad == 0 and t.prioridad > 0 and t.estado == "cola":
            ia.cola.subir(t)
        return t
    return ia.nuevo("verificar", lambda ctx: vf.verificar_leccion(ctx, usuario, tid), prioridad, usuario, f"tema:{tid}")


def preparar_lecciones(usuario, tids, prioridad, maxima=False):
    perfil = perfil_ia(usuario)
    n = 0
    for tid in tids:
        if _lista(usuario, tid, maxima):
            continue
        previo = next((x for x in ia.cola.trabajos.values() if x.tipo == "leccion" and x.etiqueta == tid and x.usuario == usuario
                       and x.estado in ("cola", "corriendo", "conflicto")), None)
        if previo:
            if prioridad == 0 and previo.prioridad > 0 and previo.estado == "cola":
                ia.cola.subir(previo)
            continue
        ia.nuevo("leccion", lambda ctx, tid=tid: _leccion_y_rapida(ctx, tid, usuario, perfil, maxima),
                 prioridad, usuario, tid)
        n += 1
    return n


@ruta("POST", "/api/hoy/preparar")
def r_hoy_preparar(usuario, q, d, h):
    perfil = perfil_de(usuario)
    plan = ad.plan_del_dia(usuario, perfil)
    n = preparar_lecciones(usuario, plan["recuperar"] + plan["temas"] + plan["extra"], 0, bool(perfil.get("dia_maxima")))
    return {"ok": True, "encoladas": n}


@ruta("POST", "/api/hoy/extra")
def r_hoy_extra(usuario, q, d, h):
    perfil = perfil_de(usuario)
    cantidad = max(1, min(int(d.get("cantidad") or perfil.get("nuevos_dia", 3)), 10))
    nuevos = ad.agregar_sesion(usuario, perfil, cantidad)
    if d.get("preparar", True):
        preparar_lecciones(usuario, nuevos, 0, bool(perfil.get("dia_maxima")))
    return {"ok": True, "agregados": len(nuevos)}


@ruta("GET", "/api/pulso")
def r_pulso(usuario, q, d, h):
    return {"tarjetas": ad.pulso(usuario, int(q.get("n", 5)), q.get("modo", "diario"), q.get("tema")),
            "hecho": ad.pulso_hecho_hoy(usuario)}


@ruta("POST", "/api/pulso")
def r_pulso_fin(usuario, q, d, h):
    ad.registrar_pulso(usuario, int(d.get("bien", 0)), int(d.get("total", 0)), d.get("modo", "diario"))
    ad.invalidar(usuario)
    return {"ok": True}


@ruta("GET", "/api/niveles")
def r_niveles(usuario, q, d, h):
    ad.actualizar_niveles(usuario)
    return ad.niveles(usuario) | {"historial": ad.historial_niveles(usuario)}


@ruta("GET", "/api/largo_plazo")
def r_largo(usuario, q, d, h):
    return {"largo": ad.largo_plazo(usuario), "cambios": ad.cambios(usuario),
            "plan": ad.plan_adaptativo(usuario, perfil_de(usuario))}


@ruta("GET", "/api/reporte")
def r_reporte(usuario, q, d, h):
    r = ad.datos_reporte(usuario, perfil_de(usuario))
    r["trabajo"] = next((x.publico() for x in ia.cola.trabajos.values()
                         if x.tipo == "reporte" and x.usuario == usuario and x.estado in ("cola", "corriendo", "conflicto")), None)
    return r


# ---------------------------------------------------------------- 💻 práctica con código
def _ejercicio_de(usuario, eid):
    try:
        return fila("SELECT * FROM codigo_ejercicio WHERE id=? AND usuario=?", (int(eid), usuario))
    except (TypeError, ValueError):
        return None


def _codigo_en_cola(usuario, tid):
    return next((x for x in ia.cola.trabajos.values() if x.tipo == "codigo" and x.usuario == usuario and x.etiqueta == tid
                 and x.estado in ("cola", "corriendo", "conflicto")), None)


@ruta("GET", "/api/codigo/estado")
def r_codigo_estado(usuario, q, d, h):
    tid = q.get("tema", "")
    t = cur.tema(tid, usuario)
    if not t:
        return {"error": "tema desconocido"}
    ok, motivo = ejc.disponible()
    area = t.get("area") or tid.split(".")[0]
    exs = []
    for r in filas("SELECT id, datos, creado, vio_solucion FROM codigo_ejercicio WHERE usuario=? AND tema=? ORDER BY id DESC LIMIT 10", (usuario, tid)):
        it = fila("SELECT COUNT(*) n, MAX(aprobado) ap, MAX(CASE WHEN aprobado=1 AND vio_solucion=0 THEN 1 ELSE 0 END) limpio "
                  "FROM codigo_intento WHERE usuario=? AND ejercicio=?", (usuario, r["id"]))
        exs.append({"id": r["id"], "titulo": json.loads(r["datos"]).get("titulo"), "creado": r["creado"], "intentos": it["n"],
                    "aprobado": bool(it["ap"]), "limpio": bool(it["limpio"]), "vio_solucion": bool(r["vio_solucion"])})
    tr = _codigo_en_cola(usuario, tid)
    return {"disponible": ok, "motivo": motivo, "area_ok": area in ejc.AREAS_CODIGO, "ejercicios": exs,
            "trabajo": tr.publico() if tr else None}


@ruta("POST", "/api/codigo/nuevo")
def r_codigo_nuevo(usuario, q, d, h):
    tid = str(d.get("tema", ""))
    t = cur.tema(tid, usuario)
    if not t:
        return {"error": "tema desconocido"}
    if (t.get("area") or tid.split(".")[0]) not in ejc.AREAS_CODIGO:
        return {"error": "la práctica con código es para las áreas de sistemas, ciberseguridad, tecnología, mecatrónica y matemáticas"}
    ok, motivo = ejc.disponible()
    if not ok:
        return {"error": motivo}
    x = _codigo_en_cola(usuario, tid)
    if x:
        return trabajo_json(x)
    perfil = perfil_ia(usuario)
    tr = ia.nuevo("codigo", lambda ctx: ejc.generar(ctx, usuario, tid, perfil, None), 0, usuario, tid)
    tr.permiso = d.get("permiso")
    return trabajo_json(tr)


@ruta("GET", "/api/codigo/ejercicio")
def r_codigo_ejercicio(usuario, q, d, h):
    r = _ejercicio_de(usuario, q.get("id"))
    if not r:
        return {"error": "ejercicio no encontrado"}
    ult = fila("SELECT codigo FROM codigo_intento WHERE usuario=? AND ejercicio=? ORDER BY id DESC LIMIT 1", (usuario, r["id"]))
    return dict(ejc.publico(r), ultimo_codigo=ult["codigo"] if ult else None,
                intentos=fila("SELECT COUNT(*) n FROM codigo_intento WHERE usuario=? AND ejercicio=?", (usuario, r["id"]))["n"],
                pista=json.loads(r["datos"]).get("pista"))


@ruta("POST", "/api/codigo/ejecutar")
def r_codigo_ejecutar(usuario, q, d, h):
    r = _ejercicio_de(usuario, d.get("id"))
    if not r:
        return {"error": "ejercicio no encontrado"}
    codigo = str(d.get("codigo") or "")
    if not codigo.strip():
        return {"error": "escribe tu código primero"}
    res = ejc.evaluar(usuario, r, codigo)
    if res.get("error"):
        return res
    aprobado = res["aprobados"] == res["total"] and not res.get("error_carga")
    ejecutar("INSERT INTO codigo_intento(usuario,ejercicio,codigo,aprobados,total,aprobado,vio_solucion,fecha) VALUES(?,?,?,?,?,?,?,?)",
             (usuario, r["id"], codigo[:ejc.CODIGO_MAX], res["aprobados"], res["total"], int(aprobado), int(bool(r["vio_solucion"])), time.time()))
    t = cur.tema(r["tema"], usuario)
    registrar(usuario, "codigo", r["tema"], (t or {}).get("area"), res["aprobados"] / max(1, res["total"]),
              {"ejercicio": r["id"], "vio_solucion": bool(r["vio_solucion"]), "aprobado": aprobado})
    res["aprobado"] = aprobado
    return res


@ruta("POST", "/api/codigo/solucion")
def r_codigo_solucion(usuario, q, d, h):
    """Pedir la solución es válido para aprender, pero queda anotado: un ejercicio resuelto después no cuenta como evidencia."""
    r = _ejercicio_de(usuario, d.get("id"))
    if not r:
        return {"error": "ejercicio no encontrado"}
    ejecutar("UPDATE codigo_ejercicio SET vio_solucion=1 WHERE id=?", (r["id"],))
    return {"solucion": json.loads(r["datos"])["solucion"]}


# ---------------------------------------------------------------- 🧬 dominio medido: estados 0-5 y prueba diferida (modo sombra)
def _diferida_en_cola(usuario, tid):
    return next((x for x in ia.cola.trabajos.values() if x.tipo == "diferida" and x.usuario == usuario and x.etiqueta == tid
                 and x.estado in ("cola", "corriendo", "conflicto")), None)


@ruta("GET", "/api/dominio/tema")
def r_dominio_tema(usuario, q, d, h):
    tid = q.get("tema", "")
    if not cur.tema(tid, usuario):
        return {"error": "tema desconocido"}
    cal = est.calendario(usuario, tid)
    sig = next((c for c in cal if not c["hecha"]), None)
    lista = fila("SELECT id, etapa FROM prueba_diferida WHERE usuario=? AND tema=? AND estado='lista' ORDER BY id DESC LIMIT 1", (usuario, tid))
    tr = _diferida_en_cola(usuario, tid)
    return {"estado": est.estado_tema(usuario, tid), "calendario": cal, "siguiente": sig, "lista": dict(lista) if lista else None,
            "trabajo": tr.publico() if tr else None, "estados": est.ESTADOS, "dias": est.DIAS_ETAPA}


@ruta("GET", "/api/dominio/estados")
def r_dominio_estados(usuario, q, d, h):
    return est.estados_persona(usuario)


@ruta("POST", "/api/diferida/preparar")
def r_diferida_preparar(usuario, q, d, h):
    tid = str(d.get("tema", ""))
    if not cur.tema(tid, usuario):
        return {"error": "tema desconocido"}
    sig = est.siguiente_cita(usuario, tid)
    if not sig:
        return {"error": "este tema aún no cuenta como dominado (o ya hiciste las tres pruebas diferidas)"}
    if not sig["disponible"]:
        return {"error": "todavía no toca: la prueba de los %d días está disponible desde el %s" % (
            sig["dias"], datetime.fromtimestamp(sig["desde"]).strftime("%d/%m/%Y"))}
    x = fila("SELECT id FROM prueba_diferida WHERE usuario=? AND tema=? AND etapa=? AND estado='lista'", (usuario, tid, sig["etapa"]))
    if x:
        return {"lista": x["id"]}
    en = _diferida_en_cola(usuario, tid)
    if en:
        return trabajo_json(en)
    perfil = perfil_ia(usuario)
    t = ia.nuevo("diferida", lambda ctx: est.generar_banco(ctx, usuario, tid, sig["etapa"], perfil), 0, usuario, tid)
    t.permiso = d.get("permiso")
    return trabajo_json(t)


@ruta("GET", "/api/diferida/prueba")
def r_diferida_prueba(usuario, q, d, h):
    r = fila("SELECT * FROM prueba_diferida WHERE id=? AND usuario=?", (q.get("id"), usuario))
    return est.publica(r) if r else {"error": "prueba no encontrada"}


@ruta("POST", "/api/diferida/responder")
def r_diferida_responder(usuario, q, d, h):
    r = fila("SELECT * FROM prueba_diferida WHERE id=? AND usuario=?", (d.get("id"), usuario))
    if not r:
        return {"error": "prueba no encontrada"}
    return est.responder(usuario, r, d.get("respuestas"))


@ruta("GET", "/api/tablero")
def r_tablero(usuario, q, d, h):
    return ad.tablero(usuario, perfil_de(usuario))


@ruta("GET", "/api/reporte.md")
def r_reporte_md(usuario, q, d, h):
    texto = ad.reporte_markdown(ad.datos_reporte(usuario, perfil_de(usuario)))
    b = texto.encode()
    h.send_response(200)
    h.send_header("Content-Type", "text/markdown; charset=utf-8")
    h.send_header("Content-Disposition", f'attachment; filename="reporte-academia-{datetime.now():%Y-%m-%d}.md"')
    h.send_header("Content-Length", str(len(b)))
    h.end_headers()
    h.wfile.write(b)


@ruta("GET", "/api/exportar")
def r_exportar(usuario, q, d, h):
    b = ad.exportar_zip(usuario, CUADERNO)
    h.send_response(200)
    h.send_header("Content-Type", "application/zip")
    h.send_header("Content-Disposition", f'attachment; filename="academia-datos-{datetime.now():%Y-%m-%d}.zip"')
    h.send_header("Content-Length", str(len(b)))
    h.end_headers()
    h.wfile.write(b)


@ruta("POST", "/api/reporte/ia")
def r_reporte_ia(usuario, q, d, h):
    perfil = perfil_de(usuario)

    def fn(ctx):
        r = ad.datos_reporte(usuario, perfil)
        md_ = ad.reporte_markdown(r)
        ctx.fase("Analizando tu reporte")
        texto = ctx.chat([{"role": "system", "content": lec.SISTEMA_BASE}, {"role": "user", "content": (
            lec.texto_perfil(perfil) + "\nEres su director académico. Lee este reporte con datos reales y escribe "
            "un análisis (markdown, 400-650 palabras) con estas cinco secciones, cada título en su propia línea y con un solo "
            "«##» al inicio (sin repetirlo): «Diagnóstico (desarrollo real vs metas)», «Fortalezas», «Necesidades y riesgos», "
            "«Cómo está aprendiendo y qué cambió» y «Recomendaciones para las próximas 4 semanas» (concretas: qué áreas, "
            "cuántos minutos, qué métodos, a qué hora). En el diagnóstico, REEVALÚA su "
            "nivel real comparando lo que domina con lo que el mercado pide HOY (sección «Nivel frente al mercado de "
            "hoy»): lo que se exige ahora no es lo de hace 5 años; señala qué competencias nuevas o en alza le faltan y "
            "cuáles de las que sabe van en declive. Usa SOLO estos datos; si son pocos, dilo. No inventes cifras.\n\n"
            + md_[:16000])}], max_tokens=2400, temperatura=0.4)
        kv_set(f"reporte_ia:{usuario}", {"texto": ad.limpiar_titulos(texto), "fecha": time.time(), "kpi": ad.kpi_reporte(r["analitica"])})
        return {"ok": True}

    t = ia.nuevo("reporte", fn, 0, usuario, "reporte")
    t.permiso = d.get("permiso")
    return trabajo_json(t)


# ------------------------------------------------------------ cola de la IA
# Trabajos de contenido común (noticias, síntesis, mercado…) se ven tal cual; los de otra persona, sin detalles.
COMUNES = {"noticias", "sintesis", "comparar", "explicar", "a_fondo", "lectura", "ciencia", "mercado"}
NOMBRE_TRABAJO = {
    "leccion": "📖 Lección", "tarea": "🏋️ Tarea de práctica", "objetivo": "🎯 Plan de meta", "area": "📚 Área completa",
    "chequeo": "🧪 Chequeo semanal", "reporte": "📄 Reporte", "prueba": "📝 Prueba de nivel", "tutor": "💬 Tutor",
    "corregir": "✅ Corrección", "entrega": "✅ Corrección de entrega", "apunte": "✍️ Evaluación de apuntes",
    "noticias": "🌍 Análisis de noticias", "sintesis": "🧭 Síntesis de noticias", "comparar": "🔎 Comparar fuentes",
    "explicar": "🔎 Noticia a fondo", "lectura": "🈶 Lectura en idioma", "ciencia": "🔬 Consultas científicas",
    "mercado": "📈 Referente del mercado", "a_fondo": "🌍 Noticia a fondo",
    "verificar": "🔎 Contrastar fuentes", "ruta": "🔄 Actualizar una ruta", "ramas": "🌳 Mapa de sub-ramas",
    "ideas": "🚀 Ideas en la frontera", "presentacion": "🎤 Preparar presentación", "pares": "🧑‍⚖️ Revisión de pares", "frontera": "🔭 Frontera de una meta", "paper": "📄 Lectura guiada de paper", "aporte": "💡 Evaluar tu aporte",
    "reexplicar": "🔄 Explicación de otra forma", "externo": "📥 Lo que estudiaste fuera", "aportada": "📎 Analizar una fuente que aportaste", "rapida": "⚡ Ruta rápida",
    "codigo": "💻 Ejercicio de código", "diferida": "🧬 Prueba diferida", "pronostico": "💹 Pronóstico de una acción", "relaciones": "💹 Mapa de una acción", "acciones": "💹 Acciones vigiladas",
}


def trabajo_visible(t, usuario, pos=0):
    """Cómo ve un trabajo de la cola esta persona: los suyos con detalle, los comunes tal cual,
    los de otra persona solo como «otra persona» (sin tema ni fase)."""
    base_ = {"estado": t.estado, "pos": pos, "fondo": t.prioridad > 0,
             "espera_hasta": t.no_antes if t.no_antes > time.time() else None, "creado": t.creado}
    if t.tipo in COMUNES or t.usuario == usuario:
        detalle = t.etiqueta
        if t.tipo == "leccion" and t.usuario == usuario:
            tt = cur.tema(t.etiqueta, usuario)
            detalle = tt["t"] if tt else t.etiqueta
        return base_ | {"tipo": NOMBRE_TRABAJO.get(t.tipo, t.tipo), "detalle": str(detalle or ""), "fase": t.fase,
                        "id": t.id if t.usuario == usuario else None, "mio": t.usuario == usuario, "comun": t.tipo in COMUNES}
    return base_ | {"tipo": "🔒 Tarea de otra persona", "detalle": "", "fase": "", "id": None, "mio": False, "comun": False}


def estado_ia(usuario=None):
    act = ia.cola.actual
    vis = trabajo_visible(act, usuario) if act else None
    return {"cargados": ia.modelos_cargados(), "ocupado_pc": ia.pc_ocupado(),
            "actual": {"tipo": vis["tipo"], "etiqueta": vis["detalle"], "fase": vis["fase"] or vis["tipo"]} if act else None,
            "corriendo": len(ia.cola.actuales), "paralelos": ia.paralelos(), "paralelos_nube": ia.en_nube(),
            "en_cola": len(ia.cola._h), "modelo": str(ia.MODELO), "modo": config.C.get("modo"),
            "ia_url": config.C.get("ia_url"), "permitir_interrumpir": config.C.get("permitir_interrumpir", True)}


def es_admin(h, usuario):
    """Puede cambiar la configuración: quien está en el propio PC, o las cuentas administradoras
    (por defecto la primera cuenta permitida = el dueño), también desde el celular."""
    if not h.tailscale() and h.de_confianza():
        return True
    if not h.tailscale():
        return False                    # otro equipo de la red con la clave: usa la Academia, no la administra
    admins = config.C.get("administradores")
    if admins is None:
        perm = permitidos()
        admins = perm[:1]
    return usuario in admins


@ruta("GET", "/api/config")
def r_config(usuario, q, d, h):
    c = dict(config.C)
    c["editable"] = es_admin(h, usuario)
    c["presets"] = config.PRESETS
    c["archivo"] = str(config.ARCHIVO)
    c["datos"] = str(config.DATOS)
    return c


@ruta("POST", "/api/config/detectar")
def r_config_detectar(usuario, q, d, h):
    """Busca servidores de IA en este PC y prueba los presets remotos (otro PC de tu red)."""
    if not es_admin(h, usuario):
        return {"error": "Solo el administrador de esta Academia puede cambiar la IA."}
    import urllib.request as ur

    def modelos(url):
        try:
            with ur.urlopen(f"{url}/v1/models", timeout=4) as r:
                return [m.get("id") for m in json.loads(r.read()).get("data", [])]
        except Exception:
            return None
    out = []
    for nombre, url in config.SERVIDORES_LOCALES:
        m = modelos(url)
        if m is not None:
            out.append({"nombre": nombre, "url": url, "modelos": m, "lugar": "este PC"})
    for p in config.PRESETS.values():
        if p.get("modo") == "remoto":
            m = modelos(p["ia_url"].rstrip("/"))
            out.append({"nombre": p.get("nombre_preset", p["ia_url"]), "url": p["ia_url"], "modelos": m or [],
                        "lugar": "tailnet", "disponible": m is not None})
    return {"servidores": out}


@ruta("GET", "/api/version")
def r_version(usuario, q, d, h):
    """Versión del código (git) y si hay una más nueva en GitHub."""
    def git(*a):
        try:
            r = subprocess.run(["git", "-c", f"safe.directory={RAIZ}", *a], cwd=RAIZ, capture_output=True, text=True, timeout=25)
            return r.stdout.strip() if r.returncode == 0 else None
        except Exception:
            return None
    actual = git("log", "-1", "--format=%h|%cI|%s")
    if not actual:
        return {"git": False, "version": config.VERSION, "docker": Path("/.dockerenv").exists()}
    h_, fecha, msg = actual.split("|", 2)
    info = {"git": True, "version": config.VERSION, "commit": h_, "fecha": fecha, "mensaje": msg, "rama": git("rev-parse", "--abbrev-ref", "HEAD"),
            "remoto": git("remote", "get-url", "origin"), "cambios_locales": bool(git("status", "--porcelain", "--untracked-files=no"))}
    if q.get("buscar"):
        ok = git("fetch", "-q", "origin") is not None
        atras = git("rev-list", "--count", "HEAD..@{u}") if ok else None
        adelante = git("rev-list", "--count", "@{u}..HEAD") if ok else None
        nuevos = git("log", "--format=%h %s", "HEAD..@{u}") if ok else None
        info.update({"buscado": ok, "atras": int(atras or 0), "adelante": int(adelante or 0),
                     "novedades": (nuevos or "").splitlines()[:15]})
    return info


@ruta("POST", "/api/actualizar")
def r_actualizar(usuario, q, d, h):
    """git pull y reinicio del servidor. Tus datos (datos/) no se tocan."""
    if not es_admin(h, usuario):
        return {"error": "Solo el administrador de esta Academia puede actualizarla."}
    if ia.cola.actual or ia.cola._h:
        return {"error": "La IA está trabajando; actualiza cuando termine (mira la barra de arriba)."}
    r = subprocess.run(["git", "-c", f"safe.directory={RAIZ}", "pull", "--ff-only"], cwd=RAIZ,
                       capture_output=True, text=True, timeout=120)
    if r.returncode != 0:
        return {"error": "No se pudo actualizar: " + (r.stderr or r.stdout).strip()[-400:]}

    def reiniciar():
        time.sleep(1.5)
        os.execv(sys.executable, [sys.executable] + sys.argv)   # vuelve a arrancar con el código nuevo
    threading.Thread(target=reiniciar, daemon=True).start()
    return {"ok": True, "salida": r.stdout.strip()[-400:]}


@ruta("POST", "/api/config")
def r_config_guardar(usuario, q, d, h):
    if not es_admin(h, usuario):
        return {"error": "Solo el administrador de esta Academia puede cambiar la IA."}
    validas = {"modo", "ia_url", "modelo", "modelo_ligero", "searx_url", "aigate_url", "permitir_interrumpir", "nombre",
               "trabajos_paralelos", "trabajos_nube", "noticias_a_fondo_por_persona", "lecciones_adelantadas", "regiones_por_defecto"}
    if "lecciones_adelantadas" in d:
        d["lecciones_adelantadas"] = max(0, min(6, int(d["lecciones_adelantadas"] or 0)))
    if "noticias_a_fondo_por_persona" in d:
        d["noticias_a_fondo_por_persona"] = max(1, min(60, int(d["noticias_a_fondo_por_persona"] or 15)))
    if "regiones_por_defecto" in d:
        conocidas = nt.config()["regiones"]
        d["regiones_por_defecto"] = {k: max(0, min(3, int(v))) for k, v in dict(d["regiones_por_defecto"] or {}).items()
                                     if k in conocidas} or {nt.GLOBAL: 2}
    if "trabajos_nube" in d:
        d["trabajos_nube"] = max(0, min(ia.MAX_NUBE, int(d["trabajos_nube"] or 0)))
    if "trabajos_paralelos" in d:
        d["trabajos_paralelos"] = max(1, min(ia.MAX_PARALELOS, int(d["trabajos_paralelos"] or 1)))
    config.C = config.guardar({k: v for k, v in d.items() if k in validas})
    return {"ok": True, "config": config.C}


# ------------------------------------------------------------- auto-escaneo (se borra solo a las 24 h)
@ruta("GET", "/api/escaneo")
def r_escaneo(usuario, q, d, h):
    if not es_admin(h, usuario):
        return {"error": "Solo el administrador de esta Academia puede ver el escaneo del PC."}
    return {"guardado": escaneo.leer(config.DATOS), "duracion_h": escaneo.DURACION // 3600}


@ruta("POST", "/api/escaneo")
def r_escaneo_hacer(usuario, q, d, h):
    """Escanea el PC (solo con confirmación explícita) y recomienda una configuración."""
    if not es_admin(h, usuario):
        return {"error": "Solo el administrador de esta Academia puede escanear el PC."}
    if d.get("confirmar") is not True:
        return {"error": "Falta tu confirmación (sí/no) para escanear."}
    e = escaneo.escanear(config.DATOS)
    rec = escaneo.recomendar(e, config.C)
    escaneo.guardar(config.DATOS, e, rec)
    return {"guardado": escaneo.leer(config.DATOS), "duracion_h": escaneo.DURACION // 3600}


@ruta("POST", "/api/escaneo/aplicar")
def r_escaneo_aplicar(usuario, q, d, h):
    if not es_admin(h, usuario):
        return {"error": "Solo el administrador de esta Academia puede cambiar la configuración."}
    if d.get("confirmar") is not True:
        return {"error": "Falta tu confirmación (sí/no) para aplicar."}
    g = escaneo.leer(config.DATOS)
    if not g:
        return {"error": "No hay un escaneo reciente (se borran a las 24 h). Vuelve a escanear."}
    config.C = config.guardar(g["recomendacion"]["config"])
    return {"ok": True, "config": config.C}


@ruta("DELETE", "/api/escaneo")
def r_escaneo_borrar(usuario, q, d, h):
    if not es_admin(h, usuario):
        return {"error": "Solo el administrador."}
    escaneo.purgar(config.DATOS, forzar=True)
    return {"ok": True}


@ruta("POST", "/api/config/probar")
def r_config_probar(usuario, q, d, h):
    """Prueba la conexión con la IA y el buscador configurados (sin guardar)."""
    if not es_admin(h, usuario):
        return {"error": "Solo el administrador de esta Academia puede cambiar la IA."}
    import urllib.request as ur
    out = {}
    url = (d.get("ia_url") or config.C["ia_url"]).rstrip("/").removesuffix("/v1")
    try:
        with ur.urlopen(f"{url}/v1/models", timeout=8) as r:
            out["modelos"] = [m.get("id") for m in json.loads(r.read()).get("data", [])]
        out["ia"] = True
    except Exception as e:
        out["ia"], out["ia_error"] = False, f"{type(e).__name__}: {e}"
    s_url = (d.get("searx_url") if "searx_url" in d else config.C.get("searx_url")) or ""
    if s_url:
        try:
            with ur.urlopen(f"{s_url.rstrip('/')}/search?q=prueba&format=json", timeout=10) as r:
                out["buscador"] = bool(json.loads(r.read()).get("results") is not None)
        except Exception as e:
            out["buscador"], out["buscador_error"] = False, f"{type(e).__name__}: {e}"
    return out


# ------------------------------------------------------------- API de IA opcional (nube.py)
def _admin_cuenta():
    a = config.C.get("administradores")
    if a:
        return a[0]
    p = permitidos()
    return p[0] if p else (config.C.get("usuario_local") or "")


@ruta("GET", "/api/nube")
def r_nube(usuario, q, d, h):
    admin = es_admin(h, usuario)
    out = {"admin": admin, "yo": nube.resumen_persona(usuario),
           "grupos": {k: v["nombre"] for k, v in nube.GRUPOS.items()}}
    if admin:
        out["config"] = nube.config_admin()
        out["ultimo_error"] = kv_get("nube_ultimo_error")
        out["uso"] = nube.uso_mes()
    else:
        p = nube.proveedor_actual()
        out["config"] = {"configurada": nube.configurada(), "activa": bool(config.C.get("nube_activa")),
                         "proveedor": p["nombre"] if p else "", "modelo": p["modelo"] if p else ""}
    return out


def _solo_admin(h, usuario):
    return None if es_admin(h, usuario) else {"error": "Solo el administrador de esta Academia puede cambiar esto."}


@ruta("POST", "/api/nube/config")
def r_nube_config(usuario, q, d, h):
    if (e := _solo_admin(h, usuario)):
        return e
    try:
        return {"ok": True, "config": nube.guardar_admin(d)}
    except ValueError as ex:
        return {"error": str(ex)}


@ruta("POST", "/api/nube/modelos")
def r_nube_modelos(usuario, q, d, h):
    if (e := _solo_admin(h, usuario)):
        return e
    try:
        return {"modelos": nube.listar_modelos()}
    except Exception as ex:  # noqa: BLE001
        return {"error": f"No pude pedir la lista: {str(ex)[:300]}"}


@ruta("POST", "/api/nube/probar")
def r_nube_probar(usuario, q, d, h):
    if (e := _solo_admin(h, usuario)):
        return e
    try:
        return {"ok": True, **nube.probar(usuario)}
    except Exception as ex:  # noqa: BLE001
        return {"error": f"La prueba falló: {str(ex)[:300]}"}


@ruta("POST", "/api/nube/reanudar")
def r_nube_reanudar(usuario, q, d, h):
    if not es_admin(h, usuario):
        return {"error": "Solo el administrador puede hacerlo."}
    return nube.reanudar()


@ruta("POST", "/api/nube/yo")
def r_nube_yo(usuario, q, d, h):
    try:
        nube.guardar_persona(usuario, d)
    except ValueError as ex:
        return {"error": str(ex)}
    return {"ok": True, "yo": nube.resumen_persona(usuario)}


# ------------------------------------------------------------- avisos opcionales (avisos.py)
def resumen_aviso(u):
    """Cantidades de hoy (nada de contenido) para el recordatorio de una persona."""
    perfil = perfil_de(u)
    _, venc, nuevas = cola_repaso(u, perfil)
    plan = ad.plan_del_dia(u, perfil)
    areas, avs = cur.areas(u), cur.avances(u)
    temas = [x for x in ([_tarjeta_tema(t, u, areas, avs, "x") for t in plan["recuperar"] + plan["temas"] + plan["extra"]]) if x]
    pend = [t for t in temas if not t["hecho"]]
    corta = int(perfil.get("sesion_corta") or 0)
    return {"minutos": corta or int(perfil.get("minutos_dia") or 60), "vencidas": venc, "nuevas": nuevas,
            "lecciones": min(len(pend), 1 if corta else len(pend)), "siguiente": pend[0]["t"] if pend else ""}


@ruta("GET", "/api/avisos")
def r_avisos(usuario, q, d, h):
    adm = avisos.admin_publico()
    out = {"ajustes": avisos.ajustes(usuario), "canales": avisos.CANALES,
           "telegram_listo": adm["tiene_token"], "bot": adm["bot"], "ntfy_url": adm["ntfy_url"],
           "error": kv_get(f"aviso_error:{usuario}"), "admin": es_admin(h, usuario)}
    if out["admin"]:
        out["config"] = adm
    return out


@ruta("POST", "/api/avisos/admin")
def r_avisos_admin(usuario, q, d, h):
    if (e := _solo_admin(h, usuario)):
        return e
    try:
        return {"ok": True, "config": avisos.guardar_admin(d)}
    except ValueError as ex:
        return {"error": str(ex)}


@ruta("POST", "/api/avisos")
def r_avisos_guardar(usuario, q, d, h):
    try:
        return {"ok": True, "ajustes": avisos.guardar(usuario, d)}
    except ValueError as ex:
        return {"error": str(ex)}


@ruta("POST", "/api/avisos/tema")
def r_avisos_tema(usuario, q, d, h):
    return {"tema": avisos.nuevo_tema_ntfy()}


@ruta("POST", "/api/avisos/codigo")
def r_avisos_codigo(usuario, q, d, h):
    return avisos.codigo_vinculo(usuario)


@ruta("POST", "/api/avisos/vincular")
def r_avisos_vincular(usuario, q, d, h):
    try:
        return {"ok": True, **avisos.vincular_telegram(usuario)}
    except (ValueError, RuntimeError) as ex:
        return {"error": str(ex)}


@ruta("POST", "/api/avisos/prueba")
def r_avisos_prueba(usuario, q, d, h):
    try:
        return avisos.enviar_prueba(usuario)
    except Exception as ex:  # noqa: BLE001
        return {"error": f"No se pudo enviar: {str(ex)[:200]}"}



@ruta("GET", "/api/ia")
def r_ia(usuario, q, d, h):
    return estado_ia(usuario)


_MUESTRAS = {}   # pid -> (tiempo, ticks de CPU) para calcular el % entre una consulta y la siguiente


def _uso_proceso(pid):
    """CPU (% de un núcleo, como top) y RAM de un proceso, leyendo /proc (solo Linux)."""
    try:
        campos = Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()
        ticks = int(campos[11]) + int(campos[12])
        rss = int(campos[21]) * os.sysconf("SC_PAGE_SIZE")
    except (OSError, IndexError, ValueError):
        return None
    ahora = time.time()
    antes = _MUESTRAS.get(pid)
    _MUESTRAS[pid] = (ahora, ticks)
    cpu = None
    if antes and ahora > antes[0]:
        cpu = round((ticks - antes[1]) / os.sysconf("SC_CLK_TCK") / (ahora - antes[0]) * 100)
    return {"cpu": cpu, "ram_mb": round(rss / 1048576)}


_CPU_TOTAL = {}


def _sistema():
    """Uso del PC completo: CPU (% de todos los núcleos), RAM, swap y GPU NVIDIA (si hay). Solo Linux."""
    s = {}
    try:
        v = [int(x) for x in Path("/proc/stat").read_text().split("\n", 1)[0].split()[1:]]
        ocio, total = v[3] + v[4], sum(v[:8])
        antes = _CPU_TOTAL.get("m")
        _CPU_TOTAL["m"] = (ocio, total)
        s["cpu"] = round(100 * (1 - (ocio - antes[0]) / (total - antes[1]))) if antes and total > antes[1] else None
        mem = dict(l.split(":", 1) for l in Path("/proc/meminfo").read_text().splitlines())
        kb = lambda k: int(mem[k].split()[0])
        s["ram_total"] = round(kb("MemTotal") / 1048576, 1)
        s["ram_usada"] = round((kb("MemTotal") - kb("MemAvailable")) / 1048576, 1)
        s["swap_usada"] = round((kb("SwapTotal") - kb("SwapFree")) / 1048576, 1)
    except Exception:
        pass
    try:
        out = subprocess.run(["nvidia-smi", "--query-gpu=utilization.gpu,memory.used,memory.total,temperature.gpu",
                              "--format=csv,noheader,nounits"], capture_output=True, text=True, timeout=4).stdout
        u, usada, total, temp = [x.strip() for x in out.splitlines()[0].split(",")]
        s["gpu"] = {"uso": int(u), "vram": round(int(usada) / 1024, 1), "vram_total": round(int(total) / 1024), "temp": int(temp)}
    except Exception:
        pass
    return s


def _gpu_por_proceso():
    """{pid: {"vram_mb", "gpu"}} de los procesos que usan la GPU NVIDIA (vacío si no hay)."""
    out = {}
    try:
        apps = subprocess.run(["nvidia-smi", "--query-compute-apps=pid,used_memory", "--format=csv,noheader,nounits"],
                              capture_output=True, text=True, timeout=4).stdout
        for l in apps.splitlines():
            pid, mb = [x.strip() for x in l.split(",")[:2]]
            out.setdefault(int(pid), {})["vram_mb"] = int(mb) if mb.isdigit() else None
        pm = subprocess.run(["nvidia-smi", "pmon", "-c", "1", "-s", "u"], capture_output=True, text=True, timeout=5).stdout
        for l in pm.splitlines():
            c = l.split()
            if l.startswith("#") or len(c) < 5 or not c[1].isdigit():
                continue
            out.setdefault(int(c[1]), {})["gpu"] = int(c[3]) if c[3].isdigit() else 0
    except Exception:
        pass
    return out


def _modelos_cargados_uso():
    """Cada modelo cargado en el servidor de IA (el de la Academia y los de otras apps, p. ej. Hermes) con su
    CPU, RAM, VRAM y % de GPU. llama-swap dice en /running a qué puerto arrancó cada uno."""
    try:
        corriendo = ia._get_json(f"{ia.LLAMA()}/running", 3).get("running", [])
    except Exception:
        return []
    gpu, out = _gpu_por_proceso(), []
    for m in corriendo:
        pid = _pid_en_puerto(m.get("proxy", "").rsplit(":", 1)[-1])
        u = (_uso_proceso(pid) or {}) if pid else {}
        g = gpu.get(pid, {})
        out.append({"modelo": m.get("model"), "nuestro": m.get("model") == config.C.get("modelo"),
                    "cpu": u.get("cpu"), "ram_mb": u.get("ram_mb"), "vram_mb": g.get("vram_mb"), "gpu": g.get("gpu")})
    return out


def _pid_en_puerto(puerto):
    if not puerto:
        return None
    for p in Path("/proc").iterdir():
        if not p.name.isdigit():
            continue
        try:
            cmd = (p / "cmdline").read_bytes().split(b"\0")
        except OSError:
            continue
        if cmd and cmd[0].endswith(b"llama-server") and b"--port" in cmd and cmd[cmd.index(b"--port") + 1] == puerto.encode():
            return int(p.name)
    return None


@ruta("GET", "/api/cola")
def r_cola(usuario, q, d, h):
    """Qué está haciendo la IA para la Academia y qué viene después (se consulta cada 10 s)."""
    lista = ia.cola.lista()
    trabajos = [trabajo_visible(t, usuario, i) for i, t in enumerate(lista)]
    adm = es_admin(h, usuario)
    esperan = [t for t in lista if t.estado == "cola"]
    for v, t in zip(trabajos, lista):   # reordenar: solo lo que espera, y solo lo propio (el administrador, todo)
        grupo = [x for x in esperan if x.prioridad == t.prioridad]
        v["mid"] = t.id if t.estado == "cola" and (adm or t.usuario == usuario) else None
        v["primero"] = bool(grupo) and grupo[0] is t
        v["ultimo"] = bool(grupo) and grupo[-1] is t
    recientes = sorted((t for t in ia.cola.trabajos.values()
                        if t.usuario == usuario and t.terminado and t.estado == "listo"),
                       key=lambda t: -t.terminado)[:8]
    fallidos = sorted((t for t in ia.cola.trabajos.values() if t.estado == "error" and puede_reintentar(t, usuario)),
                      key=lambda t: -(t.terminado or 0))
    recursos = {"academia": _uso_proceso(os.getpid())}
    if sys.platform.startswith("linux") and config.C.get("modo") != "remoto":
        recursos["sistema"] = _sistema()
        recursos["modelos"] = _modelos_cargados_uso()
    return {"ia": estado_ia(usuario) | {"otros": ia.otros_modelos()}, "trabajos": trabajos,
            "recientes": [trabajo_visible(t, usuario) | {"terminado": t.terminado, "error": t.error} for t in recientes],
            "fallidos": [trabajo_visible(t, usuario) | {"id": t.id, "terminado": t.terminado, "error": t.error,
                                                         "reintentos": getattr(t, "reintentos", 0)} for t in fallidos],
            "recursos": recursos, "nucleos": os.cpu_count(), "hora": time.time(), "admin": adm}


@ruta("POST", "/api/cola/mover")
def r_cola_mover(usuario, q, d, h):
    """Reordena una tarea que espera: primero | ultimo | subir | bajar | urgente | quitar. Cada persona mueve solo lo suyo;
    el administrador, cualquiera (también las tareas comunes del sistema)."""
    x = ia.cola.trabajos.get(d.get("id"))
    if not x or x.estado != "cola" or not (x.usuario == usuario or es_admin(h, usuario)):
        return {"ok": False, "error": "esa tarea ya no está esperando en la cola o no es tuya"}
    accion = d.get("accion")
    if accion == "quitar":
        quitados, _ = ia.cola.vaciar(lambda t: t.id == x.id)
        return {"ok": bool(quitados)}
    return {"ok": ia.cola.mover(x.id, accion)}


@ruta("POST", "/api/cola/limpiar")
def r_cola_limpiar(usuario, q, d, h):
    """Vacía lo que ESPERA en la cola (no lo que corre ahora). Cada persona limpia solo lo suyo; con `todos` el
    administrador limpia también lo de las demás personas y las tareas comunes del sistema. `fallidos`: además olvida
    las que fallaron."""
    todos = bool(d.get("todos")) and es_admin(h, usuario)
    quitados, olvidados = ia.cola.vaciar(lambda t: todos or t.usuario == usuario, fallidos=bool(d.get("fallidos")))
    return {"ok": True, "quitados": quitados, "fallidos_olvidados": olvidados}


def foto_salud():
    """Estado de la Academia por dentro, para el tablero 🩺 y para el vigía externo (`vigia.py`). Del equipo, no de una
    persona: solo la ve el administrador. La misma lista de problemas alimenta la pantalla y la alarma."""
    ahora = time.time()
    trabajos = [{"tipo": t.tipo, "estado": t.estado, "creado": t.creado, "terminado": t.terminado, "inicio": t.inicio}
                for t in list(ia.cola.trabajos.values())]
    sistema = _sistema() if sys.platform.startswith("linux") and config.C.get("modo") != "remoto" else {}
    d = kv_get("salud_diaria", {}) or {}
    ia_ok = None
    if config.C.get("modo") != "remoto":
        try:   # el servidor de IA local (llama-swap) responde en /health
            urllib.request.urlopen(str(config.C.get("ia_url") or "").rstrip("/") + "/health", timeout=3).read()
            ia_ok = True
        except Exception:
            ia_ok = False
    f = {"ahora": ahora, "inicio_servicio": INICIO,
         "diaria": {"programada": ultima_hora_programada(ahora), "ultima": kv_get("diaria_ultima", 0),
                    "inicio": d.get("inicio"), "fin": d.get("fin"), "error": d.get("error")},
         "cola": salud.resumen_cola(trabajos, ahora, perdidos=len(salud.perdidos_visibles())),
         "reinicio": kv_get("cola_reinicio"),
         "sistema": sistema, "ia": {"alcanzable": ia_ok, "modelo": str(ia.MODELO), "cargados": ia.modelos_cargados()},
         "api": {"configurada": bool(nube.configurada()), "gastado_mes_usd": nube.gastado()},
         "base_datos": salud.foto_base_datos(base.RUTA_DB), "disco_libre_gb": salud.disco_libre_gb(config.DATOS)}
    f["problemas"] = salud.evaluar(f)
    return f


INICIO = time.time()


@ruta("GET", "/api/salud")
def r_salud(usuario, q, d, h):
    if not es_admin(h, usuario):
        return {"error": "el tablero de salud es solo del administrador"}
    return foto_salud()


@ruta("GET", "/api/salud/linea_base")
def r_linea_base(usuario, q, d, h):
    """La línea base de uso de ESTA persona (cada perfil ve solo la suya): la primera foto y la de hoy."""
    return salud.linea_base(usuario)


# ------------------------------------------------------------------ F1: eventos y métricas («Qué sabe el sistema de ti»)
@ruta("GET", "/api/metricas")
def r_metricas(usuario, q, d, h):
    """Todas las métricas de ESTA persona con su origen, fórmula, muestra, confianza y lo que ella decidió sobre cada una."""
    eventos.sincronizar()   # al abrir la vista, lo último ya está
    ms = metricas.calcular(usuario)
    return {"metricas": ms, "familias": metricas.FAMILIAS, "eventos": eventos.resumen(usuario),
            "resumen": {"total": len(ms), "usables": sum(1 for m in ms if m["usable"]),
                        "sin_datos": sum(1 for m in ms if m["confianza"] == "sin datos"),
                        "baja": sum(1 for m in ms if m["confianza"] == "baja")}}


@ruta("POST", "/api/metricas/ajustar")
def r_metricas_ajustar(usuario, q, d, h):
    """La persona corrige al sistema: {id, estado: mal|ignorar|ok, nota} o {familia, apagada: bool}."""
    try:
        if d.get("familia"):
            return metricas.apagar_familia(usuario, str(d["familia"]), bool(d.get("apagada", True)))
        return metricas.ajustar(usuario, str(d.get("id", "")), str(d.get("estado", "")), d.get("nota", ""))
    except ValueError as e:
        return {"error": str(e)}


@ruta("GET", "/api/metricas/tendencia")
def r_metricas_tendencia(usuario, q, d, h):
    return {"id": q.get("id", ""), "serie": metricas.tendencia(usuario, q.get("id", ""))}


@ruta("POST", "/api/evento")
def r_evento(usuario, q, d, h):
    """Eventos indirectos que solo ve la interfaz (tiempo en una vista, a dónde fue después). Lista blanca de tipos."""
    return {"ok": True, "guardados": eventos.registrar_cliente(usuario, d.get("eventos"))}


_ultimo_latido = {}


@ruta("POST", "/api/tiempo")
def r_tiempo(usuario, q, d, h):
    """Segundos de estudio ACTIVO (la interfaz solo cuenta con acción real o audio sonando). Con varias pestañas o
    aparatos abiertos a la vez no se suma doble: nunca más segundos que los pasados desde el latido anterior."""
    ahora = time.time()
    s = max(0, min(float(d.get("segundos", 0)), 600))
    previo = _ultimo_latido.get(usuario)
    if previo and ahora - previo < s:
        s = max(0, ahora - previo)
    _ultimo_latido[usuario] = ahora
    if s:
        registrar(usuario, "tiempo", d.get("tema"), d.get("area"), s,
                  {"metodo": d.get("metodo")} if d.get("metodo") else None)
    return {"ok": True}


@ruta("POST", "/api/lectura/sesion")
def r_lectura_sesion(usuario, q, d, h):
    lectura.guardar(usuario, d)
    return {"ok": True}


# ------------------------------------------------------------ currículo
@ruta("GET", "/api/mapa")
def r_mapa(usuario, q, d, h):
    return {"areas": cur.mapa(usuario), "niveles": cur.NIVELES}


@ruta("GET", "/api/tema")
def r_tema(usuario, q, d, h):
    tid = q.get("id", "")
    t = cur.tema(tid, usuario)
    if not t:
        return {"error": "tema desconocido"}
    a = cur.areas(usuario)[t["area"]]
    m = cur.modulo(t["modulo"], usuario)
    lecc = fila("SELECT * FROM leccion WHERE usuario=? AND tema=?", (usuario, tid))
    av = fila("SELECT * FROM avance WHERE usuario=? AND tema=?", (usuario, tid))
    pend = next((x.publico() for x in ia.cola.trabajos.values()
                 if x.tipo == "leccion" and x.etiqueta == tid and x.usuario == usuario
                 and x.estado in ("cola", "corriendo", "conflicto")), None)
    i = t["i"]
    return {"tema": t, "area": {"id": a["id"], "nombre": a["nombre"], "icono": a.get("icono"),
                                "color": a.get("color"), "idioma": a.get("idioma")},
            "modulo": {"ref": m["ref"], "t": m["t"], "nivel": m["nivel"],
                       "temas": [{"id": x["id"], "t": x["t"]} for x in m["temas_obj"]]},
            "anterior": m["temas_obj"][i - 1]["id"] if i > 0 else None,
            "siguiente": m["temas_obj"][i + 1]["id"] if i + 1 < len(m["temas_obj"]) else None,
            "leccion": {"contenido": lecc["contenido"], "ejercicios": json.loads(lecc["ejercicios"] or "null"),
                        "fuentes": vf.marcar_fuentes(json.loads(lecc["fuentes"] or "[]")), "creado": lecc["creado"],
                        "version": lecc["version"] or 1, "completa": lecc["completa"] != 0,
                        "partes": len((json.loads(lecc["plan"]) or {}).get("partes", [])) if lecc["plan"] else 0,
                        "anteriores": fila("SELECT COUNT(*) n FROM leccion_anterior WHERE usuario=? AND tema=?",
                                                          (usuario, tid))["n"]}
            if lecc else None,
            "avance": av, "trabajo": pend,
            "tarjetas": fila("SELECT COUNT(*) n FROM tarjeta WHERE usuario=? AND tema=?", (usuario, tid))["n"],
            "formato": aa.formato(usuario), "partes": aa.partes_de(usuario, tid),
            "verificacion": vf.de(usuario, f"tema:{tid}"),
            "verificando": _verif_en_cola(usuario, f"tema:{tid}") is not None}


@ruta("POST", "/api/leccion")
def r_leccion(usuario, q, d, h):
    tid = d["tema"]
    if not cur.tema(tid, usuario):
        return {"error": "tema desconocido"}
    for x in ia.cola.trabajos.values():
        if x.tipo == "leccion" and x.etiqueta == tid and x.usuario == usuario and x.estado in ("cola", "corriendo", "conflicto"):
            if x.prioridad > 0 and x.estado == "cola":   # estaba en fondo: subirla
                ia.cola.subir(x)
            if d.get("permiso"):
                x.permiso = d["permiso"]
            return trabajo_json(x)
    perfil = perfil_ia(usuario)
    # Lección nueva de alguien que pidió «todo a máxima profundidad»: nace así (las ya escritas no se tocan al abrirlas)
    maxima = bool(d.get("maxima")) or (bool(perfil.get("dia_maxima")) and not d.get("forzar") and not fila(
        "SELECT 1 FROM leccion WHERE usuario=? AND tema=? AND completa!=0", (usuario, tid)))
    t = ia.nuevo("leccion", lambda ctx: lec.generar_leccion(ctx, tid, usuario, perfil, d.get("forzar"), maxima),
                 0, usuario, tid)
    t.permiso = d.get("permiso")
    return trabajo_json(t)


def profundizar_lecciones(usuario, limite=None, prioridad=1):
    """Reescribe a fondo (versión 2) las lecciones antiguas, en segundo plano."""
    perfil = perfil_ia(usuario)
    viejas = [r["tema"] for r in filas("SELECT tema FROM leccion WHERE usuario=? AND IFNULL(version,1) < ? ORDER BY creado DESC",
                                       (usuario, lec.VERSION_LECCION))]
    n = 0
    for tid in viejas[:limite] if limite else viejas:
        if not cur.tema(tid, usuario) or any(x.tipo == "leccion" and x.etiqueta == tid and x.usuario == usuario and x.estado in ("cola", "corriendo", "conflicto")
                                             for x in ia.cola.trabajos.values()):
            continue
        ia.nuevo("leccion", lambda ctx, tid=tid: lec.generar_leccion(ctx, tid, usuario, perfil, True), prioridad, usuario, tid)
        n += 1
    return n


def _leccion_en_cola(tid, usuario):
    return any(x.tipo == "leccion" and x.etiqueta == tid and x.usuario == usuario and x.estado in ("cola", "corriendo", "conflicto")
               for x in ia.cola.trabajos.values())


@ruta("GET", "/api/modulo/estado")
def r_modulo_estado(usuario, q, d, h):
    """Por módulo del área: cuántas lecciones hay listas, cuántas a máxima profundidad y cuántas en cola."""
    area = cur.areas(usuario).get(q.get("area", ""))
    if not area:
        return {"error": "área desconocida"}
    lecs = {r["tema"]: r for r in filas("SELECT tema, version, completa, ejercicios IS NOT NULL ej FROM leccion WHERE usuario=?",
                                        (usuario,))}
    out = {}
    for m in area["modulos"]:
        ids = [t["id"] for t in m["temas_obj"]]
        out[m["ref"]] = {"temas": len(ids),
                         "listas": sum(1 for i in ids if i in lecs and lecs[i]["completa"] != 0 and lecs[i]["ej"]),
                         "maximas": sum(1 for i in ids if i in lecs and (lecs[i]["version"] or 1) >= lec.VERSION_MAXIMA
                                        and lecs[i]["completa"] != 0),
                         "en_cola": sum(1 for i in ids if _leccion_en_cola(i, usuario))}
    return {"modulos": out}


@ruta("POST", "/api/modulo/preparar")
def r_modulo_preparar(usuario, q, d, h):
    """📥 Prepara TODAS las lecciones de un módulo (de fondo, en orden). Con «maxima»: 🔬 las reescribe a máxima
    profundidad (versión 3: más partes, fuentes y papers, derivaciones completas e historia de cada idea)."""
    m = cur.modulo(d.get("ref", ""), usuario)
    if not m:
        return {"error": "módulo desconocido"}
    tids = [t["id"] for t in m["temas_obj"]]
    if not d.get("maxima"):
        return {"encoladas": preparar_lecciones(usuario, tids, 1), "temas": len(tids)}
    perfil = perfil_ia(usuario)
    n = 0
    for tid in tids:
        v = fila("SELECT version, completa FROM leccion WHERE usuario=? AND tema=?", (usuario, tid))
        if (v and (v["version"] or 1) >= lec.VERSION_MAXIMA and v["completa"] != 0) or _leccion_en_cola(tid, usuario):
            continue
        ia.nuevo("leccion", lambda ctx, tid=tid: lec.generar_leccion(ctx, tid, usuario, perfil, True, True), 1, usuario, tid)
        n += 1
    return {"encoladas": n, "temas": len(tids)}


@ruta("POST", "/api/lecciones/profundizar")
def r_profundizar(usuario, q, d, h):
    return {"encoladas": profundizar_lecciones(usuario), "pendientes": fila(
        "SELECT COUNT(*) n FROM leccion WHERE usuario=? AND IFNULL(version,1) < ?", (usuario, lec.VERSION_LECCION))["n"]}


@ruta("GET", "/api/leccion/anterior")
def r_leccion_anterior(usuario, q, d, h):
    r = fila("SELECT * FROM leccion_anterior WHERE usuario=? AND tema=? ORDER BY id DESC LIMIT 1",
             (usuario, q.get("tema", "")))
    return {"contenido": r["contenido"], "creado": r["creado"], "version": r["version"]} if r else {"contenido": None}


@ruta("POST", "/api/mercado")
def r_mercado(usuario, q, d, h):
    """Renueva el referente de lo que pide hoy el mercado para un área (búsqueda web + IA)."""
    area = d.get("area", "")
    if area not in cur.areas(usuario):
        return {"error": "área desconocida"}
    for x in ia.cola.trabajos.values():
        if x.tipo == "mercado" and x.etiqueta == area and x.estado in ("cola", "corriendo", "conflicto"):
            if x.prioridad > 0 and x.estado == "cola":
                ia.cola.subir(x)
            return trabajo_json(x)
    t = ia.nuevo("mercado", lambda ctx: mercado.referente(ctx, area, usuario), 1 if d.get("fondo") else 0, usuario, area)
    t.permiso = d.get("permiso")
    return trabajo_json(t)


@ruta("GET", "/api/ciencia")
def r_ciencia(usuario, q, d, h):
    """Documentos científicos de un módulo (ref) o de una búsqueda libre (q, mejor en inglés)."""
    if q.get("q"):
        return {"consulta": q["q"], "papers": ciencia.buscar(q["q"], 8)}
    ref = q.get("ref", "")
    r = ciencia.para_modulo(ref, 6)
    if not r["consulta"] and cur.modulo(ref, usuario):
        area = ref.split(".")[0]
        if not any(x.tipo == "ciencia" and x.estado in ("cola", "corriendo", "conflicto") for x in ia.cola.trabajos.values()):
            t = ia.nuevo("ciencia", lambda ctx: ciencia.traducir_modulos(ctx, usuario, area), 0, usuario, area)
            r["trabajo"] = t.id
    return r


@ruta("GET", "/api/prioridad")
def r_prioridad(usuario, q, d, h):
    """Para otras apps de IA de este PC que comparten la GPU (p. ej. un servicio de memoria): si una persona espera
    una tarea no deberían empezar trabajo nuevo; con trabajo del día (prioridad 1) o masivo (2+) pueden dejarle a la
    Academia una ventana entre sus tareas."""
    pend = [t for t in list(ia.cola.trabajos.values()) if t.estado in ("cola", "corriendo", "conflicto")]
    return {"usuario_esperando": ia.usuario_esperando(),
            "diaria": sum(1 for t in pend if t.prioridad == 1),
            "fondo": sum(1 for t in pend if t.prioridad >= 2),
            "corriendo": len(ia.cola.actuales)}


@ruta("GET", "/api/trabajo")
def r_trabajo(usuario, q, d, h):
    t = ia.cola.trabajos.get(q.get("id", ""))
    if t and t.usuario in (None, usuario):   # solo los propios
        return t.publico()
    return ia.resultado_guardado(q.get("id", ""), usuario) or {"estado": "desconocido"}


def puede_reintentar(t, usuario):
    """Cada perfil reintenta lo suyo y lo común (noticias, mercado…); nunca lo de otra persona."""
    return t.usuario in (usuario, None)


@ruta("POST", "/api/trabajo/reintentar")
def r_reintentar(usuario, q, d, h):
    ids = d.get("ids") or ([d["id"]] if d.get("id") else [])
    n = 0
    for tid in ids:
        t = ia.cola.trabajos.get(tid)
        if t and puede_reintentar(t, usuario) and ia.cola.reintentar(t):
            n += 1
    return {"ok": True, "reintentados": n}


@ruta("POST", "/api/trabajo/decidir")
def r_decidir(usuario, q, d, h):
    x = ia.cola.trabajos.get(d["id"])
    if not x or x.usuario not in (None, usuario):
        return {"estado": "desconocido"}
    t = ia.cola.decidir(d["id"], d["permiso"])
    return t.publico() if t else {"estado": "desconocido"}


@ruta("POST", "/api/visto")
def r_visto(usuario, q, d, h):
    t = cur.tema(d["tema"], usuario)
    cur.marcar(usuario, d["tema"], visto=time.time())
    registrar(usuario, "leccion", d["tema"], t["area"] if t else None)
    lecc = fila("SELECT ejercicios FROM leccion WHERE usuario=? AND tema=?", (usuario, d["tema"]))
    n = 0
    if lecc and d.get("tarjetas", True):
        ej = json.loads(lecc["ejercicios"] or "{}")
        a = cur.areas(usuario)[t["area"]]
        n = agregar_tarjetas(usuario, ej.get("tarjetas", []), d["tema"], t["area"], a.get("idioma"))
    return {"ok": True, "tarjetas": n}


@ruta("POST", "/api/corregir")
def r_corregir(usuario, q, d, h):
    t = ia.nuevo("corregir", lambda ctx: lec.corregir(ctx, d["tema"], usuario, d.get("pregunta", ""),
                                                      d.get("modelo", ""), d["respuesta"], d.get("modo", "abierta")),
                 0, usuario, d["tema"])
    t.permiso = d.get("permiso")
    return trabajo_json(t)


@ruta("POST", "/api/resultado")
def r_resultado(usuario, q, d, h):
    t = cur.tema(d["tema"], usuario)
    campos = {k: float(d[k]) for k in ("quiz", "feynman") if d.get(k) is not None}
    nuevo = cur.marcar(usuario, d["tema"], **campos)
    for k, v in campos.items():
        registrar(usuario, k, d["tema"], t["area"] if t else None, v)
    return {"ok": True, "avance": nuevo}


@ruta("POST", "/api/confianza")
def r_confianza(usuario, q, d, h):
    """Confianza declarada ANTES de ver si acertó («seguro», «dudo», «adivino») y el acierto: mide si tu seguridad coincide
    con la realidad (Brier). Solo registra: no cambia el dominio ni el repaso."""
    p = ad.NIVELES_CONFIANZA.get(str(d.get("confianza", "")))
    t = cur.tema(d.get("tema", ""), usuario)
    if p is None or not t:
        return {"error": "confianza o tema no válidos"}
    registrar(usuario, "calibracion", t["id"], t["area"], 1.0 if d.get("acierto") else 0.0,
              {"p": p, "nivel": d["confianza"], "origen": str(d.get("origen") or "quiz")[:20]})
    return {"ok": True}


@ruta("POST", "/api/dominado")
def r_dominado(usuario, q, d, h):
    cur.marcar(usuario, d["tema"], estado="dominado" if d.get("si", True) else "visto")
    return {"ok": True}


def _prueba(usuario, pid):
    r = fila("SELECT * FROM prueba_nivel WHERE id=? AND usuario=?", (int(pid), usuario))
    if not r:
        return None
    return {"id": r["id"], "ref": r["ref"], "datos": json.loads(r["datos"]), "respuestas": json.loads(r["respuestas"] or "{}"),
            "estado": r["estado"], "resultado": json.loads(r["resultado"]) if r["resultado"] else None,
            "creada": r["creada"], "terminada": r["terminada"]}


@ruta("POST", "/api/prueba")
def r_prueba(usuario, q, d, h):
    """Si ya hay una prueba de ese módulo sin terminar, se retoma (desde cualquier equipo); si se está preparando,
    se devuelve ese trabajo; si no, se prepara una nueva."""
    ref = d.get("ref", "")
    if not cur.modulo(ref, usuario):
        return {"error": "módulo desconocido"}
    abierta = fila("SELECT id FROM prueba_nivel WHERE usuario=? AND ref=? AND estado='lista' ORDER BY id DESC LIMIT 1",
                   (usuario, ref))
    if abierta and not d.get("nueva"):
        return {"prueba": abierta["id"]}
    t = next((x for x in ia.cola.trabajos.values() if x.tipo == "prueba" and x.usuario == usuario and x.etiqueta == ref
              and x.estado in ("cola", "corriendo", "conflicto")), None)
    if not t:
        if abierta:   # pidió una nueva: la anterior sin terminar se descarta
            ejecutar("UPDATE prueba_nivel SET estado='descartada' WHERE id=?", (abierta["id"],))
        t = ia.nuevo("prueba", lambda ctx: lec.prueba_nivel(ctx, ref, usuario), 0, usuario, ref)
    t.permiso = d.get("permiso")
    return trabajo_json(t)


@ruta("GET", "/api/prueba")
def r_prueba_ver(usuario, q, d, h):
    x = _prueba(usuario, q.get("id")) if str(q.get("id", "")).isdigit() else None
    return x or {"error": "prueba desconocida"}


@ruta("POST", "/api/prueba/respuesta")
def r_prueba_respuesta(usuario, q, d, h):
    """Cada respuesta se guarda al tocarla: cerrar la ventana o cambiar de equipo no pierde nada."""
    x = _prueba(usuario, d.get("id") or 0)
    i, j = d.get("i"), d.get("j")
    if not x or x["estado"] != "lista" or not isinstance(i, int) or not isinstance(j, int) \
            or not 0 <= i < len(x["datos"]["preguntas"]):
        return {"error": "datos inválidos"}
    p_ = x["datos"]["preguntas"][i]
    if str(i) in x["respuestas"]:
        return {"ok": True, "repetida": True, **x["respuestas"][str(i)]}
    x["respuestas"][str(i)] = {"j": j, "ok": j == p_["correcta"], "tema": p_["tema"]}
    ejecutar("UPDATE prueba_nivel SET respuestas=? WHERE id=?", (json.dumps(x["respuestas"]), x["id"]))
    return {"ok": True, **x["respuestas"][str(i)]}


@ruta("GET", "/api/pruebas")
def r_pruebas(usuario, q, d, h):
    out = {"listas": [], "terminadas": [], "preparando": []}
    for r in filas("""SELECT id, ref, datos, respuestas, estado, resultado, creada, terminada FROM prueba_nivel
                      WHERE usuario=? AND estado IN ('lista','terminada') ORDER BY id DESC LIMIT 40""", (usuario,)):
        m = cur.modulo(r["ref"], usuario)
        item = {"id": r["id"], "ref": r["ref"], "modulo": m["t"] if m else r["ref"],
                "area": cur.modulo_area_nombre(r["ref"], usuario), "creada": r["creada"],
                "total": len(json.loads(r["datos"])["preguntas"]), "respondidas": len(json.loads(r["respuestas"] or "{}"))}
        if r["estado"] == "lista":
            out["listas"].append(item)
        else:
            res = json.loads(r["resultado"] or "{}")
            out["terminadas"].append({**item, "terminada": r["terminada"], "aprobado": res.get("aprobado"),
                                      "porcentaje": res.get("porcentaje"), "pasados": len(res.get("pasados", [])),
                                      "pendientes": len(res.get("pendientes", []))})
    out["preparando"] = [{"ref": x.etiqueta, "modulo": (cur.modulo(x.etiqueta, usuario) or {}).get("t", x.etiqueta),
                          "trabajo": x.publico()} for x in ia.cola.trabajos.values()
                         if x.tipo == "prueba" and x.usuario == usuario and x.estado in ("cola", "corriendo", "conflicto")]
    return out


@ruta("GET", "/api/ubicacion/estado")
def r_ubicacion_ver(usuario, q, d, h):
    return {"estado": kv_get(f"ubicacion:{usuario}:{q.get('clave', '')}")}


@ruta("POST", "/api/ubicacion/estado")
def r_ubicacion_guardar(usuario, q, d, h):
    """Dónde va la búsqueda binaria de «Ubícame» (se retoma desde cualquier equipo); estado null = terminada."""
    clave = re.sub(r"[^a-z0-9_.:]", "", str(d.get("clave", "")))[:80]
    if not clave:
        return {"error": "clave inválida"}
    kv_set(f"ubicacion:{usuario}:{clave}", d.get("estado"))
    return {"ok": True}


@ruta("POST", "/api/prueba/resultado")
def r_prueba_res(usuario, q, d, h):
    """95 % o más = módulo superado (todos sus temas probados). Si no, se marcan
    como probados solo los temas con TODAS sus preguntas bien; el resto queda pendiente."""
    guardada = _prueba(usuario, d["id"]) if str(d.get("id", "")).isdigit() else None
    if guardada:
        d["ref"] = guardada["ref"]
        if guardada["estado"] == "terminada" and guardada["resultado"]:
            return guardada["resultado"]
    m = cur.modulo(d["ref"], usuario)
    res = list(guardada["respuestas"].values()) if guardada else d.get("respuestas", [])
    bien = sum(1 for r in res if r.get("ok"))
    total = len(res)
    aprobado = total > 0 and bien / total >= lec.APROBAR_PRUEBA
    por_tema = {}
    for r in res:
        por_tema.setdefault(int(r["tema"]), []).append(bool(r.get("ok")))
    evaluados = set(kv_get(f"prueba_temas:{usuario}:{d['ref']}") or [t["i"] for t in m["temas_obj"]])
    pasados, pendientes = [], []
    for t in m["temas_obj"]:
        if t["i"] not in evaluados:      # ya sabido de un intento anterior: no se toca
            continue
        respuestas = por_tema.get(t["i"], [])
        if aprobado or (respuestas and all(respuestas)):
            cur.marcar(usuario, t["id"], estado="probado", quiz=1.0)
            pasados.append({"id": t["id"], "t": t["t"]})
        else:
            pendientes.append({"id": t["id"], "t": t["t"], "bien": sum(respuestas), "total": len(respuestas)})
    registrar(usuario, "prueba", None, m["area"], bien / max(1, total),
              {"ref": d["ref"], "pasados": len(pasados), "pendientes": len(pendientes)})
    ad.invalidar(usuario)
    out = {"aprobado": aprobado, "bien": bien, "total": total, "porcentaje": bien / max(1, total),
           "minimo": lec.APROBAR_PRUEBA, "pasados": pasados, "pendientes": pendientes}
    if guardada:
        ejecutar("UPDATE prueba_nivel SET estado='terminada', resultado=?, terminada=? WHERE id=?",
                 (json.dumps(out, ensure_ascii=False), time.time(), guardada["id"]))
    return out


# ------------------------------------------------- lectura adaptativa (por partes)
@ruta("POST", "/api/parte")
def r_parte(usuario, q, d, h):
    if not cur.tema(d.get("tema", ""), usuario):
        return {"error": "tema desconocido"}
    try:
        aa.guardar_parte(usuario, d["tema"], int(d["parte"]), d.get("estado"), d.get("segundos"))
    except (ValueError, TypeError, KeyError):
        return {"error": "datos inválidos"}
    ad.invalidar(usuario)
    return {"ok": True}


@ruta("POST", "/api/reexplicar")
def r_reexplicar(usuario, q, d, h):
    if not cur.tema(d.get("tema", ""), usuario) or d.get("estilo") not in aa.ESTILOS:
        return {"error": "datos inválidos"}
    t = aa.reexplicar_trabajo(usuario, perfil_ia(usuario), d["tema"], int(d.get("parte") or 1), d["estilo"],
                              str(d.get("duda") or "")[:600])
    t.permiso = d.get("permiso")
    return trabajo_json(t)


@ruta("POST", "/api/rapida")
def r_rapida(usuario, q, d, h):
    if not cur.tema(d.get("tema", ""), usuario):
        return {"error": "tema desconocido"}
    t = aa.preparar_rapida(usuario, perfil_ia(usuario), d["tema"], 0)
    if not t:
        rap = aa.rapida_de(usuario, d["tema"])
        return {"listo": True, "texto": rap["texto"]} if rap else {"error": "no disponible: la lección aún no está completa o es de idiomas"}
    t.permiso = d.get("permiso")
    return trabajo_json(t)


@ruta("POST", "/api/diagnostico")
def r_diagnostico(usuario, q, d, h):
    if not cur.tema(d.get("tema", ""), usuario):
        return {"error": "tema desconocido"}
    return {"ok": True, "diagnostico": aa.guardar_diagnostico(usuario, d["tema"], int(d.get("bien", 0)),
                                                               int(d.get("total", 0)), d.get("flojas") or [],
                                                               d.get("vistas") or [])}


# ------------------------------------------------- horizonte, ubicación y aprendizaje externo
@ruta("GET", "/api/horizonte")
def r_horizonte(usuario, q, d, h):
    n = max(1, min(int(q.get("enfoque") or 3), 8))
    return aa.horizonte(usuario, perfil_de(usuario), n)


@ruta("POST", "/api/enfoque")
def r_enfoque(usuario, q, d, h):
    """Enfocarse: las áreas elegidas a prioridad 3; las demás activas a `resto` (0 = mantenimiento: sin temas nuevos
    pero sus tarjetas se siguen repasando; 1 = de fondo: avanzan poco).
    Lo pide la persona con un botón; nunca se aplica solo."""
    mias = cur.areas_de(usuario)
    elegidas = [a for a in d.get("areas", []) if a in mias]
    if not elegidas:
        return {"error": "elige al menos un área"}
    resto = max(0, min(1, int(d.get("resto", 0))))
    p = perfil_de(usuario)
    metas = cur.areas_de_metas(usuario)
    for a_id, a in cur.areas(usuario).items():
        if a_id not in mias:
            continue
        if a_id in elegidas:
            p["pesos"][a_id] = 3
        elif cur.peso(a, p["pesos"], usuario, metas) > 0:
            p["pesos"][a_id] = resto
    guardar_perfil(usuario, p)
    ad.reiniciar_plan_si_no_empezo(usuario)
    ad.invalidar(usuario)
    return {"ok": True, "pesos": p["pesos"]}


@ruta("POST", "/api/ubicacion/inferir")
def r_ubicacion_inferir(usuario, q, d, h):
    if not cur.modulo(d.get("ref", ""), usuario):
        return {"error": "módulo desconocido"}
    marcados = aa.inferir_requisitos(usuario, d["ref"], bool(d.get("todas")))
    ad.invalidar(usuario)
    return {"ok": True, "inferidos": len(marcados)}


@ruta("GET", "/api/externo")
def r_externo_ver(usuario, q, d, h):
    return {"externo": aa.externo(usuario)}


@ruta("POST", "/api/externo")
def r_externo(usuario, q, d, h):
    texto = str(d.get("texto") or "").strip()
    if len(texto) < 5:
        return {"error": "cuenta qué estudiaste"}
    t = ia.nuevo("externo", lambda ctx: aa.mapear_externo(ctx, usuario, texto), 0, usuario, "externo")
    t.permiso = d.get("permiso")
    return trabajo_json(t)


# --------------------------------------------------------------- repaso
@ruta("GET", "/api/repaso")
def r_repaso(usuario, q, d, h):
    perfil = perfil_de(usuario)
    cola, venc, nuevas = cola_repaso(usuario, perfil)
    out = []
    for t in cola[:int(q.get("n", 60))]:
        out.append({"id": t["id"], "frente": t["frente"], "reverso": t["reverso"], "idioma": t["idioma"],
                    "area": t["area"], "tema": t["tema"], "nueva": t["estabilidad"] is None,
                    "botones": fsrs.vista_previa(t)})
    return {"tarjetas": out, "vencidas": venc, "nuevas": nuevas}


@ruta("POST", "/api/repaso")
def r_repasar(usuario, q, d, h):
    t = fila("SELECT * FROM tarjeta WHERE id=? AND usuario=?", (d["id"], usuario))
    if not t:
        return {"error": "no existe"}
    origen = d.get("origen") if d.get("origen") in ("pulso", "chequeo") else "repaso"
    p = an.aplicar_repaso(usuario, t, int(d["nota"]), d.get("segundos"), origen)
    return {"ok": True, "vence": p["vence"]}


@ruta("POST", "/api/quiz/fallos")
def r_quiz_fallos(usuario, q, d, h):
    """Lo que fallaste en el quiz se vuelve tarjeta (desde el quiz guardado de la lección, no desde el navegador):
    repasar justo los errores es lo que más rinde por minuto."""
    t = cur.tema(d.get("tema", ""), usuario)
    lecc = fila("SELECT ejercicios FROM leccion WHERE usuario=? AND tema=?", (usuario, d.get("tema", "")))
    if not t or not lecc:
        return {"error": "tema desconocido"}
    quiz = (json.loads(lecc["ejercicios"] or "{}") or {}).get("quiz", [])
    tarjetas = []
    for i in d.get("fallos", [])[:20]:
        if not isinstance(i, int) or not 0 <= i < len(quiz):
            continue
        p_ = quiz[i]
        ops = p_.get("opciones") or []
        correcta = ops[p_["correcta"]] if p_.get("tipo") == "opcion" and isinstance(p_.get("correcta"), int) \
            and 0 <= p_["correcta"] < len(ops) else ""
        tarjetas.append({"frente": p_.get("pregunta", ""),
                         "reverso": (f"**{correcta}**\n\n" if correcta else "") + (p_.get("explicacion") or "")})
    a = cur.areas(usuario)[t["area"]]
    return {"ok": True, "agregadas": agregar_tarjetas(usuario, tarjetas, t["id"], t["area"], a.get("idioma"), "quiz")}


@ruta("POST", "/api/tarjeta")
def r_tarjeta(usuario, q, d, h):
    n = agregar_tarjetas(usuario, [d], d.get("tema"), d.get("area"), d.get("idioma"), d.get("origen", "manual"))
    return {"ok": True, "agregadas": n}


@ruta("POST", "/api/tarjetas")
def r_tarjetas(usuario, q, d, h):
    n = agregar_tarjetas(usuario, d.get("tarjetas", []), d.get("tema"), d.get("area"), d.get("idioma"),
                         d.get("origen", "manual"))
    return {"ok": True, "agregadas": n}


@ruta("POST", "/api/tarjeta/suspender")
def r_suspender(usuario, q, d, h):
    ejecutar("UPDATE tarjeta SET suspendida=? WHERE id=? AND usuario=?", (1 if d.get("si", True) else 0, d["id"], usuario))
    return {"ok": True}


@ruta("POST", "/api/tarjeta/editar")
def r_editar(usuario, q, d, h):
    ejecutar("UPDATE tarjeta SET frente=?, reverso=? WHERE id=? AND usuario=?", (d["frente"], d["reverso"], d["id"], usuario))
    return {"ok": True}


# ---------------------------------------------------------------- tutor
@ruta("POST", "/api/tutor")
def r_tutor(usuario, q, d, h):
    perfil = perfil_ia(usuario)
    hilo = d.get("hilo") or "general"
    t = ia.nuevo("tutor", lambda ctx: lec.tutor(ctx, usuario, perfil, hilo, d["mensaje"], d.get("tema"),
                                                d.get("web", False)), 0, usuario, hilo)
    t.permiso = d.get("permiso")
    return trabajo_json(t)


@ruta("GET", "/api/chat")
def r_chat(usuario, q, d, h):
    return {"mensajes": filas("SELECT rol, texto, fecha FROM chat WHERE usuario=? AND hilo=? ORDER BY id",
                              (usuario, q.get("hilo", "general")))}


@ruta("GET", "/api/hilos")
def r_hilos(usuario, q, d, h):
    return {"hilos": filas("""SELECT hilo, MAX(fecha) fecha, COUNT(*) n FROM chat WHERE usuario=?
                              GROUP BY hilo ORDER BY fecha DESC LIMIT 30""", (usuario,))}


@ruta("POST", "/api/chat/borrar")
def r_chat_borrar(usuario, q, d, h):
    ejecutar("DELETE FROM chat WHERE usuario=? AND hilo=?", (usuario, d["hilo"]))
    return {"ok": True}


# ------------------------------------------------------------- cuaderno
def _carpeta_usuario(usuario):
    c = CUADERNO / (re.sub(r"[^\w.@-]", "_", usuario).lstrip(".") or "_")
    c.mkdir(exist_ok=True)
    return c


@ruta("GET", "/api/cuaderno")
def r_cuaderno(usuario, q, d, h):
    return {"notas": filas("""SELECT id, titulo, tema, area, puntaje, creado, actualizado,
                              substr(IFNULL(transcripcion,''),1,160) extracto, evaluacion IS NOT NULL evaluada
                              FROM cuaderno WHERE usuario=? ORDER BY actualizado DESC""", (usuario,))}


@ruta("GET", "/api/cuaderno/nota")
def r_nota(usuario, q, d, h):
    n = fila("SELECT * FROM cuaderno WHERE id=? AND usuario=?", (int(q["id"]), usuario))
    if not n:
        return {"error": "no existe"}
    n["evaluacion"] = json.loads(n["evaluacion"]) if n["evaluacion"] else None
    n["trazos"] = json.loads(n["trazos"]) if n["trazos"] else None
    return n


@ruta("POST", "/api/cuaderno")
def r_cuaderno_guardar(usuario, q, d, h):
    ahora = time.time()
    png = d.get("png", "")
    if not png.startswith("data:image/png;base64,"):
        return {"error": "falta la imagen"}
    datos = base64.b64decode(png.split(",", 1)[1])
    tema = d.get("tema") or None
    t = cur.tema(tema, usuario) if tema else None
    if d.get("id"):
        nid = int(d["id"])
        if not fila("SELECT id FROM cuaderno WHERE id=? AND usuario=?", (nid, usuario)):
            return {"error": "no existe"}
        ejecutar("""UPDATE cuaderno SET titulo=?, tema=?, area=?, trazos=?, ancho=?, alto=?, actualizado=?
                    WHERE id=?""", (d.get("titulo") or "Apuntes", tema, t["area"] if t else None,
                                    json.dumps(d.get("trazos")), d.get("ancho"), d.get("alto"), ahora, nid))
    else:
        nid = ejecutar("""INSERT INTO cuaderno(usuario,titulo,tema,area,trazos,ancho,alto,creado,actualizado)
                          VALUES(?,?,?,?,?,?,?,?,?)""",
                       (usuario, d.get("titulo") or "Apuntes", tema, t["area"] if t else None,
                        json.dumps(d.get("trazos")), d.get("ancho"), d.get("alto"), ahora, ahora)).lastrowid
        registrar(usuario, "apunte", tema, t["area"] if t else None)
    ruta_png = _carpeta_usuario(usuario) / f"{nid}.png"
    ruta_png.write_bytes(datos)
    ejecutar("UPDATE cuaderno SET imagen=? WHERE id=?", (str(ruta_png), nid))
    return {"ok": True, "id": nid}


def img_cuaderno(h, usuario, nid):
    n = fila("SELECT imagen FROM cuaderno WHERE id=? AND usuario=?", (nid, usuario))
    if not n or not n["imagen"]:
        return h.texto("no existe", codigo=404)
    return h.archivo(Path(n["imagen"]), cache=False)


@ruta("POST", "/api/cuaderno/evaluar")
def r_cuaderno_evaluar(usuario, q, d, h):
    n = fila("SELECT * FROM cuaderno WHERE id=? AND usuario=?", (int(d["id"]), usuario))
    if not n:
        return {"error": "no existe"}

    def fn(ctx):
        ev = lec.evaluar_apunte(ctx, n["imagen"], n["tema"], usuario, d.get("contexto", ""))
        titulo = n["titulo"] if n["titulo"] and n["titulo"] != "Apuntes" else ev.get("titulo") or "Apuntes"
        ejecutar("UPDATE cuaderno SET transcripcion=?, evaluacion=?, puntaje=?, titulo=? WHERE id=?",
                 (ev.get("transcripcion"), json.dumps(ev, ensure_ascii=False), ev.get("puntaje"), titulo, n["id"]))
        registrar(usuario, "apunte_eval", n["tema"], n["area"], (ev.get("puntaje") or 0) / 100)
        return ev

    t = ia.nuevo("apunte", fn, 0, usuario, str(n["id"]))
    t.permiso = d.get("permiso")
    return trabajo_json(t)


@ruta("POST", "/api/cuaderno/tarjetas")
def r_cuaderno_tarjetas(usuario, q, d, h):
    n = fila("SELECT * FROM cuaderno WHERE id=? AND usuario=?", (int(d["id"]), usuario))
    ev = json.loads(n["evaluacion"] or "{}")
    k = agregar_tarjetas(usuario, ev.get("tarjetas", []), n["tema"], n["area"], None, "cuaderno")
    return {"ok": True, "agregadas": k}


@ruta("POST", "/api/cuaderno/borrar")
def r_cuaderno_borrar(usuario, q, d, h):
    n = fila("SELECT * FROM cuaderno WHERE id=? AND usuario=?", (int(d["id"]), usuario))
    if n:
        if n["imagen"]:
            Path(n["imagen"]).unlink(missing_ok=True)
        ejecutar("DELETE FROM cuaderno WHERE id=?", (n["id"],))
    return {"ok": True}


# ------------------------------------------------------- práctica (entregas)
ENTREGAS = base.DATOS / "entregas"
ENTREGAS.mkdir(exist_ok=True)


def _entrega_pub(e):
    e = dict(e)
    e["evaluacion"] = json.loads(e["evaluacion"]) if e["evaluacion"] else None
    e["tiene_imagen"] = bool(e.pop("imagen", None))
    e["corrigiendo"] = any(x.tipo == "entrega" and x.etiqueta == str(e["id"]) and x.estado in ("cola", "corriendo", "conflicto")
                           for x in ia.cola.trabajos.values())
    return e


@ruta("GET", "/api/entregas")
def r_entregas(usuario, q, d, h):
    tid = q.get("tema")
    if q.get("tarea"):
        ta = fila("SELECT * FROM tarea WHERE id=? AND usuario=?", (int(q["tarea"]), usuario))
        if not ta:
            return {"error": "tarea inexistente"}
        ejs = [{"n": i + 1, "titulo": e["titulo"], "enunciado": re.sub(r"\s+", " ", e["enunciado"])[:220]}
               for i, e in enumerate(json.loads(ta["ejercicios"]))]
        filas_ = filas("SELECT * FROM entrega WHERE usuario=? AND tarea=? ORDER BY id DESC", (usuario, ta["id"]))
        for e in filas_:
            e["tema_t"] = ta["titulo"]
        return {"ejercicios": ejs, "entregas": [_entrega_pub(e) for e in filas_]}
    lecc = fila("SELECT contenido FROM leccion WHERE usuario=? AND tema=?", (usuario, tid)) if tid else None
    sql = "SELECT * FROM entrega WHERE usuario=? AND tarea IS NULL" + (" AND tema=?" if tid else "") + " ORDER BY id DESC"
    filas_ = filas(sql, (usuario, tid) if tid else (usuario,))
    for e in filas_:
        tt = cur.tema(e["tema"], usuario)
        e["tema_t"] = tt["t"] if tt else e["tema"]
    return {"ejercicios": lec.ejercicios_de(lecc["contenido"]) if lecc else [],
            "entregas": [_entrega_pub(e) for e in filas_]}


def lanzar_correccion(usuario, eid, permiso=None):
    def fn(ctx):
        e = fila("SELECT * FROM entrega WHERE id=?", (eid,))
        ev = lec.corregir_entrega(ctx, e, usuario)
        ejecutar("UPDATE entrega SET evaluacion=?, puntaje=?, corregido=? WHERE id=?",
                 (json.dumps(ev, ensure_ascii=False), ev.get("puntaje"), time.time(), eid))
        registrar(usuario, "practica", e["tema"], e["area"], (ev.get("puntaje") or 0) / 100,
                  {"ejercicio": e["ejercicio"], "version": e["version"]})
        return ev
    t = ia.nuevo("entrega", fn, 0, usuario, str(eid))
    t.permiso = permiso
    return t


@ruta("POST", "/api/entrega")
def r_entrega(usuario, q, d, h):
    tid = d.get("tema")
    t = cur.tema(tid, usuario) if tid else None
    if not t:
        return {"error": "tema desconocido"}
    ejercicio = str(d.get("ejercicio") or "1")[:80]
    texto = (d.get("texto") or "").strip()
    img = d.get("imagen") or ""
    cuaderno = d.get("cuaderno")
    ruta_img, tipo = None, "texto"
    if cuaderno:
        n = fila("SELECT imagen FROM cuaderno WHERE id=? AND usuario=?", (int(cuaderno), usuario))
        if not n or not n["imagen"]:
            return {"error": "nota del cuaderno no encontrada"}
        ruta_img, tipo = n["imagen"], "cuaderno"
    elif img.startswith("data:image/"):
        tipo = "imagen"
    elif not texto:
        return {"error": "Escribe tu solución o adjunta una foto"}
    tarea = int(d["tarea"]) if d.get("tarea") else None
    if tarea and not fila("SELECT 1 FROM tarea WHERE id=? AND usuario=?", (tarea, usuario)):
        return {"error": "tarea inexistente"}
    version = (fila("SELECT MAX(version) v FROM entrega WHERE usuario=? AND tema=? AND ejercicio=? AND IFNULL(tarea,0)=?",
                    (usuario, tid, ejercicio, tarea or 0))["v"] or 0) + 1
    eid = ejecutar("""INSERT INTO entrega(usuario,tema,area,ejercicio,version,tipo,texto,imagen,cuaderno,creado,tarea)
                      VALUES(?,?,?,?,?,?,?,?,?,?,?)""", (usuario, tid, t["area"], ejercicio, version, tipo, texto or None,
                                                       ruta_img, cuaderno, time.time(), tarea)).lastrowid
    if tipo == "imagen":
        ext = "png" if img.startswith("data:image/png") else "jpg"
        destino = _carpeta(ENTREGAS, usuario) / f"{eid}.{ext}"
        destino.write_bytes(base64.b64decode(img.split(",", 1)[1]))
        ejecutar("UPDATE entrega SET imagen=? WHERE id=?", (str(destino), eid))
    registrar(usuario, "entrega", tid, t["area"], None, {"ejercicio": ejercicio, "version": version})
    j = lanzar_correccion(usuario, eid, d.get("permiso"))
    return {"ok": True, "id": eid, "version": version, "trabajo": j.id}


@ruta("POST", "/api/entrega/corregir")
def r_entrega_corregir(usuario, q, d, h):
    if not fila("SELECT 1 FROM entrega WHERE id=? AND usuario=?", (int(d["id"]), usuario)):
        return {"error": "no existe"}
    return trabajo_json(lanzar_correccion(usuario, int(d["id"]), d.get("permiso")))


@ruta("POST", "/api/entrega/borrar")
def r_entrega_borrar(usuario, q, d, h):
    e = fila("SELECT * FROM entrega WHERE id=? AND usuario=?", (int(d["id"]), usuario))
    if e:
        if e["tipo"] == "imagen" and e["imagen"]:
            Path(e["imagen"]).unlink(missing_ok=True)
        ejecutar("DELETE FROM entrega WHERE id=?", (e["id"],))
    return {"ok": True}


def img_entrega(h, usuario, eid):
    e = fila("SELECT imagen FROM entrega WHERE id=? AND usuario=?", (eid, usuario))
    if not e or not e["imagen"]:
        return h.texto("no existe", codigo=404)
    return h.archivo(Path(e["imagen"]), cache=False)


@ruta("GET", "/api/tareas")
def r_tareas(usuario, q, d, h):
    out = []
    for ta in filas("SELECT * FROM tarea WHERE usuario=? ORDER BY id DESC LIMIT 80", (usuario,)):
        ejs = json.loads(ta["ejercicios"])
        tt = cur.tema(ta["tema"], usuario)
        x = {"id": ta["id"], "titulo": ta["titulo"], "tema": ta["tema"], "tema_t": tt["t"] if tt else ta["tema"],
             "tipo": ta["tipo"] or "desarrollo", "dificultad": ta["dificultad"], "creado": ta["creado"], "n": len(ejs)}
        if x["tipo"] == "quiz":
            ints = json.loads(ta["intentos"] or "[]")
            x["intentos"] = len(ints)
            x["mejor"] = max((i["bien"] / i["total"] for i in ints), default=None)
        else:
            ent = filas("SELECT ejercicio, MAX(puntaje) p FROM entrega WHERE usuario=? AND tarea=? GROUP BY ejercicio",
                        (usuario, ta["id"]))
            x["entregados"] = len(ent)
            x["aprobados"] = sum(1 for e in ent if (e["p"] or 0) >= 80)
        out.append(x)
    pend = [x.publico() for x in ia.cola.trabajos.values()
            if x.tipo == "tarea" and x.usuario == usuario and x.estado in ("cola", "corriendo", "conflicto")]
    return {"tareas": out, "pendientes": pend}


@ruta("GET", "/api/tarea")
def r_tarea(usuario, q, d, h):
    ta = fila("SELECT * FROM tarea WHERE id=? AND usuario=?", (int(q["id"]), usuario))
    if not ta:
        return {"error": "tarea inexistente"}
    ta["ejercicios"] = json.loads(ta["ejercicios"])
    ta["intentos"] = json.loads(ta["intentos"] or "[]")
    ta["tipo"] = ta["tipo"] or "desarrollo"
    t = cur.tema(ta["tema"], usuario)
    a = cur.areas(usuario).get(t["area"]) if t else None
    ta["tema_t"] = t["t"] if t else ta["tema"]
    ta["area_nombre"] = a["nombre"] if a else ""
    ta["idioma"] = a.get("idioma") if a else None
    return ta


@ruta("GET", "/api/tarea/sugerencias")
def r_tarea_sug(usuario, q, d, h):
    """Temas ya vistos, agrupados por área y por meta, con los que se están olvidando marcados."""
    avs = cur.avances(usuario)
    con_actividad = {r["tema"] for r in filas(
        "SELECT DISTINCT tema FROM actividad WHERE usuario=? AND tema IS NOT NULL", (usuario,))}
    con_tarjetas = {r["tema"] for r in filas("SELECT DISTINCT tema FROM tarjeta WHERE usuario=? AND tema IS NOT NULL", (usuario,))}
    olvido = {x["id"]: x["r"] for x in an.analitica(usuario)["olvidando"]}
    temas, grupos = {}, []
    for a in cur.areas(usuario).values():
        ids = []
        for m in a["modulos"]:
            for t in m["temas_obj"]:
                av = avs.get(t["id"]) or {}
                visto = av.get("estado") in ("visto", "dominado", "probado") or t["id"] in con_actividad or t["id"] in con_tarjetas
                if not visto:
                    continue
                ids.append(t["id"])
                temas[t["id"]] = {"id": t["id"], "t": t["t"], "modulo": m["t"], "nivel": m["nivel"],
                                  "area": a["id"], "area_nombre": a["nombre"], "icono": a.get("icono"),
                                  "estado": av.get("estado", "visto"), "olvido": olvido.get(t["id"])}
        if ids:
            grupos.append({"id": "area:" + a["id"], "tipo": "area", "nombre": f"{a.get('icono', '')} {a['nombre']}", "temas": ids})
    for o in filas("SELECT * FROM objetivo WHERE usuario=? AND estado='activo'", (usuario,)):
        plan = json.loads(o["plan"] or "{}")
        refs = cur.cierre_prerrequisitos(plan.get("modulos", []) + plan.get("extra", []), usuario)
        ids = [t["id"] for r in refs for t in ((cur.modulo(r, usuario) or {}).get("temas_obj") or []) if t["id"] in temas]
        if ids:
            grupos.insert(0, {"id": f"meta:{o['id']}", "tipo": "meta", "nombre": f"🎯 {o['titulo']}", "temas": ids})
    sugeridos = sorted(olvido, key=lambda k: olvido[k])[:8]
    return {"grupos": grupos, "temas": temas, "sugeridos": [s_ for s_ in sugeridos if s_ in temas]}


@ruta("POST", "/api/tarea/nueva")
def r_tarea_nueva(usuario, q, d, h):
    ids = [t for t in (d.get("temas") or ([d["tema"]] if d.get("tema") else [])) if cur.tema(t, usuario)]
    if not ids:
        return {"error": "Elige al menos un tema"}
    perfil = perfil_ia(usuario)
    dif = d.get("dificultad") if d.get("dificultad") in lec.DIFICULTADES else "intermedia"
    tipo = "quiz" if d.get("tipo") == "quiz" else "desarrollo"
    maximo = 15 if tipo == "quiz" else 6
    n = max(1, min(int(d.get("cantidad") or (5 if tipo == "quiz" else 3)), maximo))
    enfoque = (d.get("enfoque") or "").strip()
    trabajos = []
    for tid in ids[:20]:
        t = ia.nuevo("tarea", lambda ctx, tid=tid: lec.crear_tarea(ctx, usuario, perfil, tid, dif, n, enfoque, tipo),
                     0, usuario, tid)
        t.permiso = d.get("permiso")
        trabajos.append(t.id)
    return {"trabajos": trabajos, "trabajo": trabajos[0], "estado": "cola"}


@ruta("POST", "/api/tarea/quiz")
def r_tarea_quiz(usuario, q, d, h):
    """Califica un intento de un quiz de práctica (respuestas = índice elegido por pregunta)."""
    ta = fila("SELECT * FROM tarea WHERE id=? AND usuario=? AND tipo='quiz'", (int(d["id"]), usuario))
    if not ta:
        return {"error": "quiz inexistente"}
    ejs = json.loads(ta["ejercicios"])
    resp = d.get("respuestas") or []
    bien = sum(1 for i, e in enumerate(ejs) if i < len(resp) and resp[i] == e["correcta"])
    ints = json.loads(ta["intentos"] or "[]") + [{"fecha": time.time(), "bien": bien, "total": len(ejs)}]
    ejecutar("UPDATE tarea SET intentos=? WHERE id=?", (json.dumps(ints), ta["id"]))
    registrar(usuario, "practica", ta["tema"], ta["area"], bien / max(1, len(ejs)), {"tarea": ta["id"], "tipo": "quiz"})
    ad.invalidar(usuario)
    return {"bien": bien, "total": len(ejs), "intentos": ints}


@ruta("POST", "/api/tarea/borrar")
def r_tarea_borrar(usuario, q, d, h):
    tid = int(d["id"])
    for e in filas("SELECT * FROM entrega WHERE tarea=? AND usuario=?", (tid, usuario)):
        if e["tipo"] == "imagen" and e["imagen"]:
            Path(e["imagen"]).unlink(missing_ok=True)
    ejecutar("DELETE FROM entrega WHERE tarea=? AND usuario=?", (tid, usuario))
    ejecutar("DELETE FROM tarea WHERE id=? AND usuario=?", (tid, usuario))
    return {"ok": True}


def _carpeta(raiz, usuario):
    c = raiz / (re.sub(r"[^\w.@-]", "_", usuario).lstrip(".") or "_")
    c.mkdir(exist_ok=True)
    return c


# ------------------------------------------------------------ objetivos
@ruta("GET", "/api/objetivos")
def r_objetivos(usuario, q, d, h):
    pend = [x.publico() for x in ia.cola.trabajos.values()
            if x.tipo in ("objetivo", "area") and x.usuario == usuario and x.estado in ("cola", "corriendo", "conflicto")]
    return {"objetivos": [cur.estado_objetivo(usuario, o) for o in
                          filas("SELECT * FROM objetivo WHERE usuario=? ORDER BY estado='activo' DESC, id DESC",
                                (usuario,))], "pendientes": pend}


@ruta("POST", "/api/objetivos")
def r_objetivo_nuevo(usuario, q, d, h):
    titulo = (d.get("titulo") or "").strip()
    if not titulo:
        return {"error": "Escribe el objetivo"}
    perfil = perfil_de(usuario)
    def planear(ctx):
        r = lec.planear_objetivo(ctx, usuario, perfil, titulo, d.get("descripcion", ""))
        dominio.mapear_ramas(ctx, usuario, perfil, r["objetivo"])   # que no quede ninguna sub-rama sin cubrir
        if d.get("semanas"):
            dominio.poner_plazo(usuario, r["objetivo"], int(d["semanas"]))
        ia.nuevo("frontera", lambda c: dominio.generar_frontera(c, usuario, perfil_ia(usuario), r["objetivo"]),
                 1, usuario, str(r["objetivo"]))
        return r
    t = ia.nuevo("objetivo", planear, 0, usuario, titulo)
    t.permiso = d.get("permiso")
    return trabajo_json(t)


# ------------------------------------------------- programa de dominio (meta → frontera)
def _frontera_en_cola(usuario, oid):
    return next((x for x in ia.cola.trabajos.values() if x.tipo == "frontera" and x.usuario == usuario
                 and x.etiqueta == str(oid) and x.estado in ("cola", "corriendo", "conflicto")), None)


@ruta("GET", "/api/dominio")
def r_dominio(usuario, q, d, h):
    oid = q.get("objetivo", "")
    if not oid.isdigit() or not fila("SELECT 1 FROM objetivo WHERE id=? AND usuario=?", (int(oid), usuario)):
        return {"error": "meta desconocida"}
    pend = _frontera_en_cola(usuario, oid)
    trab = {x.tipo: x.publico() for x in ia.cola.trabajos.values() if x.usuario == usuario and x.etiqueta == str(oid)
            and x.tipo in ("ramas", "ideas") and x.estado in ("cola", "corriendo", "conflicto")}
    return {"programa": dominio.estado_programa(usuario, perfil_de(usuario), oid), "ramas": dominio.ramas_de(usuario, oid),
            "ideas": dominio.ideas_de(usuario, oid), "trabajos": trab,
            "frontera": dominio.ultima_frontera(oid), "frontera_trabajo": pend.publico() if pend else None,
            "lecturas": dominio.lecturas_de(usuario, oid), "aportes": dominio.aportes_de(usuario, oid)}


@ruta("POST", "/api/programa")
def r_programa(usuario, q, d, h):
    try:
        prog = dominio.poner_plazo(usuario, d.get("objetivo"), max(0, min(int(d.get("semanas") or 0), 260)))
    except (ValueError, TypeError):
        return {"error": "meta desconocida"}
    ad.invalidar(usuario)
    ad.reiniciar_plan_si_no_empezo(usuario)
    return {"ok": True, "programa": prog}


@ruta("POST", "/api/frontera")
def r_frontera(usuario, q, d, h):
    oid = str(d.get("objetivo", ""))
    if not oid.isdigit() or not fila("SELECT 1 FROM objetivo WHERE id=? AND usuario=?", (int(oid), usuario)):
        return {"error": "meta desconocida"}
    t = _frontera_en_cola(usuario, oid)
    if t:
        if t.prioridad > 0 and t.estado == "cola":
            ia.cola.subir(t)
        return trabajo_json(t)
    t = ia.nuevo("frontera", lambda ctx: dominio.generar_frontera(ctx, usuario, perfil_ia(usuario), oid), 0, usuario, oid)
    t.permiso = d.get("permiso")
    return trabajo_json(t)


def _meta_propia(usuario, oid):
    oid = str(oid or "")
    return oid if oid.isdigit() and fila("SELECT 1 FROM objetivo WHERE id=? AND usuario=?", (int(oid), usuario)) else None


def _tarea_meta(tipo, usuario, etiqueta, fn, d):
    t = next((x for x in ia.cola.trabajos.values() if x.tipo == tipo and x.usuario == usuario and x.etiqueta == etiqueta
              and x.estado in ("cola", "corriendo", "conflicto")), None) or ia.nuevo(tipo, fn, 0, usuario, etiqueta)
    t.permiso = d.get("permiso")
    return trabajo_json(t)


@ruta("POST", "/api/ramas")
def r_ramas(usuario, q, d, h):
    oid = _meta_propia(usuario, d.get("objetivo"))
    if not oid:
        return {"error": "meta desconocida"}
    return _tarea_meta("ramas", usuario, oid, lambda ctx: dominio.mapear_ramas(ctx, usuario, perfil_ia(usuario), oid), d)


@ruta("POST", "/api/ideas")
def r_ideas(usuario, q, d, h):
    oid = _meta_propia(usuario, d.get("objetivo"))
    if not oid:
        return {"error": "meta desconocida"}
    if not dominio.ultima_frontera(oid):
        return {"error": "primero hace falta el mapa de la frontera (🔭) de esta meta"}
    enfoque = str(d.get("enfoque") or "")[:600]
    return _tarea_meta("ideas", usuario, oid, lambda ctx: dominio.idear(ctx, usuario, perfil_ia(usuario), oid, enfoque), d)


def _idea_propia(usuario, d):
    iid = str(d.get("idea") or "")
    return iid if iid.isdigit() and dominio._idea(usuario, iid) else None


@ruta("POST", "/api/idea/elegir")
def r_idea_elegir(usuario, q, d, h):
    iid = _idea_propia(usuario, d)
    if not iid:
        return {"error": "idea desconocida"}
    dominio.elegir_idea(usuario, iid)
    ad.invalidar(usuario)
    ad.reiniciar_plan_si_no_empezo(usuario)
    return {"ok": True}


@ruta("POST", "/api/idea/presentacion")
def r_idea_presentacion(usuario, q, d, h):
    iid = _idea_propia(usuario, d)
    if not iid:
        return {"error": "idea desconocida"}
    return _tarea_meta("presentacion", usuario, iid, lambda ctx: dominio.preparar_presentacion(ctx, usuario, perfil_ia(usuario), iid), d)


@ruta("POST", "/api/idea/pares")
def r_idea_pares(usuario, q, d, h):
    iid = _idea_propia(usuario, d)
    if not iid:
        return {"error": "idea desconocida"}
    return _tarea_meta("pares", usuario, iid, lambda ctx: dominio.revision_pares(ctx, usuario, iid), d)


@ruta("POST", "/api/paper/guia")
def r_paper_guia(usuario, q, d, h):
    oid = str(d.get("objetivo", ""))
    if not oid.isdigit() or not fila("SELECT 1 FROM objetivo WHERE id=? AND usuario=?", (int(oid), usuario)):
        return {"error": "meta desconocida"}
    n = int(d.get("paper") or 0)
    t = ia.nuevo("paper", lambda ctx: dominio.guia_paper(ctx, usuario, perfil_ia(usuario), oid, n), 0, usuario, f"{oid}:{n}")
    t.permiso = d.get("permiso")
    return trabajo_json(t)


@ruta("GET", "/api/paper")
def r_paper(usuario, q, d, h):
    x = dominio.lectura(usuario, q.get("id") or 0) if str(q.get("id", "")).isdigit() else None
    return x or {"error": "lectura desconocida"}


@ruta("POST", "/api/paper/responder")
def r_paper_responder(usuario, q, d, h):
    respuesta = str(d.get("respuesta") or "").strip()
    if not dominio.lectura(usuario, int(d.get("id") or 0)) or len(respuesta) < 3:
        return {"error": "datos inválidos"}
    t = ia.nuevo("corregir", lambda ctx: dominio.corregir_respuesta(ctx, usuario, int(d["id"]), int(d.get("i", 0)),
                                                                   respuesta[:4000]), 0, usuario, f"paper:{d['id']}")
    t.permiso = d.get("permiso")
    return trabajo_json(t)


@ruta("POST", "/api/aporte")
def r_aporte(usuario, q, d, h):
    oid = str(d.get("objetivo", ""))
    texto = str(d.get("texto") or "").strip()
    if not oid.isdigit() or not fila("SELECT 1 FROM objetivo WHERE id=? AND usuario=?", (int(oid), usuario)) \
            or len(texto) < 20:
        return {"error": "escribe tu idea (al menos una frase completa)"}
    t = ia.nuevo("aporte", lambda ctx: dominio.evaluar_aporte(ctx, usuario, perfil_ia(usuario), oid, texto[:4000]),
                 0, usuario, oid)
    t.permiso = d.get("permiso")
    return trabajo_json(t)


# ------------------------------------------------- fuentes verificadas y comparador
@ruta("POST", "/api/verificar/leccion")
def r_verificar_leccion(usuario, q, d, h):
    tid = d.get("tema", "")
    if not cur.tema(tid, usuario) or not fila("SELECT 1 FROM leccion WHERE usuario=? AND tema=?", (usuario, tid)):
        return {"error": "la lección aún no existe"}
    t = encolar_verificacion(usuario, tid, 0)
    t.permiso = d.get("permiso")
    return trabajo_json(t)


@ruta("POST", "/api/verificar")
def r_verificar(usuario, q, d, h):
    texto = str(d.get("texto") or "").strip()
    if len(texto) < 10:
        return {"error": "escribe la afirmación o la pregunta (al menos una frase)"}
    t = ia.nuevo("verificar", lambda ctx: vf.verificar_texto(ctx, usuario, texto[:3000]), 0, usuario, "texto")
    t.permiso = d.get("permiso")
    return trabajo_json(t)


@ruta("POST", "/api/aportada")
def r_aportada(usuario, q, d, h):
    """Guarda el texto de una página que la persona pegó y lo analiza (resumen, referencias y contraste)."""
    try:
        ident = aportadas.guardar(usuario, d.get("tema"), d.get("titulo"), d.get("url"), d.get("texto"))
    except ValueError as ex:
        return {"error": str(ex)}
    t = ia.nuevo("aportada", lambda ctx: aportadas.analizar(ctx, usuario, ident), 0, usuario, ident)
    t.permiso = d.get("permiso")
    return trabajo_json(t) | {"id": ident}


@ruta("GET", "/api/aportadas")
def r_aportadas(usuario, q, d, h):
    out = []
    for x in aportadas.lista(usuario, q.get("tema") or None):
        out.append(aportadas.publico(x) | {"analisis": vf.de(usuario, f"aportada:{x['id']}")})
    return {"aportadas": out}


@ruta("POST", "/api/aportada/borrar")
def r_aportada_borrar(usuario, q, d, h):
    aportadas.borrar(usuario, str(d.get("id") or ""))
    return {"ok": True}


@ruta("GET", "/api/verificar")
def r_verificar_ver(usuario, q, d, h):
    clave = q.get("clave", "")
    if clave:
        return vf.de(usuario, clave) or {"error": "no existe"}
    pend = [x.publico() for x in ia.cola.trabajos.values() if x.tipo == "verificar" and x.usuario == usuario
            and x.etiqueta == "texto" and x.estado in ("cola", "corriendo", "conflicto")]
    return {"historial": vf.historial(usuario), "pendientes": pend}


# ------------------------------------------------- rutas vivas: preparar todo y actualizar
def _ruta_area(usuario, d):
    """La ruta pedida como id de área: un área ({area}) o la de una meta ({objetivo} → obj<N>)."""
    if d.get("objetivo") not in (None, ""):
        oid = str(d["objetivo"])
        if not oid.isdigit() or not fila("SELECT 1 FROM objetivo WHERE id=? AND usuario=?", (int(oid), usuario)):
            return None
        return f"obj{oid}"
    a = str(d.get("area") or "")
    return a if a in cur.areas_de(usuario) and a in cur.areas(usuario) else None


def _temas_ruta(usuario, area_id):
    """Todos los temas de una ruta; en una meta, también los de sus requisitos de otras áreas."""
    if area_id.startswith("obj"):
        o = fila("SELECT * FROM objetivo WHERE id=? AND usuario=?", (int(area_id[3:]), usuario))
        if not o:
            return []
        return [t["id"] for p in cur.estado_objetivo(usuario, o)["pasos"] for t in p["faltan"]]
    avs = cur.avances(usuario)
    return [t["id"] for m in sorted(cur.areas(usuario)[area_id]["modulos"], key=lambda m: m["nivel"])
            for t in m["temas_obj"] if cur.dominio_tema(avs.get(t["id"])) < cur.UMBRAL_DOMINIO]


PRIORIDAD_RUTA = 2   # «preparar toda la ruta» va detrás de lo diario (noticias, mercado, lecciones del día)


@ruta("POST", "/api/ruta/preparar")
def r_ruta_preparar(usuario, q, d, h):
    area_id = _ruta_area(usuario, d)
    if not area_id:
        return {"error": "ruta desconocida"}
    marcadas = set(kv_get(f"preparar_ruta:{usuario}") or [])
    marcadas.add(area_id)
    kv_set(f"preparar_ruta:{usuario}", sorted(marcadas))   # la actualización diaria re-encola lo que falte
    tids = _temas_ruta(usuario, area_id)
    n = preparar_lecciones(usuario, tids, PRIORIDAD_RUTA, bool(perfil_de(usuario).get("dia_maxima")))
    return {"ok": True, "encoladas": n, "temas": len(tids)}


def actualizar_ruta(ctx, usuario, area_id, forzar=False):
    """Nivel profesional (referente del mercado) → revisión de la ruta → lecciones de lo nuevo. En una meta, el
    mapa de la frontera hace de referente."""
    area = cur.areas(usuario).get(area_id)
    if not area and not area_id.startswith("obj"):
        raise ValueError("ruta desconocida")
    dias_m = float(config.C.get("mercado_cada_dias") or 30)
    if area_id.startswith("obj"):
        f = dominio.ultima_frontera(int(area_id[3:]))
        if not f or forzar and time.time() - f["creada"] > 86400:
            dominio.generar_frontera(ctx, usuario, perfil_ia(usuario), int(area_id[3:]))
        area = cur.areas(usuario).get(area_id)   # la frontera puede haber creado el área propia de la meta
        if not area:
            return {"area": area_id, "agregados": [], "resumen": "La meta usa solo rutas del catálogo: se revisan en "
                                                                 "cada área; su frontera quedó al día."}
    elif not area.get("idioma") and area.get("grupo") != "Idiomas":
        r = kv_get(f"mercado:{area_id}")
        if not r or time.time() - r["fecha"] > (1 if forzar else dias_m) * 86400 - 3600:
            mercado.referente(ctx, area_id, usuario)
    res = revision.revisar(ctx, usuario, perfil_ia(usuario), area_id)
    nuevos = [i for x in res["agregados"] for i in x.get("ids", [])]
    if nuevos:
        preparar_lecciones(usuario, nuevos, PRIORIDAD_RUTA, bool(perfil_de(usuario).get("dia_maxima")))
    ad.invalidar(usuario)
    return res


def _ruta_en_cola(usuario, area_id):
    return next((x for x in ia.cola.trabajos.values() if x.tipo == "ruta" and x.usuario == usuario
                 and x.etiqueta == area_id and x.estado in ("cola", "corriendo", "conflicto")), None)


@ruta("POST", "/api/ruta/actualizar")
def r_ruta_actualizar(usuario, q, d, h):
    area_id = _ruta_area(usuario, d)
    if not area_id:
        return {"error": "ruta desconocida"}
    t = _ruta_en_cola(usuario, area_id)
    if t:
        if t.prioridad > 0 and t.estado == "cola":
            ia.cola.subir(t)
        return trabajo_json(t)
    t = ia.nuevo("ruta", lambda ctx: actualizar_ruta(ctx, usuario, area_id, True), 0, usuario, area_id)
    t.permiso = d.get("permiso")
    return trabajo_json(t)


@ruta("GET", "/api/ruta/estado")
def r_ruta_estado(usuario, q, d, h):
    area_id = _ruta_area(usuario, q)
    if not area_id:
        return {"error": "ruta desconocida"}
    tids = _temas_ruta(usuario, area_id)
    listas = sum(1 for t in tids if fila("SELECT 1 FROM leccion WHERE usuario=? AND tema=? AND ejercicios IS NOT NULL",
                                          (usuario, t)))
    en_cola = sum(1 for x in ia.cola.trabajos.values() if x.tipo == "leccion" and x.usuario == usuario
                  and x.etiqueta in set(tids) and x.estado in ("cola", "corriendo", "conflicto"))
    m = kv_get(f"mercado:{area_id}")
    t = _ruta_en_cola(usuario, area_id)
    return {"revision": revision.estado(usuario, area_id), "mercado_fecha": m["fecha"] if m else None,
            "preparar": area_id in (kv_get(f"preparar_ruta:{usuario}") or []), "pendientes": len(tids),
            "listas": listas, "en_cola": en_cola, "trabajo": t.publico() if t else None}


@ruta("POST", "/api/area/nueva")
def r_area_nueva(usuario, q, d, h):
    nombre = (d.get("nombre") or "").strip()
    if not nombre:
        return {"error": "Escribe el nombre del área"}
    perfil = perfil_de(usuario)
    t = ia.nuevo("area", lambda ctx: lec.crear_area(ctx, usuario, perfil, nombre, d.get("descripcion", "")), 0, usuario, nombre)
    t.permiso = d.get("permiso")
    return trabajo_json(t)


@ruta("POST", "/api/area/borrar")
def r_area_borrar(usuario, q, d, h):
    aid = d.get("id", "")
    if not aid.startswith("p_"):
        return {"error": "solo se pueden quitar áreas creadas por ti"}
    ejecutar("DELETE FROM area_extra WHERE id=? AND usuario=?", (aid, usuario))
    return {"ok": True}


@ruta("POST", "/api/objetivos/estado")
def r_objetivo_estado(usuario, q, d, h):
    if d.get("estado") == "borrar":
        ejecutar("DELETE FROM objetivo WHERE id=? AND usuario=?", (d["id"], usuario))
        ejecutar("DELETE FROM area_extra WHERE id=? AND usuario=?", (f"obj{d['id']}", usuario))
        kv_set(f"programa:{usuario}:{d['id']}", None)
    else:
        ejecutar("UPDATE objetivo SET estado=? WHERE id=? AND usuario=?", (d["estado"], d["id"], usuario))
    return {"ok": True}


# ------------------------------------------------------------- noticias
# ------------------------------------------------------------- regiones de noticias
def regiones_de(usuario):
    """{región: prioridad 0-3} de esta persona; si nunca las eligió, las de la instalación («regiones_por_defecto»)."""
    p = perfil_de(usuario).get("regiones")
    base = p if isinstance(p, dict) else (config.C.get("regiones_por_defecto") or {nt.GLOBAL: 2})
    return {k: int(v) for k, v in base.items()}


def regiones_en_uso():
    """Regiones que alguna persona activa quiere ver: solo esas se descargan (las demás no gastan red ni IA)."""
    usadas = set()
    for r in filas("SELECT usuario FROM perfil"):
        if activo(r["usuario"]):
            usadas |= {k for k, v in regiones_de(r["usuario"]).items() if v > 0}
    return usadas | {nt.GLOBAL}      # la síntesis común sale del segmento global


def _id_region(nombre):
    t = str(nombre).lower().translate(str.maketrans("áéíóúñü", "aeiounu"))
    return re.sub(r"[^a-z0-9]+", "_", t).strip("_")[:30]


@ruta("GET", "/api/regiones")
def r_regiones(usuario, q, d, h):
    cfg = nt.config()
    prio = regiones_de(usuario)
    fuentes = {}
    for f in cfg["fuentes"]:
        if f.get("tipo") != "lectura":
            fuentes.setdefault(f["region"], []).append({"n": f["n"], "u": f["u"], "idioma": f.get("idioma"),
                                                         "peso": f.get("peso", 1), "propia": bool(f.get("propia"))})
    return {"regiones": [{"id": k, **v, "prioridad": prio.get(k, 0), "fuentes": fuentes.get(k, [])}
                         for k, v in sorted(cfg["regiones"].items(), key=lambda x: (x[0] != nt.GLOBAL, x[1]["nombre"]))],
            "editable": es_admin(h, usuario), "por_defecto": config.C.get("regiones_por_defecto") or {nt.GLOBAL: 2}}


@ruta("POST", "/api/regiones/region")
def r_region_nueva(usuario, q, d, h):
    if not es_admin(h, usuario):
        return {"error": "Solo el administrador puede agregar regiones."}
    nombre = str(d.get("nombre") or "").strip()[:40]
    rid = _id_region(nombre)
    if not rid:
        return {"error": "Escribe el nombre de la región."}
    p = nt._propias()
    p.setdefault("regiones", {})[rid] = {"nombre": nombre, "icono": (str(d.get("icono") or "📍").strip()[:8] or "📍"),
                                         "descripcion": str(d.get("descripcion") or "")[:120]}
    p["quitar_regiones"] = [x for x in p.get("quitar_regiones", []) if x != rid]
    nt.guardar_propias(p)
    return {"ok": True, "id": rid}


@ruta("POST", "/api/regiones/region/borrar")
def r_region_borrar(usuario, q, d, h):
    if not es_admin(h, usuario):
        return {"error": "Solo el administrador puede quitar regiones."}
    rid = str(d.get("id") or "")
    if rid == nt.GLOBAL:
        return {"error": "La región global no se puede quitar."}
    p = nt._propias()
    p.get("regiones", {}).pop(rid, None)
    p["fuentes"] = [f for f in p.get("fuentes", []) if f.get("region") != rid]
    p["quitar_regiones"] = sorted(set(p.get("quitar_regiones", [])) | {rid})
    nt.guardar_propias(p)
    return {"ok": True}


def _probar_fuente(url):
    if not nt.url_publica(url):
        return {"error": "La dirección debe ser un RSS público de internet (http/https)."}
    try:
        req = urllib.request.Request(url, headers={"User-Agent": nt.UA})
        with nt._abrir_publica(req, timeout=20) as r:
            items = nt._items(r.read(3_000_000))
    except Exception as e:
        return {"error": f"No se pudo leer: {type(e).__name__}"}
    if not items:
        return {"error": "Responde, pero no encontré noticias (¿es la dirección del RSS/Atom?)."}
    return {"ok": True, "noticias": len(items), "ejemplos": [i["titulo"] for i in items[:3]]}


@ruta("POST", "/api/regiones/fuente/probar")
def r_fuente_probar(usuario, q, d, h):
    if not es_admin(h, usuario):
        return {"error": "Solo el administrador puede agregar fuentes."}
    return _probar_fuente(str(d.get("u") or "").strip())


@ruta("POST", "/api/regiones/fuente")
def r_fuente_nueva(usuario, q, d, h):
    if not es_admin(h, usuario):
        return {"error": "Solo el administrador puede agregar fuentes."}
    cfg = nt.config()
    u, n, reg = str(d.get("u") or "").strip(), str(d.get("n") or "").strip()[:60], str(d.get("region") or "")
    if reg not in cfg["regiones"]:
        return {"error": "Esa región no existe."}
    if not n:
        return {"error": "Escribe el nombre de la fuente."}
    if any(f["u"] == u for f in cfg["fuentes"]):
        return {"error": "Esa fuente ya está."}
    prueba = _probar_fuente(u)
    if prueba.get("error"):
        return prueba
    p = nt._propias()
    p.setdefault("fuentes", []).append({"n": n, "u": u, "peso": max(1, min(3, int(d.get("peso") or 2))), "areas": [],
                                        "idioma": str(d.get("idioma") or "es")[:5], "region": reg})
    p["quitar_fuentes"] = [x for x in p.get("quitar_fuentes", []) if x != u]
    nt.guardar_propias(p)
    return {"ok": True, **prueba}


@ruta("POST", "/api/regiones/fuente/borrar")
def r_fuente_borrar(usuario, q, d, h):
    if not es_admin(h, usuario):
        return {"error": "Solo el administrador puede quitar fuentes."}
    u = str(d.get("u") or "")
    p = nt._propias()
    antes = len(p.get("fuentes", []))
    p["fuentes"] = [f for f in p.get("fuentes", []) if f["u"] != u]
    if len(p["fuentes"]) == antes:                       # era del catálogo: se oculta
        p["quitar_fuentes"] = sorted(set(p.get("quitar_fuentes", [])) | {u})
    nt.guardar_propias(p)
    return {"ok": True}


@ruta("GET", "/api/noticias")
def r_noticias(usuario, q, d, h):
    p = q.get("periodo", "dia")
    s = nt.sintesis_guardada(p)
    mias_todas = cur.areas_de(usuario)
    if s and not (mias_todas & set(nt.AREAS_NOTICIAS)):
        s = None   # sin áreas propias no hay síntesis que mostrarle
    elif s and not set(nt.AREAS_NOTICIAS) <= mias_todas:   # quien no tiene todas las áreas: solo ve las suyas
        todas = cur.areas(usuario)
        nombres = [a["nombre"] for i, a in todas.items() if i in mias_todas]
        s = dict(s, texto=nt.sintesis_para(s["texto"], nombres, [todas[a]["nombre"] for a in nt.AREAS_NOTICIAS]))
    pend = next((x.publico() for x in ia.cola.trabajos.values()
                 if x.tipo in ("noticias", "sintesis") and x.estado in ("cola", "corriendo")), None)
    mias = cur.areas_de(usuario) & set(nt.AREAS_NOTICIAS)   # solo lo de SUS áreas; sin áreas, nada
    if q.get("area") and q["area"] not in mias:
        q = dict(q, area="")
    pendientes = sum(1 for x in ia.cola.trabajos.values() if x.tipo == "a_fondo" and x.estado in ("cola", "corriendo", "conflicto"))
    return {"periodo": p, "ranking": nt.ranking(p, q.get("area") or None, areas=mias, solo_a_fondo=True, regiones=regiones_de(usuario)) if mias else [],
            "preparando": pendientes, "hora_diaria": "%02d:%02d" % hora_diaria(), "admin": es_admin(h, usuario),
            "impacto": [x for x in nt.impacto_por_area(p) if x["area"] in mias],
            "mis_areas": [a for a in nt.AREAS_NOTICIAS if a in mias],
            "organizaciones": [o for o in nt.organizaciones(p, limite=60) if set(o["areas"]) & mias][:15],
            "sintesis": s, "ultima": kv_get("noticias_ultima"), "sin_analizar": len(nt.pendientes_analisis(50)),
            "trabajo": pend,
            "total": fila("SELECT COUNT(*) n FROM noticia WHERE tipo='noticia' AND publicada>?",
                          (nt._ventana(p),))["n"]}


@ruta("POST", "/api/noticias/actualizar")
def r_noticias_act(usuario, q, d, h):
    if not es_admin(h, usuario):
        return {"error": "Solo el administrador puede descargar las noticias a mano (se hace sola cada día)."}
    return nt.descargar(regiones_en_uso())


@ruta("POST", "/api/noticias/analizar")
def r_noticias_an(usuario, q, d, h):
    t = ia.nuevo("noticias", lambda ctx: nt.analizar(ctx, int(d.get("n", 10))), 1 if d.get("fondo") else 0, usuario, "análisis")
    t.permiso = d.get("permiso")
    return trabajo_json(t)


@ruta("POST", "/api/noticias/sintesis")
def r_noticias_sin(usuario, q, d, h):
    t = ia.nuevo("sintesis", lambda ctx: nt.sintesis(ctx, d.get("periodo", "semana")), 0, usuario, d.get("periodo"))
    t.permiso = d.get("permiso")
    return trabajo_json(t)


@ruta("GET", "/api/noticia")
def r_noticia(usuario, q, d, h):
    n = nt.detalle(int(q.get("id", 0)))
    if not n:
        return {"error": "noticia desconocida"}
    n["trabajo"] = next((x.publico() for x in ia.cola.trabajos.values() if x.tipo in ("explicar", "comparar")
                         and x.etiqueta == str(n["id"]) and x.estado in ("cola", "corriendo", "conflicto")), None)
    return n


@ruta("POST", "/api/noticia/profundo")
def r_noticia_profundo(usuario, q, d, h):
    nid, que = int(d["id"]), d.get("que", "explicacion")
    fn = {"explicacion": nt.explicar, "comparacion": nt.comparar}[que]
    tipo = "explicar" if que == "explicacion" else "comparar"
    for x in ia.cola.trabajos.values():
        if x.tipo == tipo and x.etiqueta == str(nid) and x.estado in ("cola", "corriendo", "conflicto"):
            if x.prioridad > 0 and x.estado == "cola":
                ia.cola.subir(x)
            return trabajo_json(x)
    t = ia.nuevo(tipo, lambda ctx: fn(ctx, nid), 1 if d.get("fondo") else 0, usuario, str(nid))
    t.permiso = d.get("permiso")
    return trabajo_json(t)


@ruta("GET", "/api/lecturas")
def r_lecturas(usuario, q, d, h):
    if q.get("area"):
        return {"lecturas": nt.lecturas(q["area"])}
    idiomas = [a["id"] for a in cur.areas(usuario).values() if a.get("idioma") and a["id"] in cur.areas_de(usuario)]
    return {"lecturas": [x for a in idiomas for x in nt.lecturas(a, limite=4)]}   # solo los idiomas que estudia


@ruta("POST", "/api/lectura")
def r_lectura(usuario, q, d, h):
    t = ia.nuevo("lectura", lambda ctx: nt.estudiar_lectura(ctx, int(d["id"])), 0, usuario, str(d["id"]))
    t.permiso = d.get("permiso")
    return trabajo_json(t)


# ------------------------------------------------------------- progreso
@ruta("GET", "/api/progreso")
def r_progreso(usuario, q, d, h):
    desde = time.time() - 182 * 86400
    por_dia = {}
    for r in filas("SELECT fecha, tipo, valor FROM actividad WHERE usuario=? AND fecha>?", (usuario, desde)):
        k = datetime.fromtimestamp(inicio_dia(r["fecha"])).strftime("%Y-%m-%d")
        e = por_dia.setdefault(k, {"repasos": 0, "minutos": 0, "lecciones": 0})
        if r["tipo"] == "repaso":
            e["repasos"] += 1
        elif r["tipo"] == "tiempo":
            e["minutos"] += (r["valor"] or 0) / 60
        elif r["tipo"] == "leccion":
            e["lecciones"] += 1
    rep = filas("SELECT nota, retenibilidad FROM repaso WHERE usuario=? AND fecha>? AND retenibilidad IS NOT NULL",
                (usuario, time.time() - 30 * 86400))
    retencion = sum(1 for r in rep if r["nota"] > 1) / len(rep) if rep else None
    mapa = cur.mapa(usuario)
    mias = cur.areas_de(usuario)   # solo las áreas de esta persona
    tot = fila("""SELECT SUM(estado IN ('dominado','probado')) dom, SUM(estado='visto') vis
                  FROM avance WHERE usuario=?""", (usuario,))
    debiles = filas("""SELECT t.tema, t.area, COUNT(*) fallos FROM repaso r JOIN tarjeta t ON t.id=r.tarjeta
                       WHERE r.usuario=? AND r.nota=1 AND r.fecha>? AND t.tema IS NOT NULL
                       GROUP BY t.tema ORDER BY fallos DESC LIMIT 8""", (usuario, time.time() - 30 * 86400))
    for x in debiles:
        tt = cur.tema(x["tema"], usuario)
        x["t"] = tt["t"] if tt else x["tema"]
    return {"dias": por_dia, "retencion": retencion, "racha": racha(usuario),
            "areas": [{"id": a["id"], "nombre": a["nombre"], "icono": a["icono"], "color": a["color"],
                       "grupo": a["grupo"], "dominio": a["dominio"],
                       "temas": sum(len(m["temas"]) for m in a["modulos"]),
                       "dominados": sum(1 for m in a["modulos"] for t in m["temas"] if t["dominio"] >= 0.8)}
                      for a in mapa if a["id"] in mias],
            "dominados": tot["dom"] or 0, "vistos": tot["vis"] or 0,
            "tarjetas": fila("SELECT COUNT(*) n FROM tarjeta WHERE usuario=? AND suspendida=0", (usuario,))["n"],
            "apuntes": fila("SELECT COUNT(*) n FROM cuaderno WHERE usuario=?", (usuario,))["n"],
            "debiles": debiles}


# ------------------------------------------------- analítica y chequeo
@ruta("GET", "/api/analitica")
def r_analitica(usuario, q, d, h):
    return an.analitica(usuario)


def chequeo_pendiente(usuario):
    return next((x.publico() for x in ia.cola.trabajos.values()
                 if x.tipo == "chequeo" and x.usuario == usuario and x.estado in ("cola", "corriendo", "conflicto")), None)


def lanzar_chequeo(usuario, prioridad):
    perfil = perfil_de(usuario)
    return ia.nuevo("chequeo", lambda ctx: an.crear_chequeo(ctx, usuario, perfil), prioridad, usuario, "chequeo")


@ruta("GET", "/api/chequeos")
def r_chequeos(usuario, q, d, h):
    abierto = fila("""SELECT id FROM chequeo WHERE usuario=? AND completado IS NULL ORDER BY id DESC LIMIT 1""", (usuario,))
    return {"historial": an.historial(usuario), "abierto": abierto["id"] if abierto else None,
            "trabajo": chequeo_pendiente(usuario), "dia": an.dia_chequeo(usuario),
            "esta_semana": bool(fila("SELECT 1 FROM chequeo WHERE usuario=? AND semana=?", (usuario, an.clave_semana()))),
            "semana": an.aprendido_semana(usuario)}


@ruta("GET", "/api/chequeo")
def r_chequeo(usuario, q, d, h):
    c = fila("SELECT * FROM chequeo WHERE id=? AND usuario=?", (int(q["id"]), usuario))
    if not c:
        return {"error": "no existe"}
    for k in ("temas", "preguntas", "tarjetas", "resultado"):
        c[k] = json.loads(c[k]) if c[k] else None
    c["temas_info"] = [{"id": t, "t": (cur.tema(t, usuario) or {}).get("t", t)} for t in c["temas"] or []]
    return c


@ruta("POST", "/api/chequeo/crear")
def r_chequeo_crear(usuario, q, d, h):
    t = chequeo_pendiente(usuario)
    if t:
        return {"trabajo": t["id"], "estado": t["estado"]}
    j = lanzar_chequeo(usuario, 0)
    j.permiso = d.get("permiso")
    return trabajo_json(j)


@ruta("POST", "/api/chequeo/responder")
def r_chequeo_resp(usuario, q, d, h):
    r = an.responder_chequeo(usuario, int(d["id"]), d.get("respuestas", []), d.get("tarjetas", []))
    ad.invalidar(usuario)
    ad.actualizar_niveles(usuario)
    return r


@ruta("POST", "/api/chequeo/dia")
def r_chequeo_dia(usuario, q, d, h):
    dia = int(d.get("dia", 6))
    if not 0 <= dia <= 6:
        return {"error": "día inválido"}
    kv_set(f"chequeo_dia:{usuario}", dia)   # cada persona elige su día
    return {"ok": True, "dia": dia}



# ---------------------------------------------------------------- acciones
# Cada persona ve solo SU lista, sus pronósticos y sus alertas; precios, mapa y noticias de un símbolo son caché común.
def _pronostico_en_cola(usuario, simbolo, tipos=("pronostico", "relaciones")):
    return next((x for x in ia.cola.trabajos.values() if x.tipo in tipos and x.usuario == usuario
                 and x.etiqueta == simbolo and x.estado in ("cola", "corriendo", "conflicto")), None)


def _encolar_relaciones(usuario, s, prioridad=1):
    """Mapa de relaciones de fondo. Al correr se salta si ya está fresco (p. ej. lo hizo un pronóstico antes)."""
    if _pronostico_en_cola(usuario, s, ("relaciones",)):
        return None
    return ia.nuevo("relaciones", lambda ctx: ac.relaciones(ctx, s) if ac.necesita_relaciones(s) else {"omitido": True},
                    prioridad, usuario, s)


def _seguro(fn, *args):
    """Un dato opcional (p. ej. la beta, que pide el índice a internet) nunca tumba la vista entera."""
    try:
        return fn(*args)
    except Exception:
        traceback.print_exc()
        return None


def _simbolo(d):
    s = str(d.get("simbolo") or d.get("s") or "").strip()
    if not ac.valido(s):
        raise ValueError("símbolo inválido")
    return s if s.startswith("^") else s.upper()


@ruta("GET", "/api/acciones")
def r_acciones(usuario, q, d, h):
    rapido = q.get("rapido") == "1"   # «Hoy»: solo lo guardado, sin esperar a internet
    if not rapido:
        try:
            ac.evaluar(usuario)
        except Exception:   # sin internet o Yahoo caído: se cierran en la próxima visita
            traceback.print_exc()
    lista = ac.resumen(usuario, refrescar=not rapido)
    pend = {x.etiqueta: x.publico() for x in ia.cola.trabajos.values()
            if x.tipo in ("pronostico", "relaciones") and x.usuario == usuario and x.estado in ("cola", "corriendo", "conflicto")}
    for a in lista:
        a["trabajo"] = pend.get(a["simbolo"])
    try:
        cartera = ac.cartera(usuario) if not rapido else None
    except Exception:
        traceback.print_exc()
        cartera = None
    return {"acciones": lista, "calibracion": ac.calibracion(usuario), "descargo": ac.DESCARGO,
            "horizontes": ac.HORIZONTES, "cartera": cartera, "vista": ac.vista_de(usuario), "temas": ac.temas(), "subtemas": ac.subtemas(),
            "opciones": ac.VISTA_OPCIONES}


@ruta("POST", "/api/acciones/vista")
def r_acciones_vista(usuario, q, d, h):
    """Cómo ve la persona su lista: agrupar por tema/dividendos/sector/moneda, ordenar, ventana del dividendo…"""
    return {"ok": True, "vista": ac.guardar_vista(usuario, d)}


@ruta("GET", "/api/acciones/buscar")
def r_acciones_buscar(usuario, q, d, h):
    mias = set(ac.simbolos_de(usuario))
    return {"resultados": [dict(x, vigilada=x["simbolo"] in mias) for x in ac.buscar(q.get("q", ""))]}


@ruta("POST", "/api/acciones/vigilar")
def r_acciones_vigilar(usuario, q, d, h):
    s = ac.vigilar(usuario, _simbolo(d), d)
    if ac.necesita_relaciones(s) and not _pronostico_en_cola(usuario, s):   # el mapa (para noticias indirectas), de fondo
        _encolar_relaciones(usuario, s)
    threading.Thread(target=ac.actualizar_noticias, args=(s,), daemon=True).start()
    registrar(usuario, "accion", detalle={"simbolo": s, "que": "vigilar"})
    return {"ok": True, "simbolo": s}


@ruta("POST", "/api/acciones/quitar")
def r_acciones_quitar(usuario, q, d, h):
    ejecutar("DELETE FROM accion_vigilada WHERE usuario=? AND simbolo=?", (usuario, _simbolo(d)))
    return {"ok": True}


@ruta("POST", "/api/acciones/ajustar")
def r_acciones_ajustar(usuario, q, d, h):
    s = _simbolo(d)
    if not fila("SELECT 1 FROM accion_vigilada WHERE usuario=? AND simbolo=?", (usuario, s)):
        return {"error": "esa acción no está en tu lista"}

    def num(k):
        v = d.get(k)
        return None if v in (None, "") else float(v)
    cantidad, compra = num("cantidad"), num("precio_compra")
    if (cantidad is not None and cantidad < 0) or (compra is not None and compra < 0):
        return {"error": "la cantidad y el precio de compra no pueden ser negativos"}
    ejecutar("""UPDATE accion_vigilada SET alerta_arriba=?, alerta_abajo=?, alerta_pct=?, nota=?, cantidad=?, precio_compra=?
                WHERE usuario=? AND simbolo=?""",
             (num("alerta_arriba"), num("alerta_abajo"), num("alerta_pct"), str(d.get("nota") or "")[:500],
              cantidad, compra, usuario, s))
    return {"ok": True}


@ruta("POST", "/api/acciones/orden")
def r_acciones_orden(usuario, q, d, h):
    for k, s in enumerate(d.get("simbolos", [])[:60]):
        if ac.valido(str(s)):
            ejecutar("UPDATE accion_vigilada SET orden=? WHERE usuario=? AND simbolo=?", (k, usuario, s))
    return {"ok": True}


@ruta("GET", "/api/accion")
def r_accion(usuario, q, d, h):
    """Detalle de un símbolo. Si no está en la lista de la persona es una vista previa (sin pronósticos ni alertas)."""
    s = _simbolo(q)
    err = ac.cotizar([s])
    i = ac.info(s)
    if not i:
        return {"error": err.get(s) or "símbolo desconocido"}
    vig = fila("SELECT * FROM accion_vigilada WHERE usuario=? AND simbolo=?", (usuario, s))
    if vig:
        ejecutar("UPDATE accion_vigilada SET visto=? WHERE usuario=? AND simbolo=?", (time.time(), usuario, s))
    ind = ac.indicadores(i)
    t = _pronostico_en_cola(usuario, s, ("pronostico",)) or _pronostico_en_cola(usuario, s, ("relaciones",))
    return {"simbolo": s, "nombre": i["nombre"], "moneda": i["moneda"], "bolsa": i["bolsa"], "tipo": i["tipo"],
            "sector": i.get("sector") if i.get("sector") != "-" else "", "industria": i.get("industria"),
            "meta": i["meta"], "serie": [[x[0], x[1]] for x in i["serie"] or []], "indicadores": ind,
            "dividendos": {"vista": ac.dividendos_de(i, ac.vista_de(usuario)["dividendo_meses"]),
                           "meses": ac.vista_de(usuario)["dividendo_meses"],
                           "historial": [[t, a] for t, a in (i["meta"] or {}).get("dividendos", [])][-12:]},
            "velas": ac.velas(i["serie"]), "patrones": ac.patrones_velas(i["serie"]),
            "familia": _seguro(ac.familia, s, usuario), "con_composicion": bool(ac.REPRESENTANTE.get(s) or i["tipo"] == "ETF"),
            "lectura": ac.explicar_indicadores(ind), "relaciones": i.get("relaciones"),
            "mercado": _seguro(ac.frente_al_mercado, i),
            "noticias": ac.noticias(s), "noticias_fecha": i.get("noticias_fecha"),
            "vigilada": vig, "alertas": ac.alertas_de(vig, i["meta"] or {}) if vig else [],
            "pronosticos": ac.pronosticos(usuario, s) if vig else [], "conceptos": ac.conceptos(usuario),
            "trabajo": t.publico() if t else None, "descargo": ac.DESCARGO, "horizontes": ac.HORIZONTES,
            "error": err.get(s)}


@ruta("GET", "/api/accion/composicion")
def r_accion_composicion(usuario, q, d, h):
    """Qué empresas componen un fondo o índice y con qué porcentaje (datos públicos, en caché una semana)."""
    return {"composicion": ac.composicion(_simbolo(q))}


_familias_agregando = set()   # (usuario, clave) que se están agregando de fondo


@ruta("POST", "/api/acciones/familia")
def r_acciones_familia(usuario, q, d, h):
    """Pone en vigilancia una familia (por defecto el S&P 500 y su competencia; `familia` = clave o nombre). Las que
    tienen muchos símbolos (energía eléctrica: más de 200) se agregan de fondo y la respuesta es inmediata."""
    nombre = str(d.get("familia") or "sp500")[:80]
    f = next((x for x in ac.FAMILIAS if nombre in (x["clave"], x["nombre"])), None)
    if not f:
        raise ValueError("familia desconocida")
    total = sum(len(g[1]) for g in f["grupos"])
    if total <= 30:
        hechos, fallidos = ac.agregar_familia(usuario, f["clave"])
        registrar(usuario, "accion", detalle={"que": "familia", "familia": f["clave"], "agregados": len(hechos)})
        return {"ok": True, "agregados": hechos, "fallidos": fallidos}
    clave = (usuario, f["clave"])
    if clave in _familias_agregando:
        return {"ok": True, "agregados": [], "fallidos": {}, "en_curso": True}
    _familias_agregando.add(clave)

    def correr():
        try:
            hechos, fallidos = ac.agregar_familia(usuario, f["clave"])
            registrar(usuario, "accion", detalle={"que": "familia", "familia": f["clave"], "agregados": len(hechos),
                                                  "fallidos": len(fallidos)})
        except Exception:
            traceback.print_exc()
        finally:
            _familias_agregando.discard(clave)
    threading.Thread(target=correr, daemon=True).start()
    return {"ok": True, "agregados": [], "fallidos": {}, "en_segundo_plano": total}


@ruta("POST", "/api/accion/noticias")
def r_accion_noticias(usuario, q, d, h):
    return ac.actualizar_noticias(_simbolo(d), forzar=True)


@ruta("POST", "/api/accion/pronostico")
def r_accion_pronostico(usuario, q, d, h):
    s = _simbolo(d)
    if not fila("SELECT 1 FROM accion_vigilada WHERE usuario=? AND simbolo=?", (usuario, s)):
        return {"error": "agrega primero la acción a tu lista"}
    x = _pronostico_en_cola(usuario, s, ("pronostico",))
    if x:
        if x.prioridad > 0 and x.estado == "cola":
            ia.cola.subir(x)
        return trabajo_json(x)
    dias = int(d.get("dias") or 30)
    pu = d.get("p_usuario")
    pu = None if pu in (None, "") else max(1.0, min(99.0, float(pu)))
    t = ia.nuevo("pronostico", lambda ctx: ac.pronosticar(ctx, usuario, s, dias, pu), 0, usuario, s)
    t.permiso = d.get("permiso")
    return trabajo_json(t)


@ruta("POST", "/api/accion/relaciones")
def r_accion_relaciones(usuario, q, d, h):
    s = _simbolo(d)
    if not fila("SELECT 1 FROM accion_vigilada WHERE usuario=? AND simbolo=?", (usuario, s)):
        return {"error": "agrega primero la acción a tu lista"}
    t = _pronostico_en_cola(usuario, s, ("relaciones",))
    if t:
        if t.prioridad > 0 and t.estado == "cola":
            ia.cola.subir(t)
        return trabajo_json(t)
    ejecutar("UPDATE accion_info SET relaciones_fecha=0 WHERE simbolo=?", (s,))   # pedido a mano: se rehace
    return trabajo_json(_encolar_relaciones(usuario, s, 0))


def acciones_diarias(u):
    """Actualización diaria: cierra los pronósticos vencidos y, para cada acción vigilada, noticias + pronóstico a
    30 días (de fondo, detrás de lo de estudio) si el último tiene más de 20 h. `acciones_pronostico_diario`: False
    = solo noticias y alertas."""
    simbolos = ac.simbolos_de(u)
    if not simbolos:
        return
    try:
        ac.cotizar(simbolos)   # precios al día para el resumen de la mañana (Hermes) y «Hoy»
        ac.evaluar(u)
    except Exception:
        traceback.print_exc()
    diario = config.C.get("acciones_pronostico_diario", True)
    for s in simbolos:
        if _pronostico_en_cola(u, s) or ac.pronostico_bajo_demanda(s):
            continue
        ult = fila("SELECT creado FROM accion_pronostico WHERE usuario=? AND simbolo=? ORDER BY creado DESC LIMIT 1", (u, s))
        if diario and (not ult or time.time() - ult["creado"] > 20 * 3600):
            ia.nuevo("pronostico", lambda ctx, s=s: ac.pronosticar(ctx, u, s, 30), 1, u, s)
        elif ac.necesita_relaciones(s):
            _encolar_relaciones(u, s)


def lineas_acciones(u, refrescar=True):
    """Para Hermes: alertas activas y movimientos de la lista de la persona."""
    lista = ac.resumen(u, refrescar=refrescar)
    out = []
    en_grupos = 0
    for a in lista:
        if a["precio"] is None:
            continue
        if a.get("grupo") and not a["alertas"]:   # los grupos plegables (energía) no inflan el resumen: solo si alertan
            en_grupos += 1
            continue
        marca = "🔔 " if a["alertas"] else ""
        pr = a["pronostico"]
        out.append(f"{marca}{a['simbolo']} {a['precio']:.2f} {a['moneda'] or ''} ({a['cambio'] or 0:+.1f} %)"
                   + (f" — {', '.join(x['texto'] for x in a['alertas'])}" if a["alertas"] else "")
                   + (f" · pronóstico {pr['dias']} d: {pr['p_sube']:.0f} % de subir" if pr else ""))
    if en_grupos:
        out.append(f"(y {en_grupos} más en los grupos plegables de la Academia, sin alertas)")
    return out, any(a["alertas"] for a in lista)


# ---------------------------------------------------------------- Hermes
@ruta("GET", "/api/hermes/resumen")
def r_hermes(usuario, q, d, h):
    return h.texto(resumen_hermes(_hermes_para(h, q, usuario)), "text/markdown; charset=utf-8")


def _hermes_para(h, d, usuario):
    """Hermes (en el propio PC, sin cabecera) puede elegir la cuenta; desde el tailnet cada quien solo la suya."""
    pedido = d.get("usuario")
    return pedido if pedido and not h.tailscale() and h.de_confianza() and pedido in permitidos() else usuario


def resumen_hermes(usuario):
    perfil = perfil_de(usuario)
    pr = r_progreso(usuario, {}, {}, None)
    hoy = r_hoy(usuario, {}, {}, None)
    lineas = [f"# Academia — perfil de aprendizaje de {perfil.get('nombre') or usuario}", "",
              f"**Situación:** {perfil['situacion']}", f"**Metas:** {perfil['metas']}",
              f"**Estilo preferido:** {perfil['estilo']}", "",
              f"Racha: {pr['racha']} días · temas dominados: {pr['dominados']} · vistos: {pr['vistos']} · "
              f"tarjetas: {pr['tarjetas']} · retención 30 d: "
              + (f"{pr['retencion']:.0%}" if pr["retencion"] is not None else "sin datos"), "",
              "## Prioridad por área (0-3) y dominio actual"]
    for a in pr["areas"]:
        lineas.append(f"- {a['nombre']}: prioridad {perfil['pesos'].get(a['id'], '-')}, dominio {a['dominio']:.0%} "
                      f"({a['dominados']}/{a['temas']} temas)")
    lineas += ["", "## Lo que toca estudiar hoy"]
    lineas += [f"- {t['area']} › {t['modulo']} › {t['t']} (id `{t['id']}`)" for t in hoy["temas"]]
    lineas += [f"- Repasos pendientes: {hoy['repaso']['vencidas']} + {hoy['repaso']['nuevas']} nuevas"]
    if hoy["objetivos"]:
        lineas += ["", "## Objetivos activos"] + [f"- {o['titulo']} — {o['progreso']:.0%}" for o in hoy["objetivos"]]
    if pr["debiles"]:
        lineas += ["", "## Puntos débiles (más fallos en repasos, 30 días)"] + [
            f"- {x['t']} ({x['fallos']} fallos)" for x in pr["debiles"]]
    lineas += ["", "## Adaptación (lo que dicen sus datos)"] + [f"- {a}" for a in hoy["adaptacion"]["ajustes"]]
    reforzar = [t for t in hoy["temas"] if t["tipo"] == "recuperar"]
    if reforzar:
        lineas += ["", "## Reforzar (si estudian juntos, empieza por aquí)"] + [
            f"- {t['t']} (id `{t['id']}`): {t.get('motivo') or 'olvidado'}" for t in reforzar]
    try:
        acc, _ = lineas_acciones(usuario)
        if acc:
            lineas += ["", "## Acciones que vigila (precio, cambio del día, alertas y último pronóstico)"] + [f"- {x}" for x in acc]
    except Exception:
        traceback.print_exc()
    notas = filas("SELECT texto, fecha FROM nota WHERE usuario=? ORDER BY id DESC LIMIT 10", (usuario,))
    if notas:
        lineas += ["", "## Notas guardadas"] + [f"- {n['texto']}" for n in notas]
    return "\n".join(lineas) + "\n"


@ruta("POST", "/api/hermes/nota")
def r_hermes_nota(usuario, q, d, h):
    ejecutar("INSERT INTO nota(usuario,texto,origen,fecha) VALUES(?,?,?,?)",
             (_hermes_para(h, d, usuario), d["texto"], d.get("origen", "hermes"), time.time()))
    return {"ok": True}


@ruta("POST", "/api/hermes/tarjetas")
def r_hermes_tarjetas(usuario, q, d, h):
    return {"agregadas": agregar_tarjetas(_hermes_para(h, d, usuario), d.get("tarjetas", []), d.get("tema"),
                                          d.get("area"), d.get("idioma"), "hermes")}


@ruta("GET", "/api/hermes/siguiente")
def r_hermes_siguiente(usuario, q, d, h):
    """Mensaje corto para Telegram: lo que más rinde hoy (reforzar, temas, repaso, enfoque)."""
    u = _hermes_para(h, q, usuario)
    hoy = r_hoy(u, {}, {}, None)
    hz = aa.horizonte(u, perfil_de(u))
    lineas = ["🎓 Academia — lo que más rinde hoy"]
    reforzar = [t for t in hoy["temas"] if t["tipo"] == "recuperar" and not t["hecho"]]
    nuevos = [t for t in hoy["temas"] if t["tipo"] != "recuperar" and not t["hecho"]]
    if reforzar:
        lineas += ["♻️ Primero reforzar:"] + [f"  • {t['t']} — {t.get('motivo') or 'olvidado'}" for t in reforzar]
    if nuevos:
        lineas += ["📚 Nuevo:"] + [f"  • {t['area']} › {t['t']}" for t in nuevos]
    pend = hoy["repaso"]["vencidas"]
    if pend:
        lineas.append(f"🔁 {pend} tarjetas por repasar — escríbeme «repasemos» y te pregunto aquí.")
    if not (reforzar or nuevos or pend):
        lineas.append("✅ Hoy ya está todo hecho.")
    if hz["consejo"]:
        lineas.append("🔭 " + hz["consejo"][0])
    try:
        acc, alerta = lineas_acciones(u, refrescar=False)   # los precios los renovó la actualización diaria
        if alerta:   # en Telegram solo si alguna acción disparó una alerta
            lineas += ["💹 Acciones con alerta:"] + [f"  • {x}" for x in acc if x.startswith("🔔")]
    except Exception:
        traceback.print_exc()
    return h.texto("\n".join(lineas) + "\n", "text/plain; charset=utf-8")


@ruta("GET", "/api/hermes/acciones")
def r_hermes_acciones(usuario, q, d, h):
    """Texto para Telegram con TODA la lista vigilada (precio, cambio, alertas, pronóstico)."""
    acc, _ = lineas_acciones(_hermes_para(h, q, usuario))
    return h.texto("💹 Tus acciones\n" + ("\n".join(f"• {x}" for x in acc) or "No vigilas ninguna acción.") + "\n",
                   "text/plain; charset=utf-8")


@ruta("GET", "/api/hermes/alertas")
def r_hermes_alertas(usuario, q, d, h):
    """Para el cron de Hermes en horario de bolsa: SOLO las alertas que aún no avisó hoy (texto vacío = nada nuevo,
    y Hermes no manda nada). Cada alerta (símbolo + tipo) se avisa una vez al día."""
    u = _hermes_para(h, q, usuario)
    hoy_ = datetime.now().strftime("%Y-%m-%d")
    clave = f"alertas_avisadas:{u}"
    avisadas = kv_get(clave) or {}
    avisadas = {k: v for k, v in avisadas.items() if v == hoy_}
    nuevas = []
    for a in ac.resumen(u):
        for x in a["alertas"]:
            k = f"{a['simbolo']}:{x['tipo']}"
            if k not in avisadas:
                avisadas[k] = hoy_
                nuevas.append(f"🔔 {a['simbolo']} {a['precio']:.2f} {a['moneda'] or ''} ({a['cambio'] or 0:+.1f} %): {x['texto']}")
    kv_set(clave, avisadas)
    return h.texto("💹 Alertas de tus acciones\n" + "\n".join(nuevas) + "\n" if nuevas else "", "text/plain; charset=utf-8")


@ruta("GET", "/api/hermes/repaso")
def r_hermes_repaso(usuario, q, d, h):
    """Tarjetas para repasar por chat (Telegram): primero las vencidas, si no, las más débiles. Hermes muestra el
    frente, espera la respuesta, muestra el reverso y manda la nota (1 = no la recordé … 4 = fácil)."""
    u = _hermes_para(h, q, usuario)
    n = max(1, min(int(q.get("n") or 5), 20))
    cola, venc, _ = cola_repaso(u, perfil_de(u))
    tarjetas = [t for t in cola if t["estabilidad"] is not None][:n]
    origen = "vencidas"
    if not tarjetas:
        tarjetas, origen = ad.pulso(u, n), "pulso"
    return {"origen": origen, "vencidas": venc, "tarjetas": [
        {"id": t["id"], "frente": t["frente"], "reverso": t["reverso"], "tema": t["tema"], "area": t["area"]}
        for t in tarjetas]}


@ruta("POST", "/api/hermes/repaso")
def r_hermes_repasar(usuario, q, d, h):
    u = _hermes_para(h, d, usuario)
    t = fila("SELECT * FROM tarjeta WHERE id=? AND usuario=?", (d.get("id"), u))
    if not t or int(d.get("nota", 0)) not in (1, 2, 3, 4):
        return {"error": "tarjeta o nota inválida"}
    p = an.aplicar_repaso(u, t, int(d["nota"]), d.get("segundos"), "hermes")
    ad.invalidar(u)
    return {"ok": True, "vuelve_en_dias": round((p["vence"] - time.time()) / 86400, 1)}


@ruta("GET", "/api/hermes/examen")
def r_hermes_examen(usuario, q, d, h):
    """Material para que Hermes EXAMINE a la persona sobre un tema por chat (tutor examinador): preguntas de la propia lección con
    su respuesta modelo y los errores típicos (los distractores del quiz), para que repregunte hacia el error sin soltar la
    respuesta. Primero salen las preguntas que menos veces se han preguntado. No gasta IA: solo lee la lección ya escrita."""
    u = _hermes_para(h, q, usuario)
    tid = q.get("tema", "")
    t = cur.tema(tid, u)
    if not t:
        return {"error": "tema desconocido: busca el id con /api/hermes/buscar_tema"}
    r = fila("SELECT ejercicios FROM leccion WHERE usuario=? AND tema=? AND completa!=0", (u, tid))
    quiz = (json.loads(r["ejercicios"]).get("quiz") if r and r["ejercicios"] else None) or []
    if not quiz:
        return {"error": "este tema aún no tiene lección con preguntas: pídele a la persona que lo abra en la Academia o prepáralo"}
    previas = {}
    for x in filas("SELECT detalle FROM actividad WHERE usuario=? AND tipo='examen' AND tema=?", (u, tid)):
        k = (json.loads(x["detalle"] or "{}")).get("pregunta_id")
        if k is not None:
            previas[k] = previas.get(k, 0) + 1
    preguntas = []
    for i, p in enumerate(quiz):
        if p.get("tipo") == "opcion" and p.get("opciones"):
            ok = p["opciones"][p["correcta"]] if 0 <= p.get("correcta", -1) < len(p["opciones"]) else ""
            modelo = f"{ok}. {p.get('explicacion') or ''}".strip()
            errores = [o for k, o in enumerate(p["opciones"]) if k != p.get("correcta")]
        else:
            modelo, errores = p.get("explicacion") or "", []
        preguntas.append({"pregunta_id": i, "pregunta": p["pregunta"], "respuesta_modelo": modelo, "errores_tipicos": errores,
                          "veces_preguntada": previas.get(i, 0)})
    preguntas.sort(key=lambda x: (x["veces_preguntada"], x["pregunta_id"]))
    n = max(1, min(int(q.get("n") or 3), 8))
    return {"tema": tid, "titulo": t["t"], "area": t["area"], "preguntas": preguntas[:n],
            "protocolo": "Una pregunta a la vez; NO des la respuesta modelo ni los errores típicos. Si falla, repregunta hacia el error con "
                         "una pista (hasta 3). Puntúa de 0 a 1 con la respuesta modelo y manda la evidencia a POST /api/hermes/evidencia."}


@ruta("POST", "/api/hermes/evidencia")
def r_hermes_evidencia(usuario, q, d, h):
    """Hermes entrega lo que vio al examinar: puntaje 0-1, cuántas pistas hicieron falta y cuántas repreguntas. Queda como evidencia
    DIRECTA en la línea de tiempo (métrica `examen_tutor`); NO cambia el dominio del tema todavía (modo sombra, como pide el plan).
    Si fue floja (< 0,6) y trae la respuesta modelo, la pregunta pasa a tus tarjetas de repaso."""
    u = _hermes_para(h, d, usuario)
    tid = str(d.get("tema", ""))
    t = cur.tema(tid, u)
    try:
        puntaje = float(d.get("puntaje"))
    except (TypeError, ValueError):
        puntaje = None
    if not t or puntaje is None or not 0 <= puntaje <= 1:
        return {"error": "hace falta un tema válido y un puntaje entre 0 y 1"}
    ayudas = max(0, min(3, int(d.get("ayudas") or 0)))
    repreguntas = max(0, min(5, int(d.get("repreguntas") or 0)))
    registrar(u, "examen", tid, t["area"], puntaje,
              {"pregunta_id": d.get("pregunta_id"), "pregunta": str(d.get("pregunta") or "")[:300], "ayudas": ayudas,
               "repreguntas": repreguntas, "origen": "hermes"})
    out = {"ok": True, "tarjeta": 0}
    conf = ad.NIVELES_CONFIANZA.get(str(d.get("confianza") or ""))
    if conf is not None:
        registrar(u, "calibracion", tid, t["area"], 1.0 if puntaje >= 0.6 else 0.0, {"p": conf, "nivel": d["confianza"], "origen": "examen"})
    if puntaje < 0.6 and d.get("pregunta") and d.get("respuesta_modelo"):
        out["tarjeta"] = agregar_tarjetas(u, [{"frente": str(d["pregunta"])[:400], "reverso": str(d["respuesta_modelo"])[:800]}],
                                          tid, t["area"], None, "examen")
    return out


@ruta("GET", "/api/hermes/semanal")
def r_hermes_semanal(usuario, q, d, h):
    """Resumen ejecutivo de la semana en texto, SIN IA (semáforos, tiempo frente a la semana anterior, metas con fecha
    estimada y un siguiente paso). Lo recoge el cron semanal de Hermes y lo entrega a Telegram."""
    u = _hermes_para(h, q, usuario)
    return h.texto(ad.resumen_semanal(u, perfil_de(u)), "text/plain; charset=utf-8")


@ruta("GET", "/api/hermes/buscar_tema")
def r_hermes_buscar(usuario, q, d, h):
    palabra = (q.get("q") or "").lower()
    out = []
    for a in cur.areas(usuario).values():
        for m in a["modulos"]:
            for t in m["temas_obj"]:
                if palabra in t["t"].lower() or palabra in t["d"].lower() or palabra in m["t"].lower():
                    out.append({"id": t["id"], "tema": t["t"], "modulo": m["t"], "area": a["nombre"]})
    return {"temas": out[:30]}


# ------------------------------------------------------- trabajo de fondo
def hora_diaria():
    h = str(kv_get("hora_diaria") or ajustes().get("hora_diaria") or "06:00")
    m = re.match(r"^(\d{1,2}):(\d{2})$", h)
    return (int(m.group(1)) % 24, int(m.group(2)) % 60) if m else (6, 0)


def ultima_hora_programada(ahora=None):
    """Momento de la actualización diaria más reciente que ya debió ocurrir."""
    ahora = ahora or time.time()
    hh, mm = hora_diaria()
    d = datetime.fromtimestamp(ahora).replace(hour=hh, minute=mm, second=0, microsecond=0)
    if d.timestamp() > ahora:
        d -= timedelta(days=1)
    return d.timestamp()


def actualizacion_diaria():
    """Todo junto, una vez al día: fuentes de noticias, análisis con IA,
    síntesis y lecciones del día. Las tareas de IA van en orden por la cola
    (primero el análisis, luego las síntesis que lo usan, luego lecciones) y
    esperan solas si Hermes u otra app tiene la IA ocupada o estás jugando."""
    ahora = time.time()
    kv_set("diaria_ultima", ahora)
    nt.descargar(regiones_en_uso())
    pendientes_rutas = []
    for r in filas("SELECT usuario FROM perfil"):
        u = r["usuario"]
        perfil = perfil_de(u)
        if not activo(u, ahora):   # no entró en 2 días: no se le prepara nada (ahorra horas de IA); al volver, sigue
            continue
        # chequeo semanal: el día elegido (domingo por defecto), uno por semana ISO
        if (datetime.fromtimestamp(ahora).weekday() == an.dia_chequeo(u) and not chequeo_pendiente(u)
                and not fila("SELECT 1 FROM chequeo WHERE usuario=? AND semana=?", (u, an.clave_semana()))):
            lanzar_chequeo(u, 1)
        if not fila("SELECT 1 FROM instantanea WHERE usuario=? AND semana=?", (u, an.clave_semana())):
            ad.instantanea(u)   # foto semanal de su forma de aprender
        ad.actualizar_niveles(u)   # sube/baja de nivel profesional → historial
        ad.invalidar(u)
        plan = ad.plan_del_dia(u, perfil)
        if perfil.get("dia_maxima"):
            # Pedido de la persona: al levantarse, TODAS las sesiones del día ya escritas a máxima profundidad
            # (sin tope de adelantadas; las que estaban a profundidad normal se reescriben).
            preparar_lecciones(u, plan["recuperar"] + plan["temas"] + plan["extra"], 1, True)
        else:
            # Por adelantado, no por cuota: como máximo `lecciones_adelantadas` listas sin leer por persona
            faltan = [t for t in plan["recuperar"] + plan["temas"]
                      if not fila("SELECT 1 FROM leccion WHERE usuario=? AND tema=?", (u, t))]
            preparar_lecciones(u, faltan[:max(0, adelantadas() - sin_leer(u))], 1)
        if aa.formato(u)["recomendado"] == "esencial":   # no termina las lecciones largas: ruta rápida de cada una
            for t in plan["recuperar"] + plan["temas"] + plan["extra"]:
                aa.preparar_rapida(u, perfil_ia(u), t, 1)
        for oid in dominio.fronteras_vencidas(u)[:1]:   # frontera viva: cada meta se re-mapea cada 30 días
            if not _frontera_en_cola(u, oid):
                ia.nuevo("frontera", lambda ctx, oid=oid, u=u: dominio.generar_frontera(ctx, u, perfil_ia(u), oid),
                         1, u, str(oid))
        profundizar_lecciones(u, 1)   # las lecciones antiguas (cortas) se reescriben a fondo, 1 por día
        pendientes_rutas.append((u, perfil))   # se encolan después de las noticias (no las retrasan horas)
    # Noticias a la MÁXIMA profundidad, solo a esta hora (como todo lo demás): las que cada persona verá de sus
    # áreas pasan por análisis completo → comparación entre medios → explicación; y después las síntesis.
    # Van DESPUÉS de las lecciones del día en la cola: lo primero que se lee al levantarse son las lecciones.
    ia.nuevo("noticias", lambda ctx: _profundizar_noticias(), 1, None, "elegir a fondo")
    for u, perfil in pendientes_rutas:
        rutas_vivas(u, perfil)
        acciones_diarias(u)
    if any(not kv_get(f"consulta_en:{r}") for r, _ in cur.catalogo_modulos()):
        ia.nuevo("ciencia", lambda ctx: ciencia.traducir_modulos(ctx), 1, None, "consultas científicas")


def rutas_vivas(u, perfil):
    """Cada día, para cada ruta de la persona (áreas con prioridad > 0 y metas activas): nivel profesional vs.
    mercado (cada `mercado_cada_dias`) y revisión de la ruta (cada `revision_rutas_cada_dias`), en una sola tarea
    por ruta; y las rutas marcadas «preparar todo» re-encolan las lecciones que falten."""
    dias_r = float(config.C.get("revision_rutas_cada_dias") or 7)
    metas = cur.areas_de_metas(u)
    rutas = [a["id"] for a in cur.areas(u).values() if a["id"] in cur.areas_de(u) and not a.get("objetivo")
             and not a.get("idioma") and a.get("grupo") != "Idiomas" and cur.peso(a, perfil.get("pesos", {}), u, metas) > 0]
    rutas += [f"obj{o['id']}" for o in filas("SELECT id FROM objetivo WHERE usuario=? AND estado='activo'", (u,))
              if f"obj{o['id']}" in cur.areas(u)]
    for a in rutas:
        if revision.vencida(u, a, dias_r) and not _ruta_en_cola(u, a):
            ia.nuevo("ruta", lambda ctx, a=a, u=u: actualizar_ruta(ctx, u, a), 1, u, a)
    for a in kv_get(f"preparar_ruta:{u}") or []:
        if a in cur.areas(u):
            preparar_lecciones(u, _temas_ruta(u, a), PRIORIDAD_RUTA, bool(perfil.get("dia_maxima")))


def noticias_por_persona():
    return int(config.C.get("noticias_a_fondo_por_persona") or 8)


def adelantadas():
    v = config.C.get("lecciones_adelantadas")
    return 2 if v is None else int(v)   # 0 = no preparar nada por adelantado (solo al abrir la lección)


def activo(usuario, ahora=None):
    """Usó la Academia en las últimas 48 h (o acaba de crear su perfil): solo a esas personas se les prepara
    trabajo de fondo cada día."""
    desde = (ahora or time.time()) - 48 * 3600
    return bool(fila("SELECT 1 FROM actividad WHERE usuario=? AND fecha>? LIMIT 1", (usuario, desde))
                or fila("SELECT 1 FROM perfil WHERE usuario=? AND actualizado>?", (usuario, desde)))


def sin_leer(usuario):
    """Lecciones listas que aún no abre + las que ya están en cola para esa persona."""
    listas = fila("""SELECT COUNT(*) n FROM leccion l LEFT JOIN avance a ON a.usuario=l.usuario AND a.tema=l.tema
                     WHERE l.usuario=? AND l.completa!=0 AND a.visto IS NULL""", (usuario,))["n"]
    return listas + sum(1 for x in ia.cola.trabajos.values()
                        if x.tipo == "leccion" and x.usuario == usuario and x.estado in ("cola", "corriendo", "conflicto"))


def _profundizar_noticias(solo_pendientes=False):
    """Elige las noticias de hoy que verá cada persona (las n que más pesan en SUS áreas; la unión de todas) y encola
    cada una a máxima profundidad. Las síntesis van al final, cuando ya hay material a fondo. `solo_pendientes`
    (al reanudar tras un reinicio): solo las síntesis que no se escribieron desde la última actualización diaria."""
    elegidas = []
    for r in filas("SELECT usuario FROM perfil"):
        if not activo(r["usuario"]):
            continue
        mias = cur.areas_de(r["usuario"]) & set(nt.AREAS_NOTICIAS)
        if mias:
            elegidas += [i for i in nt.a_profundizar(mias, noticias_por_persona(), regiones_de(r["usuario"]))
                         if i not in elegidas]
    en_cola = {x.etiqueta for x in ia.cola.trabajos.values() if x.tipo == "a_fondo" and x.estado in ("cola", "corriendo", "conflicto")}
    for nid in elegidas:
        if str(nid) not in en_cola:
            ia.nuevo("a_fondo", lambda ctx, nid=nid: nt.a_fondo_completo(ctx, nid), 1, None, str(nid))
    ahora = time.time()
    for p in ("dia", "semana", "mes", "anio"):
        s = nt.sintesis_guardada(p)
        # día y semana se reescriben a diario; el mes cada semana; el año cada mes
        edad = {"dia": 0, "semana": 0, "mes": 7, "anio": 30}[p] * 86400
        if solo_pendientes and s and s["creada"] >= kv_get("diaria_ultima", 0):
            continue
        en_cola = any(x.tipo == "sintesis" and x.etiqueta == p and x.estado in ("cola", "corriendo", "conflicto")
                      for x in ia.cola.trabajos.values())
        if not en_cola and (not s or ahora - s["creada"] >= edad):
            ia.nuevo("sintesis", lambda ctx, p=p: nt.sintesis(ctx, p), 1, None, p)
    return {"a_fondo": len(elegidas)}


def reanudar():
    """La cola de la IA vive en memoria: al reiniciar el servidor se perdía todo lo pendiente (2026-10-28: 291 tareas,
    con ~12 reinicios en un día). Al arrancar se vuelve a encolar el trabajo de fondo que se puede reconstruir desde la
    base: lecciones a medio escribir, las del plan de hoy, las rutas marcadas «preparar todo», el contraste de fuentes
    de las lecciones recientes, los pronósticos de acciones del día y las noticias a fondo y síntesis que faltan. Lo que
    ya está hecho se salta solo (preparar_lecciones mira la base, a_profundizar descarta las noticias completas)."""
    n = 0
    for r in filas("SELECT usuario FROM perfil"):
        u = r["usuario"]
        if not activo(u):
            continue
        try:
            perfil = perfil_de(u)
            maxima = bool(perfil.get("dia_maxima"))
            a_medias = [x["tema"] for x in filas("SELECT tema FROM leccion WHERE usuario=? AND completa=0", (u,))]
            n += preparar_lecciones(u, a_medias, 1, maxima)
            plan = ad.plan_del_dia(u, perfil)
            del_dia = plan["recuperar"] + plan["temas"] + (plan["extra"] if maxima else [])
            if not maxima:
                del_dia = [t for t in del_dia if not fila("SELECT 1 FROM leccion WHERE usuario=? AND tema=?", (u, t))]
                del_dia = del_dia[:max(0, adelantadas() - sin_leer(u))]
            n += preparar_lecciones(u, del_dia, 1, maxima)
            for a in kv_get(f"preparar_ruta:{u}") or []:
                if a in cur.areas(u):
                    n += preparar_lecciones(u, _temas_ruta(u, a), PRIORIDAD_RUTA, maxima)
            if config.C.get("verificar_lecciones"):
                for x in filas("""SELECT l.tema FROM leccion l LEFT JOIN verificacion v ON v.usuario=l.usuario
                                  AND v.clave='tema:' || l.tema WHERE l.usuario=? AND l.completa!=0 AND l.creado>?
                                  AND v.clave IS NULL""", (u, time.time() - 3 * 86400)):
                    if not _verif_en_cola(u, f"tema:{x['tema']}"):
                        encolar_verificacion(u, x["tema"], 2)
                        n += 1
            acciones_diarias(u)   # pronósticos de acciones que no alcanzaron a hacerse hoy
            rutas_vivas(u, perfil)   # revisión de rutas y nivel vs. mercado (solo encola las vencidas que no estén en cola)
            for oid in dominio.fronteras_vencidas(u)[:1]:
                if not _frontera_en_cola(u, oid):
                    ia.nuevo("frontera", lambda ctx, oid=oid, u=u: dominio.generar_frontera(ctx, u, perfil_ia(u), oid),
                             1, u, str(oid))
                    n += 1
        except Exception:
            traceback.print_exc()
    try:   # noticias de hoy a máxima profundidad y síntesis que faltan (comunes a todas las personas)
        ia.nuevo("noticias", lambda ctx: _profundizar_noticias(solo_pendientes=True), 1, None, "elegir a fondo")
    except Exception:
        traceback.print_exc()
    if n:
        print(f"reanudadas {n} tareas de fondo tras el arranque", flush=True)
    _conciliar_cola()
    return n


_conciliada = []


def _conciliar_cola():
    """F0: compara lo que había pendiente antes de detenerse con lo que se logró volver a encolar (una vez por arranque,
    ya sea tras `reanudar()` o tras la rutina diaria atrasada, que también rehace la cola)."""
    if _conciliada:
        return
    _conciliada.append(1)
    try:
        inf = salud.conciliar([{"tipo": x.tipo, "usuario": x.usuario, "etiqueta": x.etiqueta, "estado": x.estado}
                               for x in list(ia.cola.trabajos.values())])
        if inf["antes"]:
            print(f"cola tras el reinicio: {inf['antes']} pendientes antes, {inf['recuperadas']} recuperadas, "
                  f"{len(inf['perdidas'])} no reconstruibles", flush=True)
    except Exception:
        traceback.print_exc()


_foto_metricas = {}


def _eventos_y_metricas():
    """F1, cada minuto: copia lo nuevo a la línea de tiempo de eventos y, una vez al día por persona, guarda la foto de sus métricas
    (el historial permite ver tendencias). Un fallo aquí nunca debe frenar al trabajador."""
    try:
        eventos.sincronizar()
        hoy = time.strftime("%Y-%m-%d")
        for r in filas("SELECT usuario FROM perfil"):
            if _foto_metricas.get(r["usuario"]) != hoy:
                metricas.guardar_foto(r["usuario"])
                _foto_metricas[r["usuario"]] = hoy
    except Exception:
        traceback.print_exc()


def trabajador():
    """Revisa cada minuto si ya pasó la hora diaria (config/academia.json,
    «hora_diaria», 06:00 por defecto). Si el PC estaba apagado a esa hora,
    se pone al día apenas arranca; si no, reanuda lo pendiente (reanudar)."""
    escaneo.purgar(config.DATOS)
    time.sleep(20)
    try:
        for r in filas("SELECT usuario FROM perfil"):   # F0: la línea base de uso queda guardada para todos, no solo al abrir 🩺
            salud.linea_base(r["usuario"])
    except Exception:
        traceback.print_exc()
    try:
        if kv_get("diaria_ultima", 0) >= ultima_hora_programada():
            reanudar()
    except Exception:
        traceback.print_exc()
    while True:
        try:
            escaneo.purgar(config.DATOS)          # el escaneo del PC no vive más de 24 h
            if kv_get("diaria_ultima", 0) < ultima_hora_programada():
                salud.correr_diaria(actualizacion_diaria)
            _conciliar_cola()
            _eventos_y_metricas()
            avisos.enviar_pendientes(resumen_aviso, [r["usuario"] for r in filas("SELECT usuario FROM perfil")])
        except Exception:
            traceback.print_exc()
        time.sleep(60)


@ruta("POST", "/api/horario")
def r_horario(usuario, q, d, h):
    if not es_admin(h, usuario):   # la hora de la actualización diaria es de toda la Academia
        return {"error": "solo el administrador puede cambiar la hora de la actualización diaria"}
    hora = str(d.get("hora", ""))
    if not re.match(r"^([01]?\d|2[0-3]):[0-5]\d$", hora):
        return {"error": "hora inválida (usa HH:MM)"}
    kv_set("hora_diaria", hora)  # en la base: el servicio solo puede escribir en datos/
    return {"ok": True, "hora": hora, "proxima": ultima_hora_programada() + 86400}


def main():
    n_antes = salud.al_arrancar()   # lo que quedó pendiente del proceso anterior (se concilia en reanudar)
    if n_antes:
        print(f"el diario de la cola tenía {n_antes} tareas pendientes del arranque anterior", flush=True)
    cur.cargar()
    nube.enlazar(perfil_de, _admin_cuenta)
    threading.Thread(target=trabajador, daemon=True, name="trabajador").start()
    srv = ThreadingHTTPServer((HOST, PUERTO), Manejador)
    srv.daemon_threads = True
    print(f"Academia en http://{HOST}:{PUERTO}", flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    main()
