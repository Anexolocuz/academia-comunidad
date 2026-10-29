"""Acciones bajo vigilancia: cotizaciones, noticias que las mueven y pronóstico por escenarios.

1. Datos de mercado (sin IA, sin claves): búsqueda y precios diarios de 2 años de Yahoo Finance
   (`buscar`, `cotizar`), con caché en la base (tabla `accion_info`).
2. Indicadores calculados aquí (`indicadores`): rendimientos, volatilidad, medias móviles, RSI, máximos y mínimos de
   52 semanas y, sobre todo, la **tasa base**: con qué frecuencia la acción subió en ventanas del mismo largo que el
   horizonte del pronóstico, y el rango estadístico donde suele terminar el precio.
3. Noticias (`actualizar_noticias`): **directas** (las que nombran a la empresa: Yahoo Finance por símbolo y Google
   Noticias en español e inglés) e **indirectas** (competidores, proveedores, clientes y factores de los que depende,
   según su mapa de relaciones; también las noticias que la Academia ya descarga para tus áreas).
4. IA local: `relaciones` arma el mapa de la empresa (una vez al mes) y `pronosticar` clasifica cada noticia (directa
   o indirecta, por qué la afecta, impacto -2…+2) y escribe escenarios con su probabilidad, que el código convierte en
   «muy probable», «probable», «poco probable» o «muy poco probable». La probabilidad de subir queda anclada a la tasa
   base (±20 puntos como máximo): las noticias mueven la estimación, no la inventan.
5. Aprender del resultado (`evaluar`): al vencer el horizonte se compara con el precio real (acierto de dirección,
   puntaje de Brier y si cayó dentro del rango). Si la persona dejó su propia estimación, también se mide la suya.

Cada persona tiene su lista (`accion_vigilada`), sus pronósticos y sus alertas; los precios, el mapa de relaciones y
las noticias de cada símbolo son datos públicos y se comparten como caché. Nada de esto es asesoría financiera.
"""
import html as _html
import json
import math
import re
import statistics
import threading
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

import curriculo as cur
import noticias as nt
from base import ejecutar, fila, filas

ejecutar("""CREATE TABLE IF NOT EXISTS accion_info (
  simbolo TEXT PRIMARY KEY, nombre TEXT, moneda TEXT, bolsa TEXT, tipo TEXT, sector TEXT, industria TEXT,
  meta TEXT,                 -- JSON: precio, cambio del día, máximos/mínimos (de Yahoo)
  serie TEXT,                -- JSON [[ts, cierre, máximo, mínimo, volumen], ...] diario, 2 años
  actualizado REAL,
  relaciones TEXT, relaciones_fecha REAL,   -- mapa de la IA (competidores, proveedores, factores…)
  noticias_fecha REAL)""")
ejecutar("""CREATE TABLE IF NOT EXISTS accion_vigilada (
  usuario TEXT, simbolo TEXT, orden INTEGER DEFAULT 0, nota TEXT,
  alerta_arriba REAL, alerta_abajo REAL, alerta_pct REAL DEFAULT 4,   -- avisar si el precio cruza o se mueve ±x % en el día
  visto REAL, agregada REAL, PRIMARY KEY (usuario, simbolo))""")
for _col in ("cantidad REAL", "precio_compra REAL"):   # 💼 cartera (2026-10-28): cuántas tiene y a qué precio
    if _col.split()[0] not in {r["name"] for r in filas("PRAGMA table_info(accion_vigilada)")}:
        ejecutar(f"ALTER TABLE accion_vigilada ADD COLUMN {_col}")
# Velas (2026-10-29): las series guardadas antes no traen la apertura; se marcan viejas para bajarlas de nuevo
ejecutar("""UPDATE accion_info SET actualizado=0 WHERE serie IS NOT NULL AND serie!='[]'
            AND json_array_length(json_extract(serie,'$[0]'))<6""")
ejecutar("""CREATE TABLE IF NOT EXISTS accion_composicion (
  simbolo TEXT PRIMARY KEY, fuente TEXT, fecha_datos TEXT, total INTEGER, filas TEXT, actualizado REAL)""")
ejecutar("""CREATE TABLE IF NOT EXISTS accion_noticia (
  id INTEGER PRIMARY KEY AUTOINCREMENT, simbolo TEXT, url TEXT, titulo TEXT, resumen TEXT, fuente TEXT,
  publicada REAL, relacion TEXT,      -- directa | indirecta
  via TEXT,                           -- por qué está ligada (consulta, competidor, factor, palabra)
  analisis TEXT,                      -- JSON de la IA: relevante, via, impacto -2..2, plazo, resumen
  UNIQUE (simbolo, url))""")
ejecutar("CREATE INDEX IF NOT EXISTS accion_noticia_pub ON accion_noticia(simbolo, publicada)")
ejecutar("""CREATE TABLE IF NOT EXISTS accion_pronostico (
  id INTEGER PRIMARY KEY AUTOINCREMENT, usuario TEXT, simbolo TEXT, creado REAL, dias INTEGER, precio REAL,
  p_sube REAL,            -- 0..100 (IA, anclada a la tasa base)
  p_usuario REAL,         -- 0..100 la estimación propia de la persona, si la dio (opcional)
  datos TEXT,             -- JSON: escenarios, rango, tasa base, noticias usadas…
  resultado TEXT)""")     # JSON al vencer el horizonte: precio final, acierto, Brier, dentro del rango
ejecutar("CREATE INDEX IF NOT EXISTS accion_pronostico_u ON accion_pronostico(usuario, simbolo, creado)")

UA = "Mozilla/5.0 (X11; Linux x86_64) Academia/1 (seguimiento personal de acciones; software libre)"
YAHOO = "https://query1.finance.yahoo.com"
SIMBOLO = re.compile(r"^[A-Za-z0-9.\-^=]{1,20}$")
TIPOS = {"EQUITY": "acción", "ETF": "ETF", "INDEX": "índice", "MUTUALFUND": "fondo", "CRYPTOCURRENCY": "cripto",
         "CURRENCY": "divisa", "FUTURE": "futuro"}
COTIZACION_VIGENTE = 300          # s: precios de menos de 5 min no se vuelven a pedir
NOTICIAS_VIGENTES = 3 * 3600      # s: las noticias de un símbolo se buscan como mucho cada 3 h (salvo a mano)
RELACIONES_VIGENTES = 30 * 86400
DIAS_NOTICIAS = 14
HORIZONTES = (7, 30, 90)
DESCARGO = ("Pronóstico educativo hecho por una IA local con noticias públicas y estadística del propio precio. "
            "No es asesoría financiera: no compres ni vendas solo por esto.")

# Probabilidad → etiqueta (la decide el código, no la IA, para que signifique siempre lo mismo)
ETIQUETAS = ((70, "muy probable"), (45, "probable"), (20, "poco probable"), (0, "muy poco probable"))

# Qué tema del currículo explica cada parte de la vista (solo se muestran los que existen)
CONCEPTOS = [("finanzas.inversion.1", "Volatilidad, riesgo y rendimiento"),
             ("finanzas.inversion.0", "Clases de activos"),
             ("finanzas.valoracion.1", "Valoración relativa (múltiplos)"),
             ("finanzas.mercados.2", "Gestión de riesgos (VaR, coberturas)"),
             ("finanzas.mercados.3", "Finanzas cuantitativas y backtesting"),
             ("finanzas.inversion.4", "Psicología del inversor")]

PAPELES = {"competidores": "competidor", "proveedores": "proveedor", "clientes": "cliente"}

_red = threading.Lock()   # Google Noticias de a una consulta por vez (sin ráfagas)


def etiqueta(p):
    return next(e for umbral, e in ETIQUETAS if p >= umbral)


def valido(s):
    return bool(s and SIMBOLO.match(s))


def _get(url, timeout=15):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


# ------------------------------------------------------------------ mercado
def buscar(q):
    """Símbolos que coinciden con el texto (nombre o símbolo), de Yahoo Finance."""
    q = (q or "").strip()[:60]
    if not q:
        return []
    url = f"{YAHOO}/v1/finance/search?" + urllib.parse.urlencode({"q": q, "quotesCount": 10, "newsCount": 0,
                                                                 "lang": "es-419", "region": "CO"})
    try:
        datos = json.loads(_get(url, 10))
    except Exception:
        return []
    out = []
    for x in datos.get("quotes", []):
        if x.get("quoteType") not in TIPOS or not valido(x.get("symbol")):
            continue
        out.append({"simbolo": x["symbol"], "nombre": x.get("longname") or x.get("shortname") or x["symbol"],
                    "bolsa": x.get("exchDisp") or x.get("exchange") or "", "tipo": TIPOS[x["quoteType"]],
                    "sector": x.get("sectorDisp") or x.get("sector") or "",
                    "industria": x.get("industryDisp") or x.get("industry") or ""})
    return out


