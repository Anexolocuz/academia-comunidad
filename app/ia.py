"""IA local (llama-swap) + buscador (SearXNG) con una sola cola de trabajos.

llama-swap atiende un modelo a la vez (--parallel 1) y al cargar uno descarga
el anterior. Por eso todo lo que la Academia le pide a la IA pasa por esta cola:

* prioridad 0 = algo que el usuario está esperando en pantalla;
* prioridad 1 = trabajo de fondo (adelantar lecciones, analizar noticias).

Respeto a las otras apps: si otro modelo está cargado (un agente como Hermes,
Open WebUI...) el trabajo de fondo espera, y uno interactivo pregunta antes de
interrumpir (o usa el modelo ligero). Si el monitor de GPU (aigate_url: JSON con «busy» o «game») dice que estás jugando, el
fondo también espera.
"""
import heapq
import itertools
import json
import re
import os
import threading
import time
import traceback
import urllib.parse
import urllib.request
import uuid

import config

# La configuración se lee en cada uso: cambiarla en Ajustes aplica sin reiniciar.
def _c(clave):
    return config.C.get(clave) or ""


def LLAMA():
    return _c("ia_url").rstrip("/").removesuffix("/v1")


def COMPATIBLES():
    """Modelos que pueden estar cargados sin conflicto: el nuestro, el ligero y los
    que el servidor deja convivir (config «modelos_compatibles», p. ej. el de Hermes)."""
    return ({_c("modelo"), _c("modelo_ligero")} | set(_c("modelos_compatibles") or [])) - {""}


class _Modelo:  # compatibilidad: ia.MODELO se usa como texto en otros módulos
    def __str__(self):
        return _c("modelo")

    def __format__(self, f):
        return format(str(self), f)


MODELO = _Modelo()


class Conflicto(Exception):
    def __init__(self, otros):
        super().__init__("otro modelo en uso")
        self.otros = otros


def _get_json(url, timeout=5):
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return json.loads(r.read())


def modelos_cargados():
    try:
        return [m.get("model") for m in _get_json(f"{LLAMA()}/running").get("running", [])]
    except Exception:
        return []


def pc_ocupado():
    """True si aigate detecta un juego o la GPU muy usada."""
    if not _c("aigate_url"):
        return False
    try:
        st = _get_json(_c("aigate_url"), 3)
        return bool(st.get("busy") or st.get("game"))
    except Exception:
        return False


def modelos_pedidos():
    """Modelos con peticiones en curso o ESPERANDO turno en llama-swap (evento «inflight» de /api/events).
    Sirve para ceder el paso: si Hermes pide su modelo mientras la Academia trabaja, llama-swap espera a que la
    Academia suelte el suyo; sin esto, con 2 tareas mandando peticiones sin parar, Hermes no entraba nunca."""
    try:
        with urllib.request.urlopen(f"{LLAMA()}/api/events", timeout=3) as r:
            for _ in range(300):
                linea = r.readline()
                if not linea:
                    break
                if b'"inflight"' in linea and b"snapshot" in linea:
                    d = json.loads(json.loads(linea[5:])["data"])
                    return {x.get("model") for x in d.get("requests") or []} - {None}
    except Exception:
        pass
    return set()


def otros_modelos(esperando=False):
    """Modelos de otras apps cargados (y, con esperando=True, también los que están pidiendo turno)."""
    otros = [m for m in modelos_cargados() if m not in COMPATIBLES()]
    if esperando:
        otros += [m for m in modelos_pedidos() if m not in COMPATIBLES() and m not in otros]
    return otros


EVITAR = ("youtube.com", "youtu.be", "tiktok.com", "facebook.com", "instagram.com", "pinterest.", "x.com/",
          "twitter.com", "reddit.com", "quora.com", "brainly.", "scribd.com", "slideshare.net", "linkedin.com")
CONFIABLES = (".edu", ".gov", ".ac.", "wikipedia.org", "openstax.org", "libretexts.org", "khanacademy.org",
              "britannica.com", "nature.com", "science.org", "ieee.org", "mit.edu", "stanford.edu", "nih.gov",
              "nasa.gov", "who.int", "un.org", "imf.org", "worldbank.org", "banrep.gov.co", "investopedia.com",
              "mathworks.com", "arxiv.org", "acm.org", "unam.mx", "unal.edu.co", ".edu.co", "docs.", "developer.mozilla")


def _confianza(url):
    return 2 if any(c in url for c in CONFIABLES) else 1


