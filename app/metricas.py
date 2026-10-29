"""Catálogo de métricas (fase F1): qué mide cada una, de dónde sale, cómo se calcula, cuánto se puede confiar y qué decide.

Principios (del plan de mejoras):
* **Transparencia.** Cada métrica lleva su origen (**D** directa: la persona la dio; **I** indirecta: se deduce de su comportamiento),
  su fórmula en palabras, la ventana de tiempo y la decisión que alimenta. Nada se calcula en secreto.
* **Confianza.** Cada valor trae su tamaño de muestra `n` y una confianza: *sin datos* (n = 0), *baja* (n < mínimo de la métrica),
  *media* (n < 3 × mínimo) o *alta*. **Una métrica de confianza baja o sin datos NO debe decidir nada**: `usable()` lo comprueba.
* **La persona manda.** Puede marcar una métrica como «esto está mal» o «ignorar», o apagar una familia entera: `usable()` lo respeta.
* **Por persona.** Todo se calcula con los eventos y tablas de UNA persona; no hay ninguna agregación entre perfiles.

Cada métrica es una función `(contexto) -> (valor, n)` registrada con `@metrica(...)`. El valor es un número, un texto o `None`.
"""
import json
import statistics
import time
from datetime import datetime

import eventos
from base import ejecutar, fila, filas, kv_get, kv_set

DIA = 86400
CONFIANZAS = ("sin datos", "baja", "media", "alta")
# Tipos de evento que cuentan como «estudiar» (días activos, rachas, cambios de tema…)
ESTUDIO = {"tiempo", "repaso", "lectura", "quiz", "prueba", "practica", "entrega", "apunte", "leccion", "chequeo_tema", "pulso"}
# Tipos que dicen sobre qué tema se estudia
CON_TEMA = {"repaso", "lectura", "quiz", "prueba", "practica", "entrega", "apunte", "leccion", "chequeo_tema"}
FAMILIAS = {
    "memoria": "Dominio y memoria", "lectura": "Lectura y atención", "habito": "Ritmo y hábito", "estilo": "Estilo de aprendizaje",
    "contenido": "Contenido y calidad", "metas": "Metas y avance", "decision": "Decisión y comportamiento", "sistema": "Sistema",
}

CATALOGO = {}


def metrica(id, familia, nombre, origen, formula, ventana, decide, n_min=5, unidad=""):
    def deco(fn):
        CATALOGO[id] = {"id": id, "familia": familia, "nombre": nombre, "origen": origen, "formula": formula,
                        "ventana": ventana, "decide": decide, "n_min": n_min, "unidad": unidad, "fn": fn}
        return fn
    return deco