def _descargar(simbolo):
    url = f"{YAHOO}/v8/finance/chart/{urllib.parse.quote(simbolo)}?range=2y&interval=1d&includePrePost=false"
    datos = json.loads(_get(url, 15))["chart"]
    if datos.get("error") or not datos.get("result"):
        raise ValueError((datos.get("error") or {}).get("description") or "símbolo desconocido")
    r = datos["result"][0]
    m, q = r["meta"], r["indicators"]["quote"][0]
    abierto = q.get("open") or []
    serie = [[ts, round(c, 4), h, l, v, round(o, 4) if o is not None else None] for ts, c, h, l, v, o in
             zip(r.get("timestamp") or [], q.get("close") or [], q.get("high") or [], q.get("low") or [],
                 q.get("volume") or [], abierto + [None] * (len(q.get("close") or []) - len(abierto)))
             if c is not None]   # [ts, cierre, máximo, mínimo, volumen, apertura]; la apertura sirve a las velas
    precio = m.get("regularMarketPrice") or (serie[-1][1] if serie else None)
    previo = None
    if len(serie) >= 2 and (m.get("regularMarketTime") or 0) - serie[-1][0] < 86400:
        previo = serie[-2][1]          # la última vela es la sesión de hoy: el cierre anterior es la penúltima
    elif serie:
        previo = serie[-1][1]
    cambio = m.get("regularMarketChangePercent")
    if cambio is None and precio and previo:
        cambio = (precio / previo - 1) * 100
    meta = {"precio": precio, "previo": previo, "cambio": cambio,
            "hora": m.get("regularMarketTime"), "max52": m.get("fiftyTwoWeekHigh"), "min52": m.get("fiftyTwoWeekLow"),
            "max_dia": m.get("regularMarketDayHigh"), "min_dia": m.get("regularMarketDayLow"),
            "volumen": m.get("regularMarketVolume"), "zona": m.get("exchangeTimezoneName")}
    return {"nombre": m.get("longName") or m.get("shortName") or simbolo, "moneda": m.get("currency") or "",
            "bolsa": m.get("fullExchangeName") or m.get("exchangeName") or "",
            "tipo": TIPOS.get(m.get("instrumentType"), m.get("instrumentType") or ""), "meta": meta, "serie": serie}


def info(simbolo):
    r = fila("SELECT * FROM accion_info WHERE simbolo=?", (simbolo,))
    if not r:
        return None
    for k in ("meta", "serie", "relaciones"):
        r[k] = json.loads(r[k]) if r.get(k) else None
    return r


def cotizar(simbolos, max_edad=COTIZACION_VIGENTE):
    """Actualiza (en paralelo) los símbolos cuyos precios tienen más de `max_edad` s. Devuelve {símbolo: error}."""
    viejos = []
    for s in dict.fromkeys(simbolos):
        r = fila("SELECT actualizado FROM accion_info WHERE simbolo=?", (s,))
        if not r or not r["actualizado"] or time.time() - r["actualizado"] > max_edad:
            viejos.append(s)
    errores = {}
    if not viejos:
        return errores

    def uno(s):
        try:
            return s, _descargar(s)
        except Exception as e:
            return s, e
    with ThreadPoolExecutor(6) as ex:
        for s, d in ex.map(uno, viejos):
            if isinstance(d, Exception):
                errores[s] = f"{type(d).__name__}: {d}"
                continue
            ejecutar("""INSERT INTO accion_info(simbolo,nombre,moneda,bolsa,tipo,meta,serie,actualizado)
                        VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(simbolo) DO UPDATE SET nombre=excluded.nombre,
                        moneda=excluded.moneda, bolsa=excluded.bolsa, tipo=excluded.tipo, meta=excluded.meta,
                        serie=excluded.serie, actualizado=excluded.actualizado""",
                     (s, d["nombre"], d["moneda"], d["bolsa"], d["tipo"], json.dumps(d["meta"]),
                      json.dumps(d["serie"]), time.time()))
    return errores


def completar_sector(simbolo):
    """Sector e industria (solo vienen en la búsqueda): se piden una vez."""
    r = fila("SELECT sector FROM accion_info WHERE simbolo=?", (simbolo,))
    if r and r["sector"]:
        return
    x = next((x for x in buscar(simbolo) if x["simbolo"].upper() == simbolo.upper()), None)
    if x:
        ejecutar("UPDATE accion_info SET sector=?, industria=? WHERE simbolo=?",
                 (x["sector"] or "-", x["industria"], simbolo))


# ------------------------------------------------------------ indicadores
def _sma(c, n):
    return sum(c[-n:]) / n if len(c) >= n else None


def _rsi(c, n=14):
    if len(c) <= n:
        return None
    sube = baja = 0.0
    for i in range(1, n + 1):
        d = c[i] - c[i - 1]
        sube, baja = sube + max(d, 0), baja + max(-d, 0)
    sube, baja = sube / n, baja / n
    for i in range(n + 1, len(c)):       # suavizado de Wilder
        d = c[i] - c[i - 1]
        sube = (sube * (n - 1) + max(d, 0)) / n
        baja = (baja * (n - 1) + max(-d, 0)) / n
    return 100.0 if baja == 0 else 100 - 100 / (1 + sube / baja)


def _cuantil(xs, q):
    xs = sorted(xs)
    if not xs:
        return None
    k = (len(xs) - 1) * q
    a, b = math.floor(k), math.ceil(k)
    return xs[a] + (xs[b] - xs[a]) * (k - a)


def tasa_base(serie, dias):
    """Con qué frecuencia subió la acción en ventanas de `dias` naturales (≈ días de bolsa) en los 2 años
    guardados, y entre qué rendimientos terminó el 80 % de esas ventanas. Es la referencia honesta: un pronóstico
    que no la supera no aporta nada."""
    c = [x[1] for x in serie]
    h = max(1, round(dias * 252 / 365))
    rend = [c[i + h] / c[i] - 1 for i in range(len(c) - h)]
    if len(rend) < 20:
        return None
    return {"dias": dias, "ventanas": len(rend), "p_sube": round(100 * sum(r > 0 for r in rend) / len(rend), 1),
            "p10": _cuantil(rend, .1) * 100, "p50": _cuantil(rend, .5) * 100, "p90": _cuantil(rend, .9) * 100}


def indicadores(i):
    """Todo lo que se calcula del precio, sin IA. `i` = info(simbolo)."""
    serie = (i or {}).get("serie") or []
    c = [x[1] for x in serie]
    if len(c) < 5:
        return None
    precio = (i.get("meta") or {}).get("precio") or c[-1]

    def rend(n):
        return (precio / c[-1 - n] - 1) * 100 if len(c) > n else None
    logr = [math.log(c[k] / c[k - 1]) for k in range(1, len(c)) if c[k - 1] > 0 and c[k] > 0]
    ult = logr[-252:]
    vol = statistics.pstdev(ult) * math.sqrt(252) if len(ult) > 10 else None
    anio = c[-252:]
    m = i.get("meta") or {}
    max52, min52 = m.get("max52") or max(anio), m.get("min52") or min(anio)   # Yahoo: con máximos intradía
    pico, caida = anio[0], 0.0
    for x in anio:
        pico = max(pico, x)
        caida = min(caida, x / pico - 1)
    inicio_anio = datetime(datetime.now().year, 1, 1).timestamp()
    previo_anio = next((x[1] for x in reversed(serie) if x[0] < inicio_anio), None)
    sma20, sma50, sma200 = _sma(c, 20), _sma(c, 50), _sma(c, 200)
    rsi = _rsi(c[-120:])
    tendencia = ("alcista" if sma50 and sma200 and precio > sma50 > sma200 else
                 "bajista" if sma50 and sma200 and precio < sma50 < sma200 else "mixta")
    rangos = {}
    for d in HORIZONTES:   # rango estadístico (lognormal, sin tendencia): dónde termina el precio 8 de cada 10 veces
        if vol:
            s = vol * math.sqrt(d / 365)
            rangos[d] = {"bajo": precio * math.exp(-1.2816 * s), "alto": precio * math.exp(1.2816 * s),
                         "base": tasa_base(serie, d), "casos": casos(serie, d, precio, vol)}
    return {"precio": precio, "rend": {"5d": rend(5), "1m": rend(21), "3m": rend(63), "6m": rend(126), "1a": rend(252),
                                       "ytd": (precio / previo_anio - 1) * 100 if previo_anio else None},
            "volatilidad": vol * 100 if vol else None, "sma20": sma20, "sma50": sma50, "sma200": sma200, "rsi": rsi,
            "max52": max52, "min52": min52, "desde_max": (precio / max52 - 1) * 100,
            "desde_min": (precio / min52 - 1) * 100, "caida_max": caida * 100, "tendencia": tendencia,
            "rangos": rangos}


# ------------------------------------------------------------------ casos: del peor al mejor
# Cinco zonas EXCLUYENTES donde puede terminar el precio (suman 100 %), en múltiplos de la desviación típica del
# horizonte s = volatilidad · √(días/365). A diferencia de los escenarios de la IA (eventos que pueden pasar a la
# vez, cada uno con su probabilidad), aquí las zonas compiten entre sí: la de mayor % es «lo más probable».
Z_BANDAS = 1.2816     # el 80 % central, igual que el cono del gráfico
BANDAS = (("peor", "Peor caso", None, -Z_BANDAS), ("pesimista", "Pesimista", -Z_BANDAS, -0.5),
          ("central", "Central", -0.5, 0.5), ("optimista", "Optimista", 0.5, Z_BANDAS),
          ("mejor", "Mejor caso", Z_BANDAS, None))


def _phi(z):
    return 0.5 * (1 + math.erf(z / math.sqrt(2)))


def _repartir(pesos, total=100):
    """Enteros que suman exactamente `total` (mayor residuo)."""
    s = sum(pesos) or 1
    brutos = [p / s * total for p in pesos]
    out = [int(b) for b in brutos]
    for k in sorted(range(len(out)), key=lambda k: brutos[k] - out[k], reverse=True)[:total - sum(out)]:
        out[k] += 1
    return out