def buscar_web(consulta, n=6, idioma="es"):
    """Resultados de SearXNG local: [{titulo, url, texto}], sin redes sociales
    y con las fuentes académicas/oficiales primero."""
    if not _c("searx_url"):
        return []
    q = urllib.parse.urlencode({"q": consulta, "format": "json", "language": idioma})
    try:
        datos = _get_json(f"{_c('searx_url').rstrip('/')}/search?{q}", 20)
    except Exception:
        return []
    vistos, out = set(), []
    for r in datos.get("results", []):
        u = r.get("url")
        if not u or u in vistos or any(e in u for e in EVITAR):
            continue
        vistos.add(u)
        out.append({"titulo": (r.get("title") or "")[:200], "url": u,
                    "texto": (r.get("content") or "")[:500]})
    out.sort(key=lambda r: -_confianza(r["url"]))  # orden estable: dentro de cada grupo manda SearXNG
    return out[:n]


# ------------------------------------------------------------------ trabajos
class Trabajo:
    def __init__(self, tipo, fn, prioridad=0, usuario=None, etiqueta=""):
        self.id = uuid.uuid4().hex[:12]
        self.tipo, self.fn, self.prioridad = tipo, fn, prioridad
        self.usuario, self.etiqueta = usuario, etiqueta
        self.estado = "cola"      # cola | corriendo | conflicto | listo | error
        self.texto = ""           # salida parcial (se ve mientras escribe)
        self.fase = ""            # "buscando fuentes", "escribiendo"...
        self.resultado = None
        self.error = None
        self.permiso = None       # None | "interrumpir" | "ligero"
        self.otros = []
        self.creado = time.time()
        self.no_antes = 0
        self.terminado = None

    def publico(self):
        return {"id": self.id, "tipo": self.tipo, "estado": self.estado, "texto": self.texto,
                "fase": self.fase, "resultado": self.resultado, "error": self.error,
                "otros": self.otros, "etiqueta": self.etiqueta,
                "pos": cola.posicion(self) if self.estado == "cola" else 0}


MAX_PARALELOS = 4


def paralelos():
    """Cuántas tareas manda la Academia a la vez al servidor de IA (configuración `trabajos_paralelos`).
    Debe coincidir con los «slots» del servidor (llama-server --parallel N); si no, solo se encolan allá."""
    try:
        return max(1, min(MAX_PARALELOS, int(config.C.get("trabajos_paralelos") or 1)))
    except (TypeError, ValueError):
        return 1