class Contexto:
    """Lo que ve una métrica: la persona y el momento, con atajos cacheados para no repetir consultas."""

    def __init__(self, usuario, ahora=None):
        self.u, self.ahora = usuario, ahora or time.time()
        self._cache = {}

    def desde(self, dias):
        return self.ahora - dias * DIA

    def eventos(self, tipo, dias):
        k = (tipo, dias)
        if k not in self._cache:
            self._cache[k] = eventos.de_persona(self.u, tipo, self.desde(dias), self.ahora + 1)
        return self._cache[k]

    def estudio(self, dias):
        k = ("estudio", dias)
        if k not in self._cache:
            self._cache[k] = [e for e in eventos.de_persona(self.u, None, self.desde(dias), self.ahora + 1) if e["tipo"] in ESTUDIO]
        return self._cache[k]

    def cobertura(self, dias):
        """Días de historia realmente disponibles dentro de la ventana (una persona con 3 días de uso no tiene 30 de datos).
        Es la muestra de las métricas de hábito: contar eventos inflaría la confianza."""
        if "primero" not in self._cache:
            self._cache["primero"] = fila("SELECT MIN(ts) t FROM evento WHERE usuario=?", (self.u,))["t"]
        t = self._cache["primero"]
        return 0 if t is None else max(1, min(dias, int((self.ahora - t) // DIA) + 1))

    def consulta(self, sql, *args):
        return filas(sql, (self.u,) + args)


def dia_local(ts):
    return datetime.fromtimestamp(ts - 4 * 3600).date()   # lo de madrugada cuenta para el día anterior (como `analitica`)


def _media(v):
    v = [x for x in v if x is not None]
    return (round(sum(v) / len(v), 3), len(v)) if v else (None, 0)


def _mediana(v):
    v = [x for x in v if x is not None]
    return (round(statistics.median(v), 2), len(v)) if v else (None, 0)


def _tema_de(e):
    return e["objeto"] if e["tipo"] in CON_TEMA and e["objeto"] else None


def _area_de(e):
    a = (e["contexto"] or {}).get("area")
    if a:
        return a
    o = e["objeto"] or ""
    return o.split(".")[0] if "." in o else None


# ================================================================== Dominio y memoria
@metrica("temas_dominados", "memoria", "Temas dominados", "D",
         "Temas con estado «dominado» o «probado» en el avance. Aún no exige prueba diferida (eso llega en la fase F3).",
         "acumulado", "Estados de dominio (F3) y señales de aporte (F7)", 1, "temas")
def _(c):
    r = c.consulta("SELECT COUNT(*) n, SUM(estado IN ('dominado','probado')) d FROM avance WHERE usuario=?")[0]
    return (r["d"] or 0, r["n"]) if r["n"] else (None, 0)


@metrica("temas_expuestos", "memoria", "Temas vistos sin dominar", "D",
         "Temas con estado «visto» (se abrió la lección o la ruta rápida, sin pasar su verificación).",
         "acumulado", "Barra «explorado» frente a «dominado» (F3)", 1, "temas")
def _(c):
    r = c.consulta("SELECT COUNT(*) n, SUM(estado='visto') v FROM avance WHERE usuario=?")[0]
    return (r["v"] or 0, r["n"]) if r["n"] else (None, 0)


def _retencion(lo, hi):
    def f(c):
        rs = [e for e in c.eventos("repaso", 180) if lo <= (e["contexto"].get("dias") or -1) <= hi]
        return (round(sum(1 for e in rs if e["valor"] and e["valor"] > 1) / len(rs), 3), len(rs)) if rs else (None, 0)
    return f


for _id, _lo, _hi, _txt in (("retencion_1d", 0.5, 2, "1 día"), ("retencion_7d", 5, 10, "7 días"),
                            ("retencion_30d", 20, 40, "30 días"), ("retencion_90d", 60, 120, "90 días")):
    metrica(_id, "memoria", f"Retención a {_txt}", "D",
            f"De los repasos hechos cuando la tarjeta llevaba entre {_lo:g} y {_hi:g} días sin verse, qué fracción se contestó bien (nota ≥ 2).",
            "180 días", "Intervalos de repaso y diagnóstico de olvido", 8, "%")(_retencion(_lo, _hi))


@metrica("estabilidad_fsrs", "memoria", "Estabilidad media de las tarjetas", "I",
         "Promedio de la estabilidad FSRS (días hasta que la probabilidad de recordar baja al 90 %) de las tarjetas ya repasadas.",
         "acumulado", "Cuánto tardar en repasar; estado 5 «domina» (F3)", 10, "días")
def _(c):
    r = c.consulta("SELECT AVG(estabilidad) a, COUNT(*) n FROM tarjeta WHERE usuario=? AND estabilidad IS NOT NULL AND repasos>0")[0]
    return (round(r["a"], 1), r["n"]) if r["n"] else (None, 0)


@metrica("dificultad_fsrs", "memoria", "Dificultad media de las tarjetas", "I",
         "Promedio de la dificultad FSRS (1 fácil – 10 difícil) de las tarjetas ya repasadas.",
         "acumulado", "Qué temas reforzar y con qué formato", 10, "1-10")
def _(c):
    r = c.consulta("SELECT AVG(dificultad) a, COUNT(*) n FROM tarjeta WHERE usuario=? AND dificultad IS NOT NULL AND repasos>0")[0]
    return (round(r["a"], 2), r["n"]) if r["n"] else (None, 0)


@metrica("acierto_quiz", "memoria", "Acierto medio en quizzes", "D",
         "Promedio del puntaje (0-1) de los quizzes de lección de los últimos 90 días.", "90 días",
         "Cuándo dar por comprendido un tema", 5, "0-1")
def _(c):
    return _media([e["valor"] for e in c.eventos("quiz", 90)])


@metrica("acierto_prueba", "memoria", "Acierto medio en pruebas de nivel", "D",
         "Promedio del puntaje (0-1) de las pruebas de nivel de los últimos 90 días.", "90 días",
         "Ubicar el nivel real y saltar lo que ya sabe", 3, "0-1")
def _(c):
    return _media([e["valor"] for e in c.eventos("prueba", 90)])


@metrica("feynman_medio", "memoria", "Explicación con tus palabras (Feynman)", "D",
         "Promedio del mejor puntaje Feynman (0-1) de los temas donde se intentó.", "acumulado",
         "Estado 3 «comprende» (F3)", 3, "0-1")
def _(c):
    return _media([r["feynman"] for r in c.consulta("SELECT feynman FROM avance WHERE usuario=? AND feynman IS NOT NULL")])


@metrica("errores_repetidos", "memoria", "Tarjetas que fallas una y otra vez", "I",
         "Número de tarjetas con 2 o más fallos (nota «Otra vez»).", "acumulado", "Reexplicar el concepto en vez de repetir la tarjeta", 5, "tarjetas")
def _(c):
    r = c.consulta("SELECT COUNT(*) n, SUM(fallos>=2) f FROM tarjeta WHERE usuario=? AND repasos>0")[0]
    return (r["f"] or 0, r["n"]) if r["n"] else (None, 0)


@metrica("olvido_estimado", "memoria", "Tarjetas que ya probablemente olvidaste", "I",
         "Fracción de tarjetas repasadas cuya probabilidad actual de recordarlas (FSRS) es menor de 80 %.", "acumulado",
         "Prioridad de repaso y requisitos por reponer", 10, "%")
def _(c):
    import fsrs
    ts = c.consulta("SELECT estabilidad, ultimo FROM tarjeta WHERE usuario=? AND estabilidad IS NOT NULL AND ultimo IS NOT NULL")
    if not ts:
        return None, 0
    bajas = sum(1 for t in ts if fsrs.retenibilidad((c.ahora - t["ultimo"]) / DIA, t["estabilidad"]) < 0.8)
    return round(bajas / len(ts), 3), len(ts)


@metrica("tasa_lapsos", "memoria", "Tasa de lapsos en repaso", "D",
         "Fracción de repasos de 30 días calificados «Otra vez» (nota 1).", "30 días", "Ajustar cuántas tarjetas nuevas por día", 20, "%")
def _(c):
    rs = c.eventos("repaso", 30)
    return (round(sum(1 for e in rs if e["valor"] == 1) / len(rs), 3), len(rs)) if rs else (None, 0)


@metrica("tarjetas_vencidas", "memoria", "Tarjetas vencidas ahora", "I",
         "Tarjetas no suspendidas cuya fecha de repaso ya pasó.", "ahora", "Cuánto repaso pesa en el plan de hoy", 1, "tarjetas")
def _(c):
    r = filas("SELECT COUNT(*) n, SUM(vence<=?) v FROM tarjeta WHERE usuario=? AND suspendida=0 AND vence IS NOT NULL",
              (c.ahora, c.u))[0]
    return (r["v"] or 0, r["n"]) if r["n"] else (None, 0)


@metrica("segundos_por_tarjeta", "memoria", "Segundos por tarjeta", "I",
         "Mediana de segundos por repaso (se descartan los de más de 5 minutos) en 30 días.", "30 días",
         "Tamaño de la sesión de repaso", 20, "s")
def _(c):
    return _mediana([(e["contexto"].get("segundos")) for e in c.eventos("repaso", 30)
                     if e["contexto"].get("segundos") and e["contexto"]["segundos"] < 300])


# ================================================================== Lectura y atención
@metrica("wpm_es", "lectura", "Velocidad de lectura en español", "I",
         "Palabras por minuto en textos en español, medidas con el tiempo de lectura activa (por defecto 180 hasta tener 5 min leídos).",
         "30 días", "Estimar cuánto dura una lección para esta persona", 1, "palabras/min")
def _(c):
    import lectura
    v = lectura.velocidades(c.u).get("es", {})
    return (round(v["wpm"]), round(v.get("min", 0))) if v.get("wpm") and v.get("min", 0) >= 5 else (None, 0)


def _sesiones(c, dias=30):
    return [e for e in c.eventos("lectura", dias) if e["valor"] and e["valor"] >= 20]


@metrica("palabras_por_sesion", "lectura", "Palabras leídas por sesión", "I",
         "Promedio de palabras de las sesiones de lectura de 20 segundos o más.", "30 días", "Longitud de las partes de una lección", 5, "palabras")
def _(c):
    return _media([e["contexto"].get("palabras") for e in _sesiones(c)])


@metrica("avance_medio_lectura", "lectura", "Cuánto de cada lectura termina", "I",
         "Promedio del avance (0-1) de las sesiones de lectura.", "30 días", "Si recomendar ruta rápida o lección completa", 5, "0-1")
def _(c):
    return _media([e["contexto"].get("avance") for e in _sesiones(c)])


@metrica("abandono_lectura", "lectura", "Lecturas que abandona a medias", "I",
         "Fracción de sesiones de lectura que terminaron con menos del 50 % de avance.", "30 días",
         "Partir las lecciones en partes más cortas", 5, "%")
def _(c):
    s = _sesiones(c)
    return (round(sum(1 for e in s if (e["contexto"].get("avance") or 0) < 0.5) / len(s), 3), len(s)) if s else (None, 0)


@metrica("lectura_completa", "lectura", "Lecturas que termina", "I",
         "Fracción de sesiones de lectura con 90 % de avance o más.", "30 días", "Formato recomendado", 5, "%")
def _(c):
    s = _sesiones(c)
    return (round(sum(1 for e in s if (e["contexto"].get("avance") or 0) >= 0.9) / len(s), 3), len(s)) if s else (None, 0)


@metrica("relecturas", "lectura", "Temas que relee", "I",
         "Fracción de los temas leídos en 60 días que tienen 2 o más sesiones de lectura.", "60 días",
         "Detectar partes que no se entienden a la primera", 5, "%")
def _(c):
    por = {}
    for e in c.eventos("lectura", 60):
        if e["objeto"]:
            por[e["objeto"]] = por.get(e["objeto"], 0) + 1
    return (round(sum(1 for n in por.values() if n >= 2) / len(por), 3), len(por)) if por else (None, 0)


@metrica("uso_audio", "lectura", "Uso de audio al leer", "I",
         "Fracción de sesiones de lectura en las que el audio sonó.", "30 días", "Ofrecer o no la lectura en voz alta", 5, "%")
def _(c):
    s = _sesiones(c)
    return (round(sum(1 for e in s if (e["contexto"].get("audio") or 0) > 0) / len(s), 3), len(s)) if s else (None, 0)


@metrica("lectura_que_termina", "lectura", "Longitud de lectura que sí termina", "I",
         "Mediana de palabras de las sesiones terminadas (avance ≥ 90 %).", "60 días", "Tamaño ideal de cada parte de una lección", 5, "palabras")
def _(c):
    return _mediana([e["contexto"].get("palabras") for e in _sesiones(c, 60) if (e["contexto"].get("avance") or 0) >= 0.9])


@metrica("reexplicaciones_30d", "lectura", "Reexplicaciones pedidas", "D",
         "Veces que pidió explicarle una parte de otra forma.", "30 días", "Estilo de explicación que le funciona", 3, "veces")
def _(c):
    n = len(c.eventos("reexplicacion", 30))
    return (n, n) if n else (None, 0)


@metrica("partes_no_entendidas", "lectura", "Partes que marcó «no lo entendí»", "D",
         "De las partes de lección marcadas con «¿lo entendiste?» (sabido, dudoso o no) en 90 días, fracción con respuesta «no».",
         "90 días", "Qué partes reexplicar antes de seguir", 5, "%")
def _(c):
    no = len(c.eventos("parte_no", 90))
    total = no + len(c.eventos("parte_dudoso", 90)) + len(c.eventos("parte_sabido", 90))
    return (round(no / total, 3), total) if total else (None, 0)


# ================================================================== Ritmo y hábito
def _minutos(dias):
    def f(c):
        s = [e["valor"] for e in c.eventos("tiempo", dias) if e["valor"]]
        return (round(sum(s) / 60, 1), c.cobertura(dias)) if s else (None, 0)
    return f


for _d in (7, 14, 30):
    metrica(f"minutos_{_d}d", "habito", f"Minutos de estudio ({_d} días)", "I",
            "Suma de los latidos de estudio activo (la interfaz solo cuenta con acción real o audio sonando).", f"{_d} días",
            "Cuánto pesa el plan del día", 5, "min")(_minutos(_d))


def _dias_activos(c, dias):
    return sorted({dia_local(e["ts"]) for e in c.estudio(dias)})


def _dias_n(dias):
    def f(c):
        d = _dias_activos(c, dias)
        return (len(d), c.cobertura(dias)) if d else (None, 0)
    return f


for _d in (7, 14, 30):
    metrica(f"dias_activos_{_d}d", "habito", f"Días activos ({_d} días)", "I",
            "Días distintos con alguna actividad de estudio (tiempo, repaso, lectura, quiz, prueba, práctica, entrega…).",
            f"{_d} días", "Adherencia (F11) y tamaño de la sesión", 3, f"de {_d}")(_dias_n(_d))


def _racha(dias_set, hoy):
    """Días seguidos hasta hoy; si hoy aún no estudió, cuenta desde ayer (la racha no se rompe hasta que pasa el día)."""
    d = hoy if hoy in dias_set else hoy.fromordinal(hoy.toordinal() - 1)
    n = 0
    while d in dias_set:
        n += 1
        d = d.fromordinal(d.toordinal() - 1)
    return n


@metrica("racha_actual", "habito", "Racha actual", "I",
         "Días seguidos con actividad de estudio hasta hoy (o hasta ayer si hoy aún no estudió).", "90 días",
         "Avisos y modo corto (F11)", 3, "días")
def _(c):
    d = set(_dias_activos(c, 90))
    return (_racha(d, dia_local(c.ahora)), c.cobertura(90)) if d else (None, 0)


@metrica("racha_maxima", "habito", "Mejor racha de 90 días", "I",
         "La racha más larga de días seguidos con actividad en los últimos 90 días.", "90 días", "Meta realista de constancia", 3, "días")
def _(c):
    d = _dias_activos(c, 90)
    if not d:
        return None, 0
    mejor = act = 1
    for a, b in zip(d, d[1:]):
        act = act + 1 if (b - a).days == 1 else 1
        mejor = max(mejor, act)
    return mejor, c.cobertura(90)


@metrica("recaidas_30d", "habito", "Recaídas (3 días o más sin estudiar)", "I",
         "Cuántas veces pasaron 3 o más días seguidos sin actividad entre dos días activos, en 30 días.", "30 días",
         "Cuándo mandar un aviso o bajar la exigencia", 3, "veces")
def _(c):
    d = _dias_activos(c, 30)
    return (sum(1 for a, b in zip(d, d[1:]) if (b - a).days > 3), c.cobertura(30)) if len(d) >= 2 else (None, c.cobertura(30))


@metrica("hora_tipica", "habito", "Hora en que más estudia", "I",
         "Hora del día (0-23) con más segundos de estudio activo en 30 días.", "30 días", "Hora del aviso y de preparar lecciones", 7, "h")
def _(c):
    por = {}
    for e in c.eventos("tiempo", 30):
        h = datetime.fromtimestamp(e["ts"]).hour
        por[h] = por.get(h, 0) + (e["valor"] or 0)
    return (max(por, key=por.get), c.cobertura(30)) if por else (None, 0)


@metrica("duracion_sesion", "habito", "Duración típica de una sesión", "I",
         "Mediana de minutos de estudio de las sesiones (una sesión se corta con 30 minutos sin actividad), en 30 días.", "30 días",
         "Tamaño de la sesión que sí termina y modo corto", 5, "min")
def _(c):
    ev = sorted(c.eventos("tiempo", 30), key=lambda e: e["ts"])
    ses, act, ult = [], 0.0, None
    for e in ev:
        if ult is not None and e["ts"] - ult > 1800:
            ses.append(act / 60); act = 0.0
        act += e["valor"] or 0; ult = e["ts"]
    if ult is not None:
        ses.append(act / 60)
    return _mediana(ses)


@metrica("minutos_por_dia_activo", "habito", "Minutos por día activo", "I",
         "Minutos de estudio de 14 días / días activos de esos 14 días.", "14 días", "Tamaño del plan diario", 3, "min")
def _(c):
    m, d = _minutos(14)(c)[0], len(_dias_activos(c, 14))
    return (round(m / d, 1), d) if m is not None and d else (None, 0)


@metrica("minutos_por_tema_dominado", "habito", "Minutos de estudio por tema dominado", "I",
         "TODO el tiempo de estudio registrado (minutos) / temas con estado «dominado» o «probado». Es la fórmula única: la línea base "
         "de la fase F0 y el panel usan esta definición.", "acumulado",
         "La meta «aprender más rápido con el tiempo» (baja si se mejora)", 3, "min/tema")
def _(c):
    seg = c.consulta("SELECT IFNULL(SUM(valor),0) s FROM actividad WHERE usuario=? AND tipo='tiempo'")[0]["s"]
    dom = c.consulta("SELECT COUNT(*) n FROM avance WHERE usuario=? AND estado IN ('dominado','probado')")[0]["n"]
    return (round(seg / 60 / dom), dom) if dom else (None, 0)


# ================================================================== Estilo de aprendizaje
@metrica("metodo_mas_tiempo", "estilo", "Método al que dedica más tiempo", "I",
         "Método (lección, noticias, lectura, tutor) con más segundos de lectura activa en 30 días.", "30 días",
         "Formato recomendado y orden de las actividades", 5, "")
def _(c):
    por = {}
    for e in _sesiones(c):
        m = e["contexto"].get("metodo") or "otro"
        por[m] = por.get(m, 0) + e["valor"]
    return (max(por, key=por.get), sum(1 for _ in _sesiones(c))) if por else (None, 0)


@metrica("mejor_franja", "estilo", "Franja del día en que mejor repasa", "I",
         "Franja (madrugada 0-5, mañana 6-11, tarde 12-17, noche 18-23) con mayor fracción de repasos bien contestados; "
         "solo cuentan franjas con 10 repasos o más.", "90 días", "Cuándo programar lo difícil", 30, "")
def _(c):
    franjas = {}
    rs = c.eventos("repaso", 90)
    for e in rs:
        h = datetime.fromtimestamp(e["ts"]).hour
        f = "madrugada" if h < 6 else "mañana" if h < 12 else "tarde" if h < 18 else "noche"
        franjas.setdefault(f, []).append(1 if (e["valor"] or 0) > 1 else 0)
    validas = {f: sum(v) / len(v) for f, v in franjas.items() if len(v) >= 10}
    return (max(validas, key=validas.get), len(rs)) if validas else (None, len(rs))


# ================================================================== Contenido y calidad
@metrica("lecciones_completas", "contenido", "Lecciones completas escritas para ti", "I",
         "Lecciones de la persona con estado «completa».", "acumulado", "Cuánto preparar por adelantado", 1, "lecciones")
def _(c):
    n = c.consulta("SELECT COUNT(*) n FROM leccion WHERE usuario=? AND completa!=0")[0]["n"]
    return (n, n) if n else (None, 0)


@metrica("lecciones_abiertas", "contenido", "Lecciones preparadas que sí abre", "I",
         "De las lecciones completas escritas, fracción cuyo tema tiene fecha de «visto» en el avance.", "acumulado",
         "Si preparar menos por adelantado", 5, "%")
def _(c):
    r = c.consulta("""SELECT COUNT(*) n, SUM(a.visto IS NOT NULL) v FROM leccion l LEFT JOIN avance a ON a.usuario=l.usuario AND a.tema=l.tema
                      WHERE l.usuario=? AND l.completa!=0""")[0]
    return (round((r["v"] or 0) / r["n"], 3), r["n"]) if r["n"] else (None, 0)


@metrica("verificaciones", "contenido", "Verificaciones de contenido hechas", "I",
         "Cuántas lecciones o afirmaciones se verificaron contra fuentes para esta persona.", "acumulado",
         "Qué contenido revisar con otra pasada", 1, "verificaciones")
def _(c):
    n = c.consulta("SELECT COUNT(*) n FROM verificacion WHERE usuario=?")[0]["n"]
    return (n, n) if n else (None, 0)


@metrica("tareas_ia_fallidas", "contenido", "Tareas de IA que fallaron", "I",
         "Tareas de IA de esta persona que terminaron con error en 30 días.", "30 días", "Confiabilidad de cada modelo (F2)", 1, "tareas")
def _(c):
    r = filas("SELECT COUNT(*) n, SUM(estado='error') e FROM trabajo_hecho WHERE usuario=? AND terminado>?", (c.u, c.desde(30)))[0]
    return (r["e"] or 0, r["n"]) if r["n"] else (None, 0)


@metrica("gasto_api", "contenido", "Gasto en la API de IA este mes", "I",
         "Dólares estimados que esta persona ha gastado en la API opcional en el mes en curso.", "mes", "Tope y enrutador de modelos (F2)", 1, "USD")
def _(c):
    try:
        import nube
        g = nube.gastado(c.u)
    except Exception:
        return None, 0
    return (g, 1) if g else (None, 0)


# ================================================================== Metas y avance
@metrica("metas_activas", "metas", "Metas activas", "D",
         "Objetivos de la persona con estado «activo».", "ahora", "Cuántas rutas críticas ordenar (F6)", 1, "metas")
def _(c):
    n = c.consulta("SELECT COUNT(*) n FROM objetivo WHERE usuario=? AND estado='activo'")[0]["n"]
    return (n, n) if n else (None, 0)


@metrica("entregas_corregidas", "metas", "Entregas corregidas", "D",
         "Entregas de práctica ya corregidas en 90 días.", "90 días", "Dominio nivel 4 «aplica» (F3)", 1, "entregas")
def _(c):
    n = len([e for e in c.eventos("entrega", 90) if e["contexto"].get("corregida")])
    return (n, n) if n else (None, 0)


@metrica("puntaje_entregas", "metas", "Puntaje medio de las entregas", "D",
         "Promedio del puntaje (0-100) de las entregas corregidas en 90 días.", "90 días", "Estado 4 «aplica» (F3)", 3, "pts")
def _(c):
    return _media([e["valor"] for e in c.eventos("entrega", 90) if e["contexto"].get("corregida") and e["valor"] is not None])


# ================================================================== Decisión y comportamiento
@metrica("variedad_areas_7d", "decision", "Áreas distintas en la semana", "I",
         "Número de áreas distintas con actividad de estudio en 7 días (dispersión entre áreas).", "7 días",
         "Avisar de dispersión y tope de áreas activas (F5)", 5, "áreas")
def _(c):
    ev = [e for e in c.estudio(7) if _tema_de(e)]
    return (len({_area_de(e) for e in ev if _area_de(e)}), len(ev)) if ev else (None, 0)


@metrica("cambios_de_tema_7d", "decision", "Cambios de tema en la semana", "I",
         "Veces que el tema cambió entre dos actividades de estudio seguidas, en 7 días.", "7 días",
         "Intercalado frente a bloque; fatiga (F5)", 10, "cambios")
def _(c):
    ev = sorted((e for e in c.estudio(7) if _tema_de(e)), key=lambda e: e["ts"])
    return (sum(1 for a, b in zip(ev, ev[1:]) if a["objeto"] != b["objeto"]), len(ev)) if len(ev) >= 2 else (None, len(ev))


@metrica("sugerencias_14d", "decision", "Sugerencias de «Hoy» mostradas", "I",
         "Siguientes pasos propuestos por la pantalla «Hoy» (uno por hora y destino) en 14 días.", "14 días",
         "Base para medir si el orden propuesto se sigue", 5, "sugerencias")
def _(c):
    n = len(c.eventos("sugerencia", 14))
    return (n, n) if n else (None, 0)


@metrica("acuerdo_sugerencia", "decision", "Cuánto sigue lo que Hoy le sugiere", "I",
         "De las sugerencias seguidas por una navegación desde «Hoy» en los 30 minutos siguientes, fracción en que fue justo "
         "al destino sugerido.", "14 días", "Aprender los pesos del ordenador por persona (F5)", 5, "%")
def _(c):
    sug = c.eventos("sugerencia", 14)
    nav = [e for e in c.eventos("navega", 14) if e["contexto"].get("desde") == "hoy"]
    si = total = 0
    for s in sug:
        sig = next((n for n in nav if s["ts"] < n["ts"] <= s["ts"] + 1800), None)
        if sig:
            total += 1
            si += 1 if sig["objeto"] == s["objeto"] else 0
    return (round(si / total, 3), total) if total else (None, 0)


@metrica("tiempo_en_decidir", "decision", "Tiempo en «Hoy» antes de decidir", "I",
         "Mediana de segundos que pasa en la vista «Hoy» antes de ir a otra, en 14 días.", "14 días",
         "Reducir la parálisis: un solo siguiente paso", 5, "s")
def _(c):
    return _mediana([e["valor"] for e in c.eventos("vista", 14) if e["objeto"] == "hoy"])


# ================================================================== cálculo, confianza y ajustes de la persona
def confianza(n, n_min):
    if not n:
        return "sin datos"
    if n < n_min:
        return "baja"
    return "media" if n < 3 * n_min else "alta"


def init():
    eventos.iniciar_tablas()
    ejecutar("""CREATE TABLE IF NOT EXISTS metrica_valor (
        usuario TEXT NOT NULL, id TEXT NOT NULL, dia TEXT NOT NULL, ts REAL, valor TEXT, n INTEGER, confianza TEXT,
        PRIMARY KEY (usuario, id, dia))""")
    ejecutar("""CREATE TABLE IF NOT EXISTS metrica_ajuste (
        usuario TEXT NOT NULL, id TEXT NOT NULL, estado TEXT NOT NULL, nota TEXT, ts REAL, PRIMARY KEY (usuario, id))""")


def ajustes(usuario):
    return {r["id"]: r for r in filas("SELECT id, estado, nota, ts FROM metrica_ajuste WHERE usuario=?", (usuario,))}


def familias_apagadas(usuario):
    return set(kv_get(f"metricas_off:{usuario}", []) or [])


def calcular(usuario, ahora=None, solo=None):
    """Todas las métricas de UNA persona, con su ficha, valor, muestra y confianza, más lo que la persona decidió
    (ignorada, marcada como errónea, familia apagada). Una métrica que falla devuelve error en vez de tirar el resto."""
    c = Contexto(usuario, ahora)
    aj, off = ajustes(usuario), familias_apagadas(usuario)
    out = []
    for m in CATALOGO.values():
        if solo and m["id"] not in solo:
            continue
        ficha = {k: m[k] for k in ("id", "familia", "nombre", "origen", "formula", "ventana", "decide", "n_min", "unidad")}
        ficha["familia_nombre"] = FAMILIAS[m["familia"]]
        try:
            valor, n = m["fn"](c)
            ficha.update(valor=valor, n=int(n or 0), error=None)
        except Exception as e:  # noqa: BLE001
            ficha.update(valor=None, n=0, error=f"{type(e).__name__}: {e}"[:160])
        ficha["confianza"] = confianza(ficha["n"], m["n_min"])
        a = aj.get(m["id"])
        ficha["ajuste"] = {"estado": a["estado"], "nota": a["nota"]} if a else None
        ficha["familia_apagada"] = m["familia"] in off
        ficha["usable"] = usable(ficha)
        out.append(ficha)
    return out


def usable(ficha):
    """¿Puede esta métrica alimentar una decisión? Solo con confianza media o alta, sin error, y si la persona no la
    ignoró, no la marcó como errónea ni apagó su familia."""
    return (ficha.get("error") is None and ficha["confianza"] in ("media", "alta") and not ficha.get("ajuste")
            and not ficha.get("familia_apagada"))


def guardar_foto(usuario, ahora=None):
    """Una fila por métrica y día (la del día se reemplaza): el historial permite ver la tendencia. Devuelve cuántas guardó."""
    ahora = ahora or time.time()
    dia = dia_local(ahora).isoformat()
    n = 0
    for m in calcular(usuario, ahora):
        if m["valor"] is None and not m["n"]:
            continue
        ejecutar("""INSERT INTO metrica_valor(usuario,id,dia,ts,valor,n,confianza) VALUES(?,?,?,?,?,?,?)
                    ON CONFLICT(usuario,id,dia) DO UPDATE SET ts=excluded.ts, valor=excluded.valor, n=excluded.n,
                    confianza=excluded.confianza""", (usuario, m["id"], dia, ahora, json.dumps(m["valor"]), m["n"], m["confianza"]))
        n += 1
    return n


def tendencia(usuario, id, dias=60):
    return [{"dia": r["dia"], "valor": json.loads(r["valor"]), "n": r["n"], "confianza": r["confianza"]}
            for r in filas("SELECT dia, valor, n, confianza FROM metrica_valor WHERE usuario=? AND id=? ORDER BY dia DESC LIMIT ?",
                           (usuario, id, dias))][::-1]


def ajustar(usuario, id, estado, nota="", ahora=None):
    """La persona corrige al sistema: estado «mal» (el dato es erróneo), «ignorar» (no quiere que decida) o «ok» (quita el ajuste)."""
    if id not in CATALOGO:
        raise ValueError("esa métrica no existe")
    if estado not in ("mal", "ignorar", "ok"):
        raise ValueError("estado inválido (mal, ignorar u ok)")
    if estado == "ok":
        ejecutar("DELETE FROM metrica_ajuste WHERE usuario=? AND id=?", (usuario, id))
    else:
        ejecutar("""INSERT INTO metrica_ajuste(usuario,id,estado,nota,ts) VALUES(?,?,?,?,?)
                    ON CONFLICT(usuario,id) DO UPDATE SET estado=excluded.estado, nota=excluded.nota, ts=excluded.ts""",
                 (usuario, id, estado, str(nota or "")[:300], ahora or time.time()))
    return {"ok": True}


def apagar_familia(usuario, familia, apagada=True):
    if familia not in FAMILIAS:
        raise ValueError("esa familia no existe")
    off = familias_apagadas(usuario)
    (off.add if apagada else off.discard)(familia)
    kv_set(f"metricas_off:{usuario}", sorted(off))
    return {"ok": True, "apagadas": sorted(off)}