def casos(serie, dias, precio, vol, p_sube=None):
    """Probabilidad de cada zona final del precio. `vol` = volatilidad anual (0,25 = 25 %). Mezcla 85 % lo que pasó en
    las ventanas de los últimos 2 años con 15 % de curva normal (para que ninguna zona quede en cero) y, si hay
    `p_sube` (la probabilidad final de subir, ya anclada), reparte la masa de arriba y de abajo de hoy para que
    coincida con ella."""
    c = [x[1] for x in serie or []]
    if not vol or not precio or len(c) < 40:
        return None
    s = vol * math.sqrt(dias / 365)
    h = max(1, round(dias * 252 / 365))
    zs = [math.log(c[i + h] / c[i]) / s for i in range(len(c) - h) if c[i] > 0 and c[i + h] > 0]
    cortes = (-Z_BANDAS, -0.5, 0.0, 0.5, Z_BANDAS)

    def celda(z):
        return sum(z > t for t in cortes)          # 0 peor · 1 pesimista · 2 central abajo · 3 central arriba · 4 optimista · 5 mejor
    emp = [0.0] * 6
    for z in zs:
        emp[celda(z)] += 1 / len(zs) if zs else 0
    nor = [_phi(-Z_BANDAS), _phi(-0.5) - _phi(-Z_BANDAS), _phi(0) - _phi(-0.5), _phi(0.5) - _phi(0),
           _phi(Z_BANDAS) - _phi(0.5), 1 - _phi(Z_BANDAS)]
    mezcla = [0.85 * e + 0.15 * n for e, n in zip(emp, nor)] if zs else nor
    hist = list(mezcla)
    if p_sube is not None:
        arriba = sum(mezcla[3:])
        objetivo = max(0.02, min(0.98, p_sube / 100))
        mezcla = [m * (objetivo / arriba if k >= 3 else (1 - objetivo) / (1 - arriba)) for k, m in enumerate(mezcla)]
    juntas = [mezcla[0], mezcla[1], mezcla[2] + mezcla[3], mezcla[4], mezcla[5]]
    hist5 = [hist[0], hist[1], hist[2] + hist[3], hist[4], hist[5]]
    pct, pct_h = _repartir(juntas), _repartir(hist5)
    out = []
    for (clave, nombre, z0, z1), p, ph in zip(BANDAS, pct, pct_h):
        out.append({"clave": clave, "nombre": nombre, "prob": p, "prob_estadistica": ph,
                    "desde": None if z0 is None else precio * math.exp(z0 * s),
                    "hasta": None if z1 is None else precio * math.exp(z1 * s),
                    "desde_pct": None if z0 is None else (math.exp(z0 * s) - 1) * 100,
                    "hasta_pct": None if z1 is None else (math.exp(z1 * s) - 1) * 100})
    mejor = max(range(5), key=lambda k: out[k]["prob"])
    peor = min(range(5), key=lambda k: out[k]["prob"])
    out[mejor]["marca"] = "más probable"
    out[peor]["marca"] = "menos probable"
    return {"dias": dias, "zonas": out, "ventanas": len(zs), "ajustado_a_ia": p_sube is not None}


# ------------------------------------------------------------------ velas japonesas y martillos
EXPLICACION_PATRON = {
    "martillo": ("alcista", "Cuerpo pequeño arriba y una sombra inferior larga, tras una caída: los vendedores empujaron el precio "
                 "muy abajo, pero los compradores lo devolvieron arriba. Posible fin de la caída; se confirma si la vela "
                 "siguiente cierra por encima de la del martillo."),
    "hombre colgado": ("bajista", "Misma forma del martillo pero tras una subida: aunque se recuperó, hubo vendedores fuertes. "
                       "Posible techo; solo cuenta si la vela siguiente cierra por debajo."),
    "martillo invertido": ("alcista", "Sombra superior larga y cuerpo pequeño abajo, tras una caída: los compradores probaron "
                           "subir. Es la señal más débil de las alcistas: exige confirmación al día siguiente."),
    "estrella fugaz": ("bajista", "Sombra superior larga y cuerpo pequeño abajo, tras una subida: el precio subió y fue rechazado. "
                       "Posible techo; se confirma con una vela siguiente que cierre por debajo."),
    "doji": ("neutral", "Apertura y cierre casi iguales: indecisión entre compradores y vendedores. Pesa según dónde ocurra."),
    "doji libélula": ("alcista", "Doji con una sombra inferior larga: los vendedores perdieron la pelea del día. Pesa más tras una caída."),
    "doji lápida": ("bajista", "Doji con una sombra superior larga: los compradores perdieron la pelea del día. Pesa más tras una subida."),
    "envolvente alcista": ("alcista", "Una vela verde cuyo cuerpo cubre por completo el cuerpo rojo anterior, tras una caída: "
                           "los compradores tomaron el control."),
    "envolvente bajista": ("bajista", "Una vela roja cuyo cuerpo cubre por completo el cuerpo verde anterior, tras una subida: "
                           "los vendedores tomaron el control."),
}
VENTANA_PATRON = 5      # velas hacia delante para medir qué pasó después de cada patrón en el pasado


def _ohlc(serie):
    """[(ts, apertura, máximo, mínimo, cierre)] con la apertura = cierre anterior cuando el dato viejo no la trae."""
    out = []
    for k, x in enumerate(serie):
        o = x[5] if len(x) > 5 and x[5] is not None else (serie[k - 1][1] if k else x[1])
        if x[2] is None or x[3] is None:
            continue
        out.append((x[0], o, max(x[2], o, x[1]), min(x[3], o, x[1]), x[1]))
    return out


def _detectar(v, k):
    """Nombres de patrones en la vela k de `v` (lista de _ohlc). Necesita 6 velas atrás para saber la tendencia previa."""
    if k < 6:
        return []
    _, o, h, l, c = v[k]
    rango = h - l
    if rango <= 0 or rango / max(c, 1e-9) < 0.002:
        return []
    cuerpo, inf, sup = abs(c - o), min(o, c) - l, h - max(o, c)
    previa = v[k - 1][4] / v[k - 6][4] - 1
    tend = "bajista" if previa <= -0.02 else "alcista" if previa >= 0.02 else "lateral"
    out = []
    if cuerpo <= 0.1 * rango:
        out.append("doji libélula" if inf >= 0.6 * rango and sup <= 0.1 * rango else
                   "doji lápida" if sup >= 0.6 * rango and inf <= 0.1 * rango else "doji")
    elif cuerpo <= 0.35 * rango and tend != "lateral":
        if inf >= 2 * cuerpo and sup <= 0.15 * rango:
            out.append("martillo" if tend == "bajista" else "hombre colgado")
        elif sup >= 2 * cuerpo and inf <= 0.15 * rango:
            out.append("martillo invertido" if tend == "bajista" else "estrella fugaz")
    po, pc = v[k - 1][1], v[k - 1][4]
    if tend == "bajista" and pc < po and c > o and o <= pc and c >= po:
        out.append("envolvente alcista")
    if tend == "alcista" and pc > po and c < o and o >= pc and c <= po:
        out.append("envolvente bajista")
    return out


def patrones_velas(serie, ultimas=30):
    """Patrones de velas de las últimas `ultimas` sesiones y, para cada tipo, qué pasó en este mismo activo las veces
    anteriores (a 5 sesiones): así se ve si la señal sirvió aquí o fue ruido."""
    v = _ohlc(serie or [])
    if len(v) < 20:
        return {"recientes": [], "historia": {}}
    historia, recientes = {}, []
    for k in range(6, len(v)):
        for nombre in _detectar(v, k):
            if k >= len(v) - ultimas:
                recientes.append({"ts": v[k][0], "patron": nombre, "sesgo": EXPLICACION_PATRON[nombre][0],
                                  "explicacion": EXPLICACION_PATRON[nombre][1]})
            if k + VENTANA_PATRON < len(v):
                d = historia.setdefault(nombre, {"n": 0, "subio": 0, "suma": 0.0})
                r = v[k + VENTANA_PATRON][4] / v[k][4] - 1
                d["n"] += 1
                d["subio"] += r > 0
                d["suma"] += r * 100
    hist = {n: {"n": d["n"], "sube_pct": round(100 * d["subio"] / d["n"]), "media": round(d["suma"] / d["n"], 2)}
            for n, d in historia.items()}
    for r in recientes:
        r["historia"] = hist.get(r["patron"])
    recientes.sort(key=lambda r: -r["ts"])
    return {"recientes": recientes, "historia": hist}


def velas(serie, ultimas=260):
    """Velas para el gráfico: [ts, apertura, máximo, mínimo, cierre]."""
    return [list(x) for x in _ohlc(serie or [])[-ultimas:]]


def referencia(i):
    """Índice contra el que se mide: el S&P 500, o el ETF del COLCAP para lo que cotiza en pesos colombianos."""
    return "ICOLCAP.CL" if (i or {}).get("moneda") == "COP" else "^GSPC"


def _por_dia(serie):
    return {datetime.fromtimestamp(x[0], timezone.utc).strftime("%Y-%m-%d"): x[1] for x in serie}


def frente_al_mercado(i):
    """Beta y correlación (último año de días comunes) y cuánto del movimiento de hoy es propio y no del mercado."""
    ref = referencia(i)
    if not i or i["simbolo"] == ref:
        return None
    cotizar([ref])
    r = info(ref)
    if not r or not r.get("serie") or not i.get("serie"):
        return None
    a, b = _por_dia(i["serie"]), _por_dia(r["serie"])
    dias = sorted(set(a) & set(b))[-253:]
    ra = [a[dias[k]] / a[dias[k - 1]] - 1 for k in range(1, len(dias))]
    rb = [b[dias[k]] / b[dias[k - 1]] - 1 for k in range(1, len(dias))]
    if len(ra) < 30:
        return None
    ma, mb = statistics.fmean(ra), statistics.fmean(rb)
    cov = sum((x - ma) * (y - mb) for x, y in zip(ra, rb)) / len(ra)
    var_b = statistics.pvariance(rb)
    sa, sb = statistics.pstdev(ra), statistics.pstdev(rb)
    beta = cov / var_b if var_b else None
    c_hoy, c_ref = (i.get("meta") or {}).get("cambio"), (r.get("meta") or {}).get("cambio")
    return {"referencia": ref, "nombre": r["nombre"], "beta": beta, "correlacion": cov / (sa * sb) if sa and sb else None,
            "dias": len(ra), "cambio_ref": c_ref,
            "propio": c_hoy - beta * c_ref if None not in (c_hoy, c_ref, beta) else None}