class Cola:
    def __init__(self):
        self._h, self._cv = [], threading.Condition()
        self._n = itertools.count()
        self.trabajos = {}
        self.actuales = []    # las que corren ahora (hasta `paralelos()` a la vez)
        for i in range(MAX_PARALELOS):   # los hilos de más duermen; así el número se cambia sin reiniciar
            threading.Thread(target=self._bucle, args=(i,), daemon=True, name=f"ia-cola-{i}").start()

    @property
    def actual(self):
        return self.actuales[0] if self.actuales else None

    def poner(self, t):
        with self._cv:
            self.trabajos[t.id] = t
            heapq.heappush(self._h, (t.prioridad, next(self._n), t))
            self._cv.notify()
        return t

    def posicion(self, t):
        with self._cv:
            orden = sorted(self._h)
            for i, (_, _, x) in enumerate(orden):
                if x is t:
                    return i + 1 + len(self.actuales)
        return 0

    def lista(self):
        """Lo que hace y hará la IA, en orden: el actual, la cola (como la va a tomar) y los que esperan
        a que otra app suelte la IA (conflicto)."""
        with self._cv:
            ahora = time.time()
            orden = sorted(self._h, key=lambda x: (x[2].no_antes > ahora, x[0], x[1]))
            out = list(self.actuales)
            out += [x[2] for x in orden]
            out += [t for t in self.trabajos.values() if t.estado == "conflicto" and t not in out]
            return out

    def hay_interactivo(self):
        with self._cv:
            return any(p == 0 for p, _, _ in self._h) or any(t.prioridad == 0 for t in self.actuales)

    def pendientes_fondo(self, tipo=None):
        with self._cv:
            return sum(1 for p, _, t in self._h if p == 1 and (tipo is None or t.tipo == tipo))

    def decidir(self, tid, permiso):
        t = self.trabajos.get(tid)
        if t and t.estado == "conflicto":
            t.permiso, t.estado = permiso, "cola"
            self.poner(t)
        return t

    def reintentar(self, t):
        """Vuelve a poner en la cola un trabajo que falló (botón 🔄 de la Academia). Corre la misma función desde cero."""
        with self._cv:
            if t.estado != "error":
                return False
            t.estado, t.error, t.texto, t.fase, t.resultado = "cola", None, "", "", None
            t.terminado, t.no_antes, t.permiso, t.otros = None, 0, None, []
            t.reintentos = getattr(t, "reintentos", 0) + 1
            t.pedidos = 0
            heapq.heappush(self._h, (t.prioridad, next(self._n), t))
            self._cv.notify()
        return True

    def subir(self, t):
        """Pasa un trabajo de fondo a interactivo (el usuario lo está esperando)."""
        with self._cv:
            self._h = [x for x in self._h if x[2] is not t]
            heapq.heapify(self._h)
            t.prioridad, t.no_antes = 0, 0
            heapq.heappush(self._h, (0, next(self._n), t))
            self._cv.notify()

    def _bucle(self, n=0):
        ultimo_chequeo = 0
        while True:
            if n >= paralelos():   # hilo de sobra con la configuración actual
                time.sleep(5)
                continue
            with self._cv:
                if time.time() - ultimo_chequeo > 20:
                    ultimo_chequeo = time.time()
                    self._reintentar_conflictos()
                ahora = time.time()
                listos = [x for x in self._h if x[2].no_antes <= ahora]
                if not listos:
                    self._cv.wait(5)
                    continue
                item = min(listos)
                self._h.remove(item)
                heapq.heapify(self._h)
                t = item[2]
                self.actuales.append(t)
            try:
                self._correr(t)
            finally:
                with self._cv:
                    self.actuales.remove(t)
                    self._limpiar()

    def _reintentar_conflictos(self):
        # Una tarea en «conflicto» = esperando en la cola a que otra app suelte la IA; vuelve sola en cuanto quede libre
        esperando = [t for t in self.trabajos.values() if t.estado == "conflicto"]
        if esperando and not otros_modelos():
            for t in esperando:
                t.estado = "cola"
                heapq.heappush(self._h, (t.prioridad, next(self._n), t))

    def _correr(self, t):
        ocupado = t.prioridad > 0 and pc_ocupado()
        if t.prioridad > 0 and (ocupado or otros_modelos(esperando=True)):
            # fondo: con el PC ocupado (juego…) reintentar en 10 min; si solo es otra app de IA (Hermes), en 1 min,
            # para que la Academia retome apenas Hermes suelte la tarjeta
            t.no_antes = time.time() + (600 if ocupado else 60)
            with self._cv:
                heapq.heappush(self._h, (t.prioridad, next(self._n), t))
            return
        t.estado = "corriendo"
        try:
            t.resultado = t.fn(Contexto(t))
            t.estado = "listo"
        except Conflicto as c:
            t.estado, t.otros = "conflicto", c.otros
        except Exception as e:
            traceback.print_exc()
            t.estado, t.error = "error", f"{type(e).__name__}: {e}"
        t.terminado = time.time()

    def _limpiar(self):
        # los terminados bien se olvidan a la hora; los fallidos se guardan 24 h para poder reintentarlos
        ahora = time.time()
        for k in [k for k, t in self.trabajos.items()
                  if t.terminado and t.terminado < ahora - (86400 if t.estado == "error" else 3600)]:
            del self.trabajos[k]