def explicar_indicadores(ind):
    """Lectura en palabras de los indicadores (para la persona y como contexto de la IA)."""
    if not ind:
        return []
    out = []
    if ind["volatilidad"] is not None:
        v = ind["volatilidad"]
        out.append(f"Volatilidad anual {v:.0f} %: " + ("muy alta (movimientos fuertes son normales)" if v > 50 else
                                                       "alta" if v > 30 else "moderada" if v > 18 else "baja"))
    if ind["rsi"] is not None:
        r = ind["rsi"]
        out.append(f"RSI {r:.0f}: " + ("sobrecompra (subió muy rápido; a menudo hace una pausa)" if r >= 70 else
                                       "sobreventa (cayó muy rápido; a veces rebota)" if r <= 30 else "zona neutral"))
    t = {"alcista": "precio sobre la media de 50 días y esta sobre la de 200: tendencia alcista",
         "bajista": "precio bajo la media de 50 días y esta bajo la de 200: tendencia bajista",
         "mixta": "las medias no marcan una tendencia clara"}[ind["tendencia"]]
    out.append(t[0].upper() + t[1:])
    out.append(f"A {abs(ind['desde_max']):.1f} % de su máximo de 52 semanas y {ind['desde_min']:+.1f} % sobre su mínimo")
    return [re.sub(r"(\d)\.(\d)", r"\1,\2", x) for x in out]   # decimales con coma, como en la interfaz


# ------------------------------------------------------------------ noticias
def _gn(consulta, idioma="es"):
    """Google Noticias (RSS de búsqueda, uso personal), últimos DIAS_NOTICIAS días."""
    loc = {"es": ("es-419", "CO", "CO:es-419"), "en": ("en-US", "US", "US:en")}[idioma]
    url = "https://news.google.com/rss/search?" + urllib.parse.urlencode(
        {"q": f"{consulta} when:{DIAS_NOTICIAS}d", "hl": loc[0], "gl": loc[1], "ceid": loc[2]})
    with _red:
        time.sleep(1.0)
        items = nt._items(_get(url))
    out = []
    for it in items[:10]:
        titulo, fuente = it["titulo"], ""
        if " - " in titulo:
            titulo, fuente = titulo.rsplit(" - ", 1)
        out.append(dict(it, titulo=titulo, fuente=fuente or "Google Noticias",
                        resumen="" if it["resumen"].startswith(titulo[:40]) else it["resumen"]))
    return out


def _yahoo_rss(simbolo):
    url = "https://feeds.finance.yahoo.com/rss/2.0/headline?" + urllib.parse.urlencode(
        {"s": simbolo, "region": "US", "lang": "en-US"})
    return [dict(it, fuente="Yahoo Finance") for it in nt._items(_get(url))[:15]]


def nombre_corto(nombre):
    n = re.sub(r"[,.]?\s+(Inc|Incorporated|Corp|Corporation|Co|Company|Ltd|Limited|plc|PLC|S\.?A\.?(\s*E\.?S\.?P\.?)?|"
               r"N\.?V\.?|AG|SE|Holdings?|Group|Class [A-C]|ADR)\.?$", "", nombre or "", flags=re.I).strip()
    n = re.sub(r"[,.]?\s+(Inc|Corp|Corporation|Holdings?|Group)\.?$", "", n, flags=re.I).strip()
    return n or nombre


def _guardar(simbolo, it, relacion, via):
    if not it.get("url") or not nt.url_publica(it["url"]):
        return 0
    pub = it.get("fecha") or time.time()
    if pub < time.time() - (DIAS_NOTICIAS + 1) * 86400 or pub > time.time() + 86400:
        return 0
    if relacion == "indirecta" and fila("SELECT 1 FROM accion_noticia WHERE simbolo=? AND url=?", (simbolo, it["url"])):
        return 0   # ya está (quizá como directa, que manda)
    c = ejecutar("""INSERT INTO accion_noticia(simbolo,url,titulo,resumen,fuente,publicada,relacion,via)
                    VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(simbolo,url) DO UPDATE SET
                    relacion=CASE WHEN excluded.relacion='directa' THEN 'directa' ELSE accion_noticia.relacion END""",
                 (simbolo, it["url"], it["titulo"][:300], (it.get("resumen") or "")[:600], it.get("fuente") or "",
                  pub, relacion, via[:120]))
    return c.rowcount


def _palabras_relacion(rel):
    """Palabras que, si aparecen en una noticia, la ligan indirectamente a la acción."""
    ps = {}
    for k, etq in PAPELES.items():
        for x in rel.get(k, []):
            n = nombre_corto(x.get("nombre", ""))
            if len(n) >= 4:
                ps[n.lower()] = f"{etq}: {n}"
    for f in rel.get("factores", []):
        for p in f.get("palabras", []):
            if len(p) >= 4:
                ps[p.lower()] = f"factor: {f.get('nombre', p)}"
    return ps


def actualizar_noticias(simbolo, forzar=False):
    """Busca noticias directas e indirectas (sin IA). Devuelve {nuevas, errores} o {omitido} si son recientes."""
    i = info(simbolo)
    if not i:
        return {"nuevas": 0, "errores": ["sin datos del símbolo"]}
    edad = time.time() - (i.get("noticias_fecha") or 0)
    if edad < (600 if forzar else NOTICIAS_VIGENTES):
        return {"nuevas": 0, "omitido": True}
    ejecutar("UPDATE accion_info SET noticias_fecha=? WHERE simbolo=?", (time.time(), simbolo))
    nombre = nombre_corto(i["nombre"])
    menciona = re.compile(r"(?<![\w])(" + re.escape(nombre.lower()) + "|" + re.escape(simbolo.lower().split(".")[0])
                          + r")(?![\w])")

    def yahoo():   # el RSS por símbolo trae también notas generales del mercado: solo es directa si la nombra
        return [dict(it, _rel="directa" if menciona.search(f"{it['titulo']} {it['resumen']}".lower()) else "indirecta")
                for it in _yahoo_rss(simbolo)]
    tareas = [("directa", f"Yahoo Finance ({simbolo})", yahoo),
              ("directa", f"«{nombre}»", lambda: _gn(f'"{nombre}"', "es")),
              ("directa", f"«{nombre}» (inglés)", lambda: _gn(f'"{nombre}" stock', "en"))]
    rel = i.get("relaciones") or {}
    for k, etq in PAPELES.items():
        for x in rel.get(k, [])[:1 if k != "competidores" else 2]:
            n = nombre_corto(x.get("nombre", ""))
            if n:
                tareas.append(("indirecta", f"{etq}: {n}", lambda n=n: _gn(f'"{n}"', "en")))
    for f in rel.get("factores", [])[:3]:
        if f.get("consulta"):
            tareas.append(("indirecta", f"factor: {f.get('nombre') or f['consulta']}",
                           lambda f=f: _gn(f["consulta"], "en")))
    nuevas, errores = 0, []
    for relacion, via, fn in tareas:
        try:
            for it in fn():
                r = it.get("_rel", relacion)
                nuevas += _guardar(simbolo, it, r, via if r == relacion else "mercado en general (Yahoo Finance)")
        except Exception as e:
            errores.append(f"{via}: {type(e).__name__}")
    # Indirectas también desde las noticias que la Academia ya descargó (medios verificados de tus áreas)
    ps = _palabras_relacion(rel)
    if ps:
        patron = re.compile(r"(?<![\w])(" + "|".join(re.escape(p) for p in sorted(ps, key=len, reverse=True)) + r")(?![\w])")
        for n in filas("""SELECT url, titulo, resumen, fuente, publicada FROM noticia WHERE tipo='noticia'
                          AND publicada>?""", (time.time() - 7 * 86400,)):
            m = patron.search(f"{n['titulo']} {n['resumen'] or ''}".lower())
            if m:
                nuevas += _guardar(simbolo, {"url": n["url"], "titulo": n["titulo"], "resumen": n["resumen"],
                                             "fuente": n["fuente"], "fecha": n["publicada"]}, "indirecta", ps[m.group(1)])
    ejecutar("DELETE FROM accion_noticia WHERE publicada<?", (time.time() - 45 * 86400,))
    return {"nuevas": nuevas, "errores": errores}


def noticias(simbolo, dias=DIAS_NOTICIAS, limite=200):
    out = filas("""SELECT id, url, titulo, resumen, fuente, publicada, relacion, via, analisis FROM accion_noticia
                   WHERE simbolo=? AND publicada>? ORDER BY publicada DESC LIMIT ?""",
                (simbolo, time.time() - dias * 86400, limite))
    for n in out:
        n["analisis"] = json.loads(n["analisis"]) if n["analisis"] else None
        if n["analisis"]:   # la IA puede corregir la relación (p. ej. una «directa» que solo menciona a la empresa)
            n["relacion"] = n["analisis"].get("relacion") or n["relacion"]
    return out


# --------------------------------------------------------------------- IA
ESQUEMA_RELACIONES = {"type": "object", "properties": {
    "negocio": {"type": "string"},
    "competidores": {"type": "array", "maxItems": 5, "items": {"type": "object", "properties": {
        "nombre": {"type": "string"}, "simbolo": {"type": "string"}}, "required": ["nombre", "simbolo"]}},
    "proveedores": {"type": "array", "maxItems": 4, "items": {"type": "object", "properties": {
        "nombre": {"type": "string"}, "simbolo": {"type": "string"}, "que": {"type": "string"}},
        "required": ["nombre", "simbolo", "que"]}},
    "clientes": {"type": "array", "maxItems": 4, "items": {"type": "object", "properties": {
        "nombre": {"type": "string"}, "simbolo": {"type": "string"}, "que": {"type": "string"}},
        "required": ["nombre", "simbolo", "que"]}},
    "factores": {"type": "array", "minItems": 3, "maxItems": 6, "items": {"type": "object", "properties": {
        "nombre": {"type": "string"}, "como": {"type": "string"}, "consulta": {"type": "string"},
        "palabras": {"type": "array", "maxItems": 6, "items": {"type": "string"}}},
        "required": ["nombre", "como", "consulta", "palabras"]}}},
    "required": ["negocio", "competidores", "proveedores", "clientes", "factores"]}


def relaciones(ctx, simbolo):
    """Mapa de la empresa: de qué y de quién depende su precio (base de las noticias indirectas)."""
    i = info(simbolo)
    if not i:
        raise ValueError("símbolo sin datos")
    ctx.fase(f"Mapeando de qué depende {simbolo}")
    titulares = "\n".join(f"- {n['titulo']}" for n in noticias(simbolo, limite=12) if n["relacion"] == "directa")
    prompt = (f"Empresa/activo: {i['nombre']} (símbolo {simbolo}, {i.get('tipo') or ''}, bolsa {i.get('bolsa')}, "
              f"sector {i.get('sector') or '?'}, industria {i.get('industria') or '?'}, moneda {i.get('moneda')}).\n"
              f"Titulares recientes:\n{titulares or '(ninguno)'}\n\n"
              "Arma su mapa de relaciones para seguir las noticias que la mueven INDIRECTAMENTE:\n"
              "- negocio: 2 frases sobre cómo gana dinero.\n"
              "- competidores, proveedores clave y clientes clave reales (con su símbolo bursátil si cotizan, si no \"\").\n"
              "- factores: lo macro o sectorial que más mueve el precio (tasas de interés, dólar, petróleo, regulación, "
              "precio de un insumo, demanda de un producto…). Para cada uno: «como» (si sube X, ¿qué le pasa a la "
              "acción y por qué?), «consulta» (búsqueda corta en INGLÉS para Google Noticias) y «palabras» (2-6 "
              "palabras clave en español e inglés que aparecerían en una noticia sobre ese factor).\n"
              "Usa solo lo que sabes con seguridad; si es un índice o ETF, sus componentes principales y factores.")
    r = ctx.chat([{"role": "system", "content": "Eres analista financiero. Respondes en español, preciso y sin inventar."},
                  {"role": "user", "content": prompt}], max_tokens=2000, temperatura=0.2, esquema=ESQUEMA_RELACIONES)
    for k in ("competidores", "proveedores", "clientes"):
        for x in r.get(k, []):
            x["simbolo"] = x["simbolo"].strip().upper() if valido(x.get("simbolo", "").strip()) else ""
    ejecutar("UPDATE accion_info SET relaciones=?, relaciones_fecha=?, noticias_fecha=0 WHERE simbolo=?",
             (json.dumps(r, ensure_ascii=False), time.time(), simbolo))
    return r


ESQUEMA_CLASIFICAR = {"type": "object", "properties": {"noticias": {"type": "array", "items": {
    "type": "object", "properties": {
        "i": {"type": "integer"}, "relevante": {"type": "boolean"},
        "relacion": {"type": "string", "enum": ["directa", "indirecta"]},
        "via": {"type": "string"}, "impacto": {"type": "integer", "minimum": -2, "maximum": 2},
        "plazo": {"type": "string", "enum": ["días", "semanas", "meses"]}, "resumen": {"type": "string"}},
    "required": ["i", "relevante", "relacion", "via", "impacto", "plazo", "resumen"]}}}, "required": ["noticias"]}


def clasificar(ctx, simbolo, i, tandas=2):
    """La IA lee cada noticia nueva una vez (se guarda: sirve para todas las personas que siguen el símbolo), en
    tandas de 30 (las directas y las más recientes primero)."""
    return sum(_clasificar_tanda(ctx, simbolo, i) for _ in range(tandas))


def _clasificar_tanda(ctx, simbolo, i):
    pend = filas("""SELECT id, titulo, resumen, fuente, relacion, via FROM accion_noticia WHERE simbolo=?
                    AND analisis IS NULL AND publicada>? ORDER BY relacion='directa' DESC, publicada DESC LIMIT 30""",
                 (simbolo, time.time() - DIAS_NOTICIAS * 86400))
    if not pend:
        return 0
    ctx.fase(f"Leyendo {len(pend)} noticias de {simbolo}")
    rel = i.get("relaciones") or {}
    lista = "\n".join(f"[{k}] ({n['relacion']}, vía {n['via']}) {n['titulo']} — {n['fuente']}"
                      + (f": {n['resumen'][:220]}" if n["resumen"] else "") for k, n in enumerate(pend))
    prompt = (f"Acción: {i['nombre']} ({simbolo}). Negocio: {rel.get('negocio', '?')}\n"
              f"Factores de los que depende: {'; '.join(f['nombre'] + ' → ' + f['como'] for f in rel.get('factores', []))}\n\n"
              f"NOTICIAS:\n{lista}\n\nPara CADA noticia [i]: relevante (¿puede mover el precio de esta acción?), "
              "relacion (directa si trata de la empresa misma; indirecta si la afecta por un competidor, proveedor, "
              "cliente, el sector o la economía), via (una frase: por qué camino la afecta), impacto (-2 muy negativo "
              "… +2 muy positivo para el precio; 0 si neutro o dudoso), plazo del efecto y un resumen en español de "
              "una línea. No exageres: la mayoría de noticias tienen impacto 0 o ±1.")
    r = ctx.chat([{"role": "system", "content": "Eres analista financiero riguroso. Respondes en español."},
                  {"role": "user", "content": prompt}], max_tokens=4000, temperatura=0.2, esquema=ESQUEMA_CLASIFICAR)
    hechas = 0
    for x in r.get("noticias", []):
        if 0 <= x.get("i", -1) < len(pend):
            ejecutar("UPDATE accion_noticia SET analisis=? WHERE id=?",
                     (json.dumps({k: x[k] for k in ("relevante", "relacion", "via", "impacto", "plazo", "resumen")},
                                 ensure_ascii=False), pend[x["i"]]["id"]))
            hechas += 1
    return hechas


ESQUEMA_PRONOSTICO = {"type": "object", "properties": {
    "resumen": {"type": "string"},
    "sesgo": {"type": "string", "enum": ["alcista", "bajista", "neutral"]},
    "p_sube": {"type": "integer", "minimum": 1, "maximum": 99},
    "escenarios": {"type": "array", "minItems": 4, "maxItems": 6, "items": {"type": "object", "properties": {
        "titulo": {"type": "string"}, "que_pasaria": {"type": "string"},
        "direccion": {"type": "string", "enum": ["sube", "baja", "lateral"]},
        "caso": {"type": "string", "enum": [b[0] for b in BANDAS]},
        "probabilidad": {"type": "integer", "minimum": 1, "maximum": 99},
        "por_que": {"type": "string"}, "noticias": {"type": "array", "maxItems": 5, "items": {"type": "integer"}},
        "confirma": {"type": "string"}, "descarta": {"type": "string"}},
        "required": ["titulo", "que_pasaria", "direccion", "caso", "probabilidad", "por_que", "noticias", "confirma",
                     "descarta"]}},
    "catalizadores": {"type": "array", "maxItems": 5, "items": {"type": "object", "properties": {
        "evento": {"type": "string"}, "cuando": {"type": "string"}, "efecto": {"type": "string"}},
        "required": ["evento", "cuando", "efecto"]}},
    "a_favor": {"type": "array", "maxItems": 5, "items": {"type": "string"}},
    "en_contra": {"type": "array", "maxItems": 5, "items": {"type": "string"}},
    "vigilar": {"type": "array", "maxItems": 5, "items": {"type": "string"}},
    "aprender": {"type": "array", "maxItems": 4, "items": {"type": "string"}}},
    "required": ["resumen", "sesgo", "p_sube", "escenarios", "catalizadores", "a_favor", "en_contra", "vigilar",
                 "aprender"]}


def _fmt(x, d=1):
    return "?" if x is None else f"{x:+.{d}f} %"