class Contexto:
    """Lo que recibe la función de un trabajo para hablar con la IA."""

    def __init__(self, trabajo):
        self.t = trabajo

    def fase(self, texto):
        self.t.fase = texto

    def _modelo(self):
        if self.t.permiso == "ligero" and _c("modelo_ligero"):
            return _c("modelo_ligero")
        cede = self.t.permiso != "interrumpir" or not config.C.get("permitir_interrumpir", True)
        otros = otros_modelos(esperando=True)
        if otros and cede:
            if not getattr(self.t, "pedidos", 0):
                raise Conflicto(otros)          # aún no empezó: vuelve a la cola sin perder nada
            # A mitad de una tarea: se pausa AQUÍ (no se pierde lo avanzado) hasta que la otra app termine y su
            # modelo se descargue (ttl de llama-swap). Así Hermes entra apenas lo pides.
            fase = self.t.fase
            while otros:
                self.t.fase = f"⏸ Pausada: {', '.join(otros)} usa la IA; sigue sola al terminar"
                time.sleep(20)
                otros = otros_modelos(esperando=True)
            self.t.fase = fase
        self.t.pedidos = getattr(self.t, "pedidos", 0) + 1
        return _c("modelo")

    def chat(self, mensajes, max_tokens=1800, temperatura=0.6, esquema=None, mostrar=True, semilla=None):
        """Llama al modelo con streaming. Si `esquema` (JSON Schema) se da,
        la salida queda forzada a ese formato y se devuelve ya parseada; si el
        modelo se enreda (JSON cortado), se reintenta una vez con más margen."""
        try:
            return self._chat(mensajes, max_tokens, temperatura, esquema, mostrar, semilla)
        except ValueError:
            if not esquema:
                raise
            self.fase((self.t.fase or "") + " (reintento)")
            extra = [{"role": "user", "content": "Responde de nuevo SOLO con el JSON, compacto en una sola línea, "
                                                 "con textos breves."}]
            return self._chat(mensajes + extra, int(max_tokens * 1.5), min(1.0, temperatura + 0.2), esquema, mostrar,
                              semilla + 1 if semilla else None)

    def _chat(self, mensajes, max_tokens, temperatura, esquema, mostrar, semilla=None):
        cuerpo = {"model": self._modelo(), "messages": mensajes, "stream": True,
                  "max_tokens": max_tokens, "temperature": temperatura,
                  "chat_template_kwargs": {"enable_thinking": False}}
        if semilla is not None:
            cuerpo["seed"] = semilla
        if esquema:
            cuerpo["response_format"] = {"type": "json_schema",
                                         "json_schema": {"name": "salida", "schema": esquema}}
        req = urllib.request.Request(f"{LLAMA()}/v1/chat/completions",
                                     data=json.dumps(cuerpo).encode(),
                                     headers={"Content-Type": "application/json"})
        salida = []
        if mostrar:
            self.t.texto = ""
        with urllib.request.urlopen(req, timeout=1800) as r:
            for linea in r:
                linea = linea.strip()
                if not linea.startswith(b"data:"):
                    continue
                dato = linea[5:].strip()
                if dato == b"[DONE]":
                    break
                try:
                    trozo = json.loads(dato)["choices"][0]["delta"].get("content") or ""
                except (ValueError, KeyError, IndexError):
                    continue
                salida.append(trozo)
                if mostrar:
                    self.t.texto += trozo
                if len(salida) % 40 == 0 and en_bucle("".join(salida[-200:])):
                    raise ValueError("el modelo entró en un bucle de repetición")
        texto = "".join(salida).strip()
        if esquema:
            return parsear_json(texto)
        return texto


def en_bucle(texto):
    """True si el final del texto es un mismo trozo repetido (p. ej. '\\text{ }' 50 veces)."""
    cola_ = texto[-320:]
    if len(cola_) < 320:
        return False
    for largo in range(1, 41):
        patron = cola_[-largo:]
        if patron.strip() and cola_.count(patron) * largo >= 290:
            return True
    return False


# Comandos LaTeX que el modelo escribe con UNA barra dentro de cadenas JSON: \t \f \b \r \n se
# interpretarían como tabulación, salto, etc. («\times» → TAB + «imes»). Se duplica la barra antes de parsear.
LATEX = set("""text textbf textit mathrm mathbf mathcal times cdot div pm mp frac dfrac tfrac sqrt sum prod int oint lim
infty partial nabla Delta delta theta Theta alpha beta gamma Gamma epsilon varepsilon zeta eta lambda Lambda mu nu
xi pi Pi rho sigma Sigma tau phi Phi varphi chi psi Psi omega Omega approx neq ne leq le geq ge equiv sim propto
rightarrow leftarrow Rightarrow Leftarrow leftrightarrow to mapsto in notin subset subseteq cup cap forall exists
vec hat bar dot ddot overline underline left right big Big quad qquad circ angle perp parallel degree log ln exp sin
cos tan sec csc cot arcsin arccos arctan sinh cosh tanh max min arg det dim ker over binom choose cdots ldots dots
boxed operatorname begin end matrix pmatrix bmatrix cases align frac mathbb ell hbar Re Im wedge vee neg land lor
oplus otimes star dagger prime emptyset varnothing triangle square""".split())
_RE_LATEX = re.compile(r'(?<!\\)\\([A-Za-z]+)')


def proteger_latex(texto):
    return _RE_LATEX.sub(lambda m: "\\\\" + m.group(1) if m.group(1) in LATEX else m.group(0), texto)


def parsear_json(texto):
    try:
        return json.loads(proteger_latex(texto))
    except ValueError:
        texto = proteger_latex(texto)
        a, b = texto.find("{"), texto.rfind("}")
        if a >= 0 and b > a:
            return json.loads(texto[a:b + 1])
        raise


cola = Cola()


def nuevo(tipo, fn, prioridad=0, usuario=None, etiqueta=""):
    return cola.poner(Trabajo(tipo, fn, prioridad, usuario, etiqueta))