def pronosticar(ctx, usuario, simbolo, dias=30, p_usuario=None):
    dias = dias if dias in HORIZONTES else 30
    ctx.fase(f"Precios de {simbolo}")
    cotizar([simbolo], 120)
    completar_sector(simbolo)
    i = info(simbolo)
    if not i or not i.get("serie"):
        raise ValueError("no hay precios para este símbolo")
    if not i.get("relaciones") or time.time() - (i.get("relaciones_fecha") or 0) > RELACIONES_VIGENTES:
        relaciones(ctx, simbolo)
        i = info(simbolo)
    ctx.fase(f"Buscando noticias de {simbolo} y de lo que la afecta")
    actualizar_noticias(simbolo)
    clasificar(ctx, simbolo, i)
    ind = indicadores(i)
    rango = ind["rangos"].get(dias) or {}
    base = rango.get("base") or {"p_sube": 50.0, "p10": None, "p90": None, "ventanas": 0}
    ns = [n for n in noticias(simbolo) if (n["analisis"] or {}).get("relevante", True)]
    ns.sort(key=lambda n: (-abs((n["analisis"] or {}).get("impacto") or 0), -n["publicada"]))
    ns = ns[:24]
    lista = "\n".join(
        f"[{k}] {datetime.fromtimestamp(n['publicada']):%d/%m} ({n['relacion']}; {(n['analisis'] or {}).get('via') or n['via']}; "
        f"impacto {(n['analisis'] or {}).get('impacto', '?')}) {(n['analisis'] or {}).get('resumen') or n['titulo']}"
        for k, n in enumerate(ns))
    previo = fila("""SELECT creado, dias, precio, p_sube, resultado FROM accion_pronostico WHERE usuario=? AND simbolo=?
                     ORDER BY creado DESC LIMIT 1""", (usuario, simbolo))
    rel = i.get("relaciones") or {}
    m = i.get("meta") or {}
    prompt = (
        f"ACCIÓN: {i['nombre']} ({simbolo}), {i.get('bolsa')}, moneda {i.get('moneda')}. Sector {i.get('sector') or '?'}.\n"
        f"Negocio: {rel.get('negocio', '?')}\n"
        f"Factores: {'; '.join(f['nombre'] + ' → ' + f['como'] for f in rel.get('factores', []))}\n\n"
        f"PRECIO: {ind['precio']:.2f} (hoy {_fmt(m.get('cambio'), 2)}). Rendimiento 5 d {_fmt(ind['rend']['5d'])}, "
        f"1 m {_fmt(ind['rend']['1m'])}, 3 m {_fmt(ind['rend']['3m'])}, 1 año {_fmt(ind['rend']['1a'])}.\n"
        + "\n".join(f"- {x}" for x in explicar_indicadores(ind)) + "\n\n"
        f"ESTADÍSTICA (la referencia que debes respetar): en {base['ventanas']} ventanas de {dias} días de los últimos "
        f"2 años la acción subió el {base['p_sube']:.0f} % de las veces; el 80 % de las veces terminó entre "
        f"{_fmt(base['p10'])} y {_fmt(base['p90'])}. Con su volatilidad actual, el rango del 80 % para dentro de "
        f"{dias} días es {rango.get('bajo', 0):.2f} – {rango.get('alto', 0):.2f}.\n"
        + (f"Pronóstico anterior ({datetime.fromtimestamp(previo['creado']):%d/%m}, {previo['dias']} d): "
           f"P(sube) {previo['p_sube']:.0f} % desde {previo['precio']:.2f}"
           + (f"; resultado: {json.loads(previo['resultado'])}" if previo["resultado"] else "") + "\n" if previo else "")
        + f"\nNOTICIAS (directas e indirectas, ya clasificadas):\n{lista or '(no hay noticias recientes)'}\n\n"
        f"Haz un pronóstico para los próximos {dias} días:\n"
        f"- p_sube: probabilidad (1-99) de que el precio esté MÁS ALTO que hoy dentro de {dias} días. Parte de la tasa "
        f"base ({base['p_sube']:.0f} %) y muévela solo lo que justifiquen las noticias y señales (como máximo "
        f"{margen_ia(usuario, simbolo)[0]} puntos). Los mercados son difíciles de predecir: evita la falsa seguridad.\n"
        "- escenarios: 4-6 eventos concretos y verificables que podrían pasar en ese plazo (movimientos de precio, "
        "reacciones a un evento con fecha, efectos de una noticia indirecta, comportamiento de la volatilidad). NO "
        "son excluyentes ni tienen que sumar 100: cada uno lleva su propia probabilidad (1-99) de ocurrir, honesta y "
        "coherente con la estadística. «caso» = en cuál de las 5 zonas finales del precio desembocaría: peor (caída fuerte, "
        "más allá del rango del 80 %), pesimista (caída moderada), central (queda cerca de hoy), optimista (subida "
        "moderada) o mejor (subida fuerte, más allá del rango); cubre las 5 zonas, al menos un escenario en cada una. "
        "Incluye al menos uno MUY probable (≥ 70, p. ej. que el precio siga dentro del "
        "rango estadístico) y al menos uno poco probable (≤ 25). El título no lleva la etiqueta de probabilidad. "
        "«noticias» = índices [i] que lo sustentan (en los textos no escribas números de noticia entre corchetes); "
        "«confirma»/«descarta» = qué señal observable diría que se está cumpliendo o no.\n"
        "- resumen: 3-5 frases con la conclusión: qué es lo más probable, por qué (noticias directas e indirectas y "
        "estadística) y el principal riesgo.\n"
        "- catalizadores: eventos con fecha (resultados trimestrales, decisiones de tasas, lanzamientos…) si los "
        "conoces; a_favor / en_contra; vigilar (qué mirar en los próximos días); aprender (conceptos de finanzas que "
        "ayudan a entender este caso).\nTodo en español claro.")
    ctx.fase(f"Pronosticando {simbolo} a {dias} días")
    r = ctx.chat([{"role": "system", "content": "Eres analista financiero cuantitativo, prudente y calibrado. "
                                                "Respondes en español."},
                  {"role": "user", "content": prompt}], max_tokens=3500, temperatura=0.3, esquema=ESQUEMA_PRONOSTICO)
    margen, motivo_margen = margen_ia(usuario, simbolo)
    p = max(base["p_sube"] - margen, min(base["p_sube"] + margen, r["p_sube"]))
    p = max(5, min(95, p))
    for e in r["escenarios"]:
        e["probabilidad"] = max(1, min(99, e["probabilidad"]))
        e["etiqueta"] = etiqueta(e["probabilidad"])
        e["noticias"] = [{"titulo": (ns[k]["analisis"] or {}).get("resumen") or ns[k]["titulo"], "url": ns[k]["url"],
                          "relacion": ns[k]["relacion"]} for k in e.get("noticias", []) if 0 <= k < len(ns)]
    for e in r["escenarios"]:
        if e.get("caso") not in {b[0] for b in BANDAS}:
            e["caso"] = {"sube": "optimista", "baja": "pesimista"}.get(e["direccion"], "central")
    r["escenarios"].sort(key=lambda e: -e["probabilidad"])
    r["casos"] = casos(i["serie"], dias, ind["precio"], (ind["volatilidad"] or 0) / 100, p)
    r.update({"p_sube_ia": r["p_sube"], "p_sube": p, "etiqueta": etiqueta(p) if p >= 50 else etiqueta(100 - p),
              "base": base, "rango": {"bajo": rango.get("bajo"), "alto": rango.get("alto")},
              "noticias_usadas": len(ns), "indicadores": explicar_indicadores(ind),
              "margen": margen, "margen_motivo": motivo_margen,
              "temas": temas_para(usuario, r.get("aprender", []))})
    pid = ejecutar("""INSERT INTO accion_pronostico(usuario,simbolo,creado,dias,precio,p_sube,p_usuario,datos)
                      VALUES(?,?,?,?,?,?,?,?)""",
                   (usuario, simbolo, time.time(), dias, ind["precio"], p,
                    p_usuario if p_usuario is not None else None, json.dumps(r, ensure_ascii=False))).lastrowid
    return {"id": pid, "simbolo": simbolo}


def margen_ia(usuario, simbolo):
    """Cuánto puede alejarse la IA de la tasa base (puntos). Empieza en 20; con 5+ pronósticos cerrados de esta acción
    se ajusta a su historial: si la IA lo hizo peor que la estadística sola, se acerca a ella (10 o 5); si lo hizo
    claramente mejor, gana algo de margen (25). Así el pronóstico aprende de sus errores."""
    rs = []
    for r in filas("""SELECT p_sube, datos, resultado FROM accion_pronostico WHERE usuario=? AND simbolo=?
                      AND resultado IS NOT NULL ORDER BY creado DESC LIMIT 30""", (usuario, simbolo)):
        res, d = json.loads(r["resultado"]), json.loads(r["datos"] or "{}")
        base = ((d.get("base") or {}).get("p_sube") or 50) / 100
        rs.append((res["brier"], (base - res["subio"]) ** 2))
    if len(rs) < 5:
        return 20, f"de fábrica (±20; se ajusta con 5 pronósticos cerrados, van {len(rs)})"
    b_ia, b_base = sum(x for x, _ in rs) / len(rs), sum(y for _, y in rs) / len(rs)
    habilidad = 1 - b_ia / b_base if b_base else 0
    m = 25 if habilidad > 0.1 else 20 if habilidad >= 0 else 10 if habilidad > -0.15 else 5
    return m, (f"±{m}: en {len(rs)} pronósticos cerrados la IA {'superó' if habilidad > 0 else 'no superó'} a la "
               f"estadística sola (Brier {b_ia:.3f} vs {b_base:.3f})")


def temas_para(usuario, textos, n=6):
    """Temas del currículo de la persona que explican estos conceptos (por palabras en común con el tema)."""
    import unicodedata

    def norm(t):
        t = unicodedata.normalize("NFKD", str(t).lower())
        return {w for w in re.findall(r"[a-z]{4,}", "".join(c for c in t if not unicodedata.combining(c)))
                if w not in {"para", "como", "sobre", "entre", "desde", "esta", "este", "tasa", "precio", "accion"}}
    pedidos = [norm(x) for x in textos if x]
    if not pedidos:
        return []
    puntos = {}
    for a in cur.areas(usuario).values():
        for m in a["modulos"]:
            for t in m["temas_obj"]:
                pal = norm(f"{t['t']} {t['d']}")
                mejor = max(len(q & pal) / max(1, len(q)) for q in pedidos)
                if mejor >= 0.34:
                    puntos[t["id"]] = (mejor + (0.2 if a["id"] == "finanzas" else 0), t["t"])
    return [{"id": k, "t": v[1]} for k, v in sorted(puntos.items(), key=lambda x: -x[1][0])[:n]]


# ------------------------------------------------------------------ cartera
def _tasa(moneda, a="COP"):
    if not moneda or moneda == a:
        return 1.0
    par = f"{moneda}{a}=X"
    cotizar([par], 3600)
    i = info(par)
    return ((i or {}).get("meta") or {}).get("precio")


def cartera(usuario, moneda="COP"):
    """💼 Lo que tiene la persona (acciones con cantidad): valor, ganancia, pesos por sector y por moneda, y el riesgo
    del conjunto (volatilidad de la cartera frente a la de cada acción: lo que la diversificación le ahorra)."""
    pos = [v for v in lista(usuario) if v.get("cantidad")]
    if not pos:
        return None
    filas_, series = [], {}
    for v in pos:
        i = info(v["simbolo"]) or {}
        m = i.get("meta") or {}
        tasa = _tasa(i.get("moneda"), moneda)
        precio = m.get("precio")
        if precio is None or tasa is None:
            continue
        valor = precio * v["cantidad"] * tasa
        costo = (v["precio_compra"] or precio) * v["cantidad"] * tasa
        ind = indicadores(i) or {}
        filas_.append({"simbolo": v["simbolo"], "nombre": i.get("nombre"), "moneda": i.get("moneda"),
                       "sector": (i.get("sector") or "").replace("-", "") or "Sin sector", "cantidad": v["cantidad"],
                       "precio": precio, "precio_compra": v["precio_compra"], "valor": valor, "costo": costo,
                       "ganancia": valor - costo, "ganancia_pct": (valor / costo - 1) * 100 if costo else None,
                       "hoy": (m.get("cambio") or 0) / 100 * valor / (1 + (m.get("cambio") or 0) / 100),
                       "volatilidad": ind.get("volatilidad")})
        series[v["simbolo"]] = _por_dia(i.get("serie") or [])
    total = sum(f["valor"] for f in filas_)
    if not total:
        return None
    for f in filas_:
        f["peso"] = f["valor"] / total * 100
    agrupar = lambda k: sorted(({"nombre": n, "peso": sum(f["peso"] for f in filas_ if f[k] == n)}
                                for n in {f[k] for f in filas_}), key=lambda x: -x["peso"])
    # riesgo del conjunto: rendimientos diarios ponderados en los días comunes (último año; sin el efecto del dólar)
    riesgo = None
    if len(filas_) >= 2:
        dias = sorted(set.intersection(*(set(series[f["simbolo"]]) for f in filas_)))[-253:]
        if len(dias) > 30:
            rc = [sum(f["peso"] / 100 * (series[f["simbolo"]][dias[k]] / series[f["simbolo"]][dias[k - 1]] - 1)
                      for f in filas_) for k in range(1, len(dias))]
            vol_c = statistics.pstdev(rc) * math.sqrt(252) * 100
            vol_s = sum(f["peso"] / 100 * (f["volatilidad"] or 0) for f in filas_)
            riesgo = {"volatilidad": vol_c, "suma_individual": vol_s,
                      "ahorro": (1 - vol_c / vol_s) * 100 if vol_s else None, "dias": len(rc)}
    costo = sum(f["costo"] for f in filas_)
    mayor = max(filas_, key=lambda f: f["peso"])
    avisos = []
    if mayor["peso"] > 40:
        avisos.append(f"{mayor['simbolo']} es el {mayor['peso']:.0f} % de la cartera: si le va mal, arrastra todo.")
    sect = agrupar("sector")
    if len(filas_) > 1 and sect[0]["peso"] > 60:
        avisos.append(f"El {sect[0]['peso']:.0f} % está en un solo sector ({sect[0]['nombre']}).")
    mon = agrupar("moneda")
    if len(mon) == 1 and len(filas_) > 1:
        avisos.append(f"Todo está en {mon[0]['nombre']}: no hay diversificación por moneda.")
    return {"moneda": moneda, "total": total, "costo": costo, "ganancia": total - costo,
            "ganancia_pct": (total / costo - 1) * 100 if costo else None, "hoy": sum(f["hoy"] for f in filas_),
            "posiciones": sorted(filas_, key=lambda f: -f["valor"]), "sectores": sect, "monedas": mon,
            "riesgo": riesgo, "avisos": avisos}


# ------------------------------------------------------- aprender del resultado
def evaluar(usuario):
    """Cierra los pronósticos vencidos con el precio real. Devuelve cuántos cerró."""
    vencidos = filas("""SELECT * FROM accion_pronostico WHERE usuario=? AND resultado IS NULL
                        AND creado + dias*86400 <= ?""", (usuario, time.time()))
    if not vencidos:
        return 0
    cotizar({v["simbolo"] for v in vencidos}, 3600)
    hechos = 0
    for v in vencidos:
        i = info(v["simbolo"])
        meta = v["creado"] + v["dias"] * 86400
        final = next((x for x in (i or {}).get("serie") or [] if x[0] >= meta - 6 * 3600), None)
        if not final:
            continue
        subio = final[1] > v["precio"]
        d = json.loads(v["datos"] or "{}")
        rango = d.get("rango") or {}
        res = {"precio_final": final[1], "fecha": final[0], "cambio": (final[1] / v["precio"] - 1) * 100,
               "subio": subio, "acierto": (v["p_sube"] >= 50) == subio,
               "brier": round((v["p_sube"] / 100 - subio) ** 2, 4),
               "dentro_rango": bool(rango.get("bajo") and rango["bajo"] <= final[1] <= rango["alto"])}
        if v["p_usuario"] is not None:
            res["brier_usuario"] = round((v["p_usuario"] / 100 - subio) ** 2, 4)
            res["acierto_usuario"] = (v["p_usuario"] >= 50) == subio
        ejecutar("UPDATE accion_pronostico SET resultado=? WHERE id=?", (json.dumps(res), v["id"]))
        hechos += 1
    return hechos


def calibracion(usuario):
    """¿Sirven los pronósticos? Brier medio (0 = perfecto, 0,25 = lanzar una moneda) de la IA y de la persona."""
    rs = [json.loads(r["resultado"]) for r in filas(
        "SELECT resultado FROM accion_pronostico WHERE usuario=? AND resultado IS NOT NULL", (usuario,))]
    if not rs:
        return {"n": 0}
    out = {"n": len(rs), "aciertos": sum(r["acierto"] for r in rs),
           "brier": round(sum(r["brier"] for r in rs) / len(rs), 3),
           "dentro_rango": round(100 * sum(r["dentro_rango"] for r in rs) / len(rs))}
    tuyos = [r for r in rs if "brier_usuario" in r]
    if tuyos:
        out.update({"n_usuario": len(tuyos), "aciertos_usuario": sum(r["acierto_usuario"] for r in tuyos),
                    "brier_usuario": round(sum(r["brier_usuario"] for r in tuyos) / len(tuyos), 3),
                    "brier_ia_mismos": round(sum(r["brier"] for r in tuyos) / len(tuyos), 3)})
    return out


def pronosticos(usuario, simbolo, n=12):
    out = []
    for r in filas("""SELECT * FROM accion_pronostico WHERE usuario=? AND simbolo=? ORDER BY creado DESC LIMIT ?""",
                   (usuario, simbolo, n)):
        r["datos"] = json.loads(r["datos"] or "{}")
        r["resultado"] = json.loads(r["resultado"]) if r["resultado"] else None
        out.append(r)
    return out


# ---------------------------------------------------------- lista y alertas
def lista(usuario):
    return filas("SELECT * FROM accion_vigilada WHERE usuario=? ORDER BY orden, agregada", (usuario,))


def simbolos_de(usuario):
    return [r["simbolo"] for r in lista(usuario)]


def resumen(usuario, refrescar=True):
    """La lista de la persona con precio, cambio, mini-gráfico de 30 días, último pronóstico y alertas."""
    vig = lista(usuario)
    errores = cotizar([v["simbolo"] for v in vig]) if refrescar else {}
    out = []
    for v in vig:
        i = info(v["simbolo"]) or {}
        m = i.get("meta") or {}
        serie = i.get("serie") or []
        ult = fila("""SELECT id, creado, dias, precio, p_sube, datos FROM accion_pronostico WHERE usuario=? AND simbolo=?
                      ORDER BY creado DESC LIMIT 1""", (usuario, v["simbolo"]))
        pron = None
        if ult:
            d = json.loads(ult["datos"] or "{}")
            pron = {"id": ult["id"], "creado": ult["creado"], "dias": ult["dias"], "p_sube": ult["p_sube"],
                    "sesgo": d.get("sesgo"), "etiqueta": d.get("etiqueta"),
                    "top": (d.get("escenarios") or [{}])[0].get("titulo")}
        nuevas = fila("""SELECT COUNT(*) n FROM accion_noticia WHERE simbolo=? AND publicada>? AND
                         COALESCE(json_extract(analisis,'$.relevante'),1)""",
                      (v["simbolo"], max(v["visto"] or 0, time.time() - 3 * 86400)))["n"]
        out.append({"simbolo": v["simbolo"], "nombre": i.get("nombre") or v["simbolo"], "moneda": i.get("moneda"),
                    "bolsa": i.get("bolsa"), "tipo": i.get("tipo"), "precio": m.get("precio"), "cambio": m.get("cambio"),
                    "hora": m.get("hora"), "spark": [x[1] for x in serie[-30:]], "nota": v["nota"],
                    "alerta_arriba": v["alerta_arriba"], "alerta_abajo": v["alerta_abajo"], "alerta_pct": v["alerta_pct"],
                    "cantidad": v.get("cantidad"), "precio_compra": v.get("precio_compra"),
                    "alertas": alertas_de(v, m), "pronostico": pron, "noticias_nuevas": nuevas,
                    "error": errores.get(v["simbolo"])})
    return out


def noticias_fuertes(simbolo, horas=24):
    """Noticias relevantes de impacto ±2 (según la IA) de las últimas horas: avisan aunque el precio no se mueva."""
    return filas("""SELECT id, titulo, url, json_extract(analisis,'$.impacto') impacto, json_extract(analisis,'$.resumen') resumen
                    FROM accion_noticia WHERE simbolo=? AND publicada>? AND json_extract(analisis,'$.relevante')
                    AND abs(json_extract(analisis,'$.impacto'))=2 ORDER BY publicada DESC""",
                 (simbolo, time.time() - horas * 3600))


def alertas_de(v, m):
    out = [{"tipo": f"noticia:{n['id']}", "texto": f"noticia {'muy positiva' if n['impacto'] > 0 else 'muy negativa'}: "
            f"{(n['resumen'] or n['titulo'])[:140]}", "url": n["url"]} for n in noticias_fuertes(v["simbolo"])]
    p, c = m.get("precio"), m.get("cambio")
    if p is None:
        return out
    if v["alerta_arriba"] and p >= v["alerta_arriba"]:
        out.append({"tipo": "arriba", "texto": f"superó {v['alerta_arriba']:g}"})
    if v["alerta_abajo"] and p <= v["alerta_abajo"]:
        out.append({"tipo": "abajo", "texto": f"bajó de {v['alerta_abajo']:g}"})
    if c is not None and v["alerta_pct"] and abs(c) >= v["alerta_pct"]:
        out.append({"tipo": "movimiento", "texto": f"se movió {c:+.1f} % hoy"})
    return out


def vigilar(usuario, simbolo, datos=None):
    simbolo = simbolo.strip().upper() if not simbolo.startswith("^") else simbolo.strip()
    if not valido(simbolo):
        raise ValueError("símbolo inválido")
    if len(lista(usuario)) >= 60:
        raise ValueError("máximo 60 acciones vigiladas")
    err = cotizar([simbolo], 120)
    if simbolo in err:
        raise ValueError(f"no encontré «{simbolo}» en Yahoo Finance")
    if datos and datos.get("sector"):
        ejecutar("UPDATE accion_info SET sector=?, industria=? WHERE simbolo=?",
                 (str(datos["sector"])[:80], str(datos.get("industria") or "")[:80], simbolo))
    else:
        completar_sector(simbolo)
    n = fila("SELECT COALESCE(MAX(orden),0)+1 n FROM accion_vigilada WHERE usuario=?", (usuario,))["n"]
    ejecutar("""INSERT OR IGNORE INTO accion_vigilada(usuario,simbolo,orden,alerta_pct,visto,agregada)
                VALUES(?,?,?,4,?,?)""", (usuario, simbolo, n, time.time(), time.time()))
    return simbolo


def necesita_relaciones(simbolo):
    r = fila("SELECT relaciones_fecha FROM accion_info WHERE simbolo=?", (simbolo,))
    return not r or time.time() - (r["relaciones_fecha"] or 0) > RELACIONES_VIGENTES


def conceptos(usuario):
    """Temas del currículo que explican lo que muestra la vista (solo los que existen)."""
    return [{"id": tid, "t": t} for tid, t in CONCEPTOS if cur.tema(tid, usuario)]


# ------------------------------------------------------------------ de qué se compone un fondo o índice
# Los fondos (ETF) publican qué empresas tienen y con qué peso. Un índice como el S&P 500 no se compra: se compra un
# fondo que lo copia, así que su composición es la del fondo «representante». Fuente: stockanalysis.com, que
# republica lo que el emisor publica al cierre de cada día (trae las 25 mayores posiciones, el total y la fecha).
REPRESENTANTE = {"^GSPC": "SPY", "^NDX": "QQQ", "^DJI": "DIA", "^RUT": "IWM"}
COMPOSICION_VIGENTE = 7 * 86400        # las carteras de los fondos cambian despacio: una consulta por semana
_FILA = re.compile(r"<tr[^>]*>(.*?)</tr>", re.S)
_CELDA = re.compile(r"<td[^>]*>(.*?)</td>", re.S)
_ETIQ = re.compile(r"<[^>]+>|<!--.*?-->", re.S)


def _leer_composicion(etf):
    """Baja y lee la página de posiciones de un fondo. Devuelve {fecha, total, filas:[{simbolo, nombre, peso}]}."""
    html = _get(f"https://stockanalysis.com/etf/{urllib.parse.quote(etf.lower())}/holdings/", 20).decode("utf-8", "replace")
    filas_ = []
    for tr in _FILA.findall(html):
        celdas = [_html.unescape(_ETIQ.sub("", c)).strip() for c in _CELDA.findall(tr)]
        if len(celdas) >= 4 and celdas[3].endswith("%"):
            try:
                filas_.append({"simbolo": celdas[1], "nombre": celdas[2], "peso": float(celdas[3].rstrip("%").replace(",", ""))})
            except ValueError:
                continue
    if not filas_:
        raise ValueError("no encontré la lista de posiciones")
    fecha = re.search(r'date:"([^"]+)",count:(\d+)', html)
    return {"fecha": fecha.group(1) if fecha else None, "total": int(fecha.group(2)) if fecha else len(filas_),
            "filas": filas_}


def composicion(simbolo, forzar=False):
    """Qué empresas componen el fondo o índice y qué porcentaje pesa cada una; None si no aplica (acciones sueltas)."""
    i = info(simbolo) or {}
    etf = REPRESENTANTE.get(simbolo) or (simbolo if i.get("tipo") == "ETF" and "." not in simbolo else None)
    if not etf:
        return None
    r = fila("SELECT * FROM accion_composicion WHERE simbolo=?", (etf,))
    if forzar or not r or time.time() - (r["actualizado"] or 0) > COMPOSICION_VIGENTE:
        try:
            d = _leer_composicion(etf)
            ejecutar("""INSERT INTO accion_composicion(simbolo,fuente,fecha_datos,total,filas,actualizado) VALUES(?,?,?,?,?,?)
                        ON CONFLICT(simbolo) DO UPDATE SET fuente=excluded.fuente, fecha_datos=excluded.fecha_datos,
                        total=excluded.total, filas=excluded.filas, actualizado=excluded.actualizado""",
                     (etf, "stockanalysis.com", d["fecha"], d["total"], json.dumps(d["filas"], ensure_ascii=False), time.time()))
            r = fila("SELECT * FROM accion_composicion WHERE simbolo=?", (etf,))
        except Exception as e:
            if not r:
                return {"simbolo": simbolo, "via": etf, "error": f"{type(e).__name__}: {e}"}
    filas_ = [dict(f, nombre=_html.unescape(f["nombre"])) for f in json.loads(r["filas"])]   # cachés viejas traían «&amp;»
    top = sum(f["peso"] for f in filas_)
    return {"simbolo": simbolo, "via": etf if etf != simbolo else None, "fuente": r["fuente"], "fecha": r["fecha_datos"],
            "total": r["total"], "filas": filas_, "top_pct": round(top, 2), "resto_pct": round(max(0.0, 100 - top), 2),
            "n_resto": max(0, (r["total"] or 0) - len(filas_)), "consultado": r["actualizado"]}


# ------------------------------------------------------------------ alternativas y competencia de un índice
FAMILIAS = [{
    "nombre": "S&P 500 y su competencia",
    "grupos": [
        ("📈 Fondos que copian el S&P 500 (mismo índice, distinto emisor)", [
            ("SPY", "El más antiguo y el que más se negocia; ideal para operar a corto plazo."),
            ("VOO", "El de Vanguard; pensado para quien lo guarda años."),
            ("IVV", "El de iShares (BlackRock); casi idéntico a los otros dos."),
            ("SPYM", "La versión «portafolio» de State Street (antes SPLG): misma cartera con un precio por acción más bajo.")]),
        ("🧭 Otras formas de comprar el mercado de EE. UU.", [
            ("RSP", "El mismo S&P 500 pero con peso igual para cada empresa: apuesta menos a las gigantes tecnológicas."),
            ("VTI", "Todo el mercado de EE. UU. (grandes, medianas y pequeñas) en un solo fondo.")]),
        ("⚔️ Índices que compiten con el S&P 500", [
            ("^NDX", "Nasdaq-100: las 100 mayores no financieras del Nasdaq; mucha tecnología."),
            ("^IXIC", "Nasdaq Composite: todas las empresas del Nasdaq (más de 3 000)."),
            ("^DJI", "Dow Jones: solo 30 empresas gigantes, ponderadas por precio de la acción."),
            ("^RUT", "Russell 2000: empresas pequeñas de EE. UU.; más riesgo y más ciclo económico.")]),
        ("🎯 Fondos de esos índices", [
            ("QQQ", "Copia el Nasdaq-100."), ("DIA", "Copia el Dow Jones."), ("IWM", "Copia el Russell 2000.")]),
        ("🌍 Más allá de EE. UU.", [
            ("URTH", "Acciones de países desarrollados (MSCI World); EE. UU. pesa mucho pero no es todo.")])]}]


def familia(simbolo, usuario=None):
    """Panel de alternativas si `simbolo` pertenece a una familia (S&P 500 y los suyos): quién es, cuánto rinde frente
    a los demás y si ya está en vigilancia. Solo usa lo guardado (sin red)."""
    f = next((x for x in FAMILIAS if simbolo == "^GSPC" or any(simbolo == s for g in x["grupos"] for s, _ in g[1])), None)
    if not f:
        return None
    mias = set(simbolos_de(usuario)) if usuario else set()
    grupos = []
    for titulo, items in f["grupos"]:
        filas_ = []
        for s, que in items:
            i = info(s) or {}
            ind = indicadores(i) if i.get("serie") else None
            m = i.get("meta") or {}
            filas_.append({"simbolo": s, "nombre": i.get("nombre") or s, "que": que, "vigilada": s in mias,
                           "precio": m.get("precio"), "moneda": i.get("moneda"), "cambio": m.get("cambio"),
                           "rend": {k: (ind["rend"] or {}).get(k) for k in ("1m", "3m", "1a")} if ind else None,
                           "volatilidad": ind["volatilidad"] if ind else None,
                           "tiene_composicion": s in REPRESENTANTE or i.get("tipo") == "ETF"})
        grupos.append({"titulo": titulo, "items": filas_})
    return {"nombre": f["nombre"], "grupos": grupos, "simbolos": [it["simbolo"] for g in grupos for it in g["items"]]}


def agregar_familia(usuario, nombre_familia="S&P 500 y su competencia"):
    """Pone en vigilancia a todos los de la familia (los que ya están, se saltan). Devuelve (agregados, fallidos)."""
    f = next(x for x in FAMILIAS if x["nombre"] == nombre_familia)
    nuevos = [s for g in f["grupos"] for s, _ in g[1] if s not in set(simbolos_de(usuario))]
    if "^GSPC" not in simbolos_de(usuario):
        nuevos.insert(0, "^GSPC")
    cotizar(nuevos, 120)
    hechos, fallidos = [], {}
    for s in nuevos:
        try:
            vigilar(usuario, s)
            hechos.append(s)
        except Exception as e:
            fallidos[s] = str(e)
    return hechos, fallidos


def pronostico_bajo_demanda(simbolo):
    """Los miembros de una familia (fondos y rivales del S&P 500) no se pronostican solos cada día para no ocupar la
    GPU con 14 pronósticos casi iguales: solo el ancla (^GSPC) entra en la rutina diaria. Los demás se pronostican
    cuando la persona lo pide; su estadística (casos, velas, composición) está siempre al día sin IA."""
    f = familia(simbolo)
    return bool(f) and simbolo != "^GSPC"
