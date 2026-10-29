"""Evaluación de corto y largo plazo, adaptación de cada sesión, plan del día
(con sesiones extra), revisión de cómo cambia la forma de aprender y reportes.

- Pulso diario (corto plazo, 1-2 min): 5 tarjetas que miden lo de ayer y lo
  más antiguo; también 2 tarjetas «antes de seguir» dentro de cada lección.
- Largo plazo: retención según la EDAD del conocimiento (días desde que se
  aprendió), y el recuerdo verificado más antiguo.
- Plan adaptativo: ajusta cuántos temas nuevos, qué recuperar primero, la hora
  y el bloque recomendados, y el método, según los datos.
- Instantáneas semanales del perfil de aprendizaje para ver cómo cambia.
"""
import csv
import io
import json
import math
import random
import re
import time
import zipfile
from datetime import datetime, timedelta
from pathlib import Path

import adaptativo as aa
import analitica as an
import estados  # noqa: F401  (crea la tabla de las pruebas diferidas)
import ejecucion  # noqa: F401  (crea las tablas de la práctica con código, que el reporte y la exportación leen)
import curriculo as cur
from base import ejecutar, fila, filas, kv_get, kv_set

DIA = 86400

ejecutar("""CREATE TABLE IF NOT EXISTS instantanea (
  usuario TEXT, semana TEXT, datos TEXT, creada REAL, PRIMARY KEY (usuario, semana))""")


def hoy_clave(t=None):
    d = datetime.fromtimestamp(t or time.time())
    if d.hour < 4:
        d -= timedelta(days=1)
    return d.strftime("%Y-%m-%d")


def inicio_hoy():
    d = datetime.strptime(hoy_clave(), "%Y-%m-%d").replace(hour=4)
    return d.timestamp()


# ------------------------------------------------------------- corto plazo
def pulso(usuario, n=5, modo="diario", excluir_tema=None):
    """Tarjetas para medir el recuerdo: de 1-3 días (corto plazo), las más
    antiguas (largo plazo) y la más débil. No repite las ya vistas hoy."""
    ahora = time.time()
    vistas_hoy = {r["tarjeta"] for r in filas("SELECT tarjeta FROM repaso WHERE usuario=? AND fecha>?",
                                             (usuario, inicio_hoy()))}
    maduras = [t for t in filas("""SELECT * FROM tarjeta WHERE usuario=? AND suspendida=0 AND estabilidad IS NOT NULL""",
                                (usuario,)) if t["id"] not in vistas_hoy and t["tema"] != excluir_tema]
    if not maduras:
        return []
    recientes = [t for t in maduras if ahora - t["creada"] < 3 * DIA]
    antiguas = sorted(maduras, key=lambda t: t["creada"])
    debiles = sorted(maduras, key=lambda t: an.r_actual(t, ahora) or 1)
    elegidas, ids = [], set()

    def tomar(lista, k, tipo):
        for t in lista:
            if len([e for e in elegidas if e["tipo"] == tipo]) >= k or len(elegidas) >= n:
                return
            if t["id"] not in ids:
                ids.add(t["id"])
                elegidas.append({"tipo": tipo, **t})

    if modo == "sesion":
        tomar(random.sample(maduras, len(maduras)), 1, "intercalada")
        tomar(debiles, 1, "debil")
    else:
        tomar(random.sample(recientes, len(recientes)), 2, "corto")
        tomar(antiguas[:max(5, len(antiguas) // 5)], 2, "largo")
        tomar(debiles, 1, "debil")
        tomar(random.sample(maduras, len(maduras)), n, "corto")
    etiquetas = {"corto": "de los últimos días", "largo": "de lo más antiguo", "debil": "a punto de olvidarse",
                 "intercalada": "de otro tema"}
    out = []
    for t in elegidas[:n]:
        dias = (ahora - t["creada"]) / DIA
        out.append({"id": t["id"], "frente": t["frente"], "reverso": t["reverso"], "idioma": t["idioma"],
                    "area": t["area"], "tema": t["tema"], "tipo": t["tipo"], "etiqueta": etiquetas[t["tipo"]],
                    "edad_dias": round(dias, 1)})
    return out


def pulso_hecho_hoy(usuario):
    return bool(fila("SELECT 1 FROM actividad WHERE usuario=? AND tipo='pulso' AND fecha>?", (usuario, inicio_hoy())))


def registrar_pulso(usuario, bien, total, modo="diario"):
    ejecutar("INSERT INTO actividad(usuario,tipo,valor,detalle,fecha) VALUES(?,?,?,?,?)",
             (usuario, "pulso" if modo == "diario" else "pulso_sesion", bien / total if total else None,
              json.dumps({"bien": bien, "total": total}), time.time()))


# ------------------------------------------------------------- largo plazo
EDADES = [(0, 7, "<1 sem"), (7, 30, "1-4 sem"), (30, 90, "1-3 meses"), (90, 180, "3-6 meses"),
          (180, 365, "6-12 meses"), (365, 99999, "+1 año")]


def largo_plazo(usuario):
    rows = filas("""SELECT r.nota, r.fecha, r.dias, t.creada, t.frente, t.tema FROM repaso r JOIN tarjeta t ON t.id=r.tarjeta
                    WHERE r.usuario=? AND r.dias >= 1""", (usuario,))
    curva = []
    for a, b, et in EDADES:
        sel = [r for r in rows if a <= (r["fecha"] - r["creada"]) / DIA < b]
        curva.append({"edad": et, "n": len(sel),
                      "retencion": sum(1 for r in sel if r["nota"] > 1) / len(sel) if sel else None})
    bien = [r for r in rows if r["nota"] > 1]
    mas_viejo = max(bien, key=lambda r: r["fecha"] - r["creada"], default=None)
    pul = filas("SELECT valor, fecha FROM actividad WHERE usuario=? AND tipo='pulso' AND fecha>? ORDER BY fecha",
                (usuario, time.time() - 30 * DIA))
    corto = filas("""SELECT r.nota FROM repaso r WHERE r.usuario=? AND r.dias BETWEEN 0.5 AND 2.5 AND r.fecha>?""",
                  (usuario, time.time() - 30 * DIA))
    chq = filas("""SELECT a.valor, a.fecha, av.visto FROM actividad a LEFT JOIN avance av
                   ON av.usuario=a.usuario AND av.tema=a.tema WHERE a.usuario=? AND a.tipo='chequeo_tema'""", (usuario,))
    chq_viejos = [c for c in chq if c["visto"] and c["fecha"] - c["visto"] > 30 * DIA]
    return {
        "curva_edad": curva,
        "recuerdo_mas_antiguo": {"dias": round((mas_viejo["fecha"] - mas_viejo["creada"]) / DIA),
                                 "frente": mas_viejo["frente"][:140]} if mas_viejo else None,
        "pulso_30": [{"fecha": p["fecha"], "valor": p["valor"]} for p in pul],
        "pulso_media": sum(p["valor"] for p in pul if p["valor"] is not None) / len(pul) if pul else None,
        "retencion_1dia": sum(1 for r in corto if r["nota"] > 1) / len(corto) if corto else None,
        "n_1dia": len(corto),
        "chequeo_temas_viejos": sum(c["valor"] for c in chq_viejos) / len(chq_viejos) if chq_viejos else None,
        "n_chequeo_viejos": len(chq_viejos)}


# ------------------------------------------------------- plan adaptativo
_cache = {}


def plan_adaptativo(usuario, perfil):
    """Decide cómo debe ser la sesión de hoy a partir de los datos."""
    c = _cache.get(usuario)
    if c and time.time() - c[0] < 600:
        return c[1]
    d = an.analitica(usuario)
    lp = largo_plazo(usuario)
    base_n = int(perfil.get("nuevos_dia", 3))
    n, ajustes = base_n, []
    ahora = time.time()
    rep14 = filas("SELECT nota FROM repaso WHERE usuario=? AND fecha>? AND retenibilidad IS NOT NULL",
                  (usuario, ahora - 14 * DIA))
    ret14 = sum(1 for r in rep14 if r["nota"] > 1) / len(rep14) if len(rep14) >= 30 else None
    pendientes = fila("""SELECT COUNT(*) n FROM tarjeta WHERE usuario=? AND suspendida=0 AND estabilidad IS NOT NULL
                         AND vence<=?""", (usuario, ahora))["n"]
    if ret14 is not None and ret14 < 0.8:
        n = max(1, n - 1)
        ajustes.append(f"Hoy {n} tema(s) nuevo(s) en vez de {base_n}: tu retención de 14 días es {ret14:.0%} "
                       "(por debajo de 80 %). Primero fijar, luego avanzar.")
    elif ret14 is not None and ret14 > 0.94 and pendientes < 30:
        n = base_n + 1
        ajustes.append(f"Hoy {n} temas nuevos (uno más): recuerdas el {ret14:.0%} y no tienes repasos atrasados.")
    if pendientes > 120:
        n = max(1, n - 1)
        ajustes.append(f"Tienes {pendientes} repasos atrasados: hoy empieza por Repasar; un tema nuevo menos.")
    # cuántos temas nuevos caben de verdad en tu día, con los minutos que te cuesta cada uno
    rit = aa.ritmo(usuario)
    if rit["medido"]:
        caben = max(1, int(float(perfil.get("minutos_dia") or 60) * aa.FRACCION_NUEVO // rit["min_por_tema"]))
        if n > caben:
            ajustes.append(f"Hoy {caben} tema(s) nuevo(s) y no {n}: a tu ritmo real (~{rit['min_por_tema']} min por tema "
                           f"con quiz y práctica) es lo que cabe en tus {perfil.get('minutos_dia')} min sin dejar de repasar.")
            n = caben
    import dominio
    necesita, nombres = dominio.necesidad_diaria(usuario, perfil)
    if necesita > n + 0.2:
        ajustes.append(f"Tus metas con plazo ({', '.join(nombres)}) piden ~{necesita:.1f} temas nuevos por día y hoy "
                       f"caben {n}. Para llegar a tiempo: más minutos al día, un plazo más largo, o «Ubícame» para "
                       "saltar lo que ya sabes. Los temas de esas metas van primero.")
    metas = cur.areas_de_metas(usuario)
    activas = [a for a in cur.areas(usuario).values() if a["id"] in cur.areas_de(usuario) and not a.get("objetivo")
               and cur.peso(a, perfil.get("pesos", {}), usuario, metas) > 0]
    if len(activas) > 5 and n:
        ajustes.append(f"Tienes {len(activas)} áreas recibiendo temas nuevos y hoy caben {n}: a cada una le toca un tema "
                       f"cada ~{round(len(activas) / n)} días. En 🔭 Horizonte puedes enfocarte en 2-3 y dejar el resto "
                       "en mantenimiento (siguen sus repasos).")
    recuperar = [{**t, "motivo": "el chequeo o el pulso mostraron que lo olvidaste"} for t in olvidados_recientes(usuario)]
    if recuperar:
        ajustes.append(f"Recupera primero {len(recuperar)} tema(s) que el chequeo o el pulso mostraron olvidados.")
    ya = {t["id"] for t in recuperar}
    no_entendidas = [t for t in aa.partes_no_entendidas(usuario) if t["id"] not in ya][:max(0, 3 - len(recuperar))]
    if no_entendidas:
        ajustes.append(f"Vuelve a {len(no_entendidas)} lección(es) con partes que marcaste «no lo entendí»: "
                       "ábrelas y pide «🔄 Explícamelo de otra forma».")
        recuperar += no_entendidas
        ya |= {t["id"] for t in no_entendidas}
    requisitos = [t for t in aa.requisitos_olvidados(usuario) if t["id"] not in ya][:max(0, 3 - len(recuperar))]
    if requisitos:
        ajustes.append("Refresca antes " + ", ".join(f"«{t['t']}»" for t in requisitos) + ": es requisito de lo que "
                       "estás por estudiar y se te está olvidando (la causa más común de no entender lo nuevo).")
        recuperar += requisitos
    fmt = aa.formato(usuario)
    if fmt["recomendado"] == "esencial" and fmt["razon"]:
        ajustes.append(fmt["razon"] + " (Se cambia arriba de cada lección.)")
    fr = [f for f in d["franjas"] if f["repasos"] >= 20 and f["retencion"] is not None]
    mejor = max(fr, key=lambda f: f["retencion"]) if len(fr) >= 2 else None
    if mejor:
        ajustes.append(f"Tu mejor franja es la {mejor['franja']} ({mejor['retencion']:.0%}): haz ahí lo nuevo y difícil.")
    med = d["sesiones"]["mediana"]
    bloque = 50 if med >= 45 else 25
    metodo = None
    for e in d["eficacia"]:
        if e["con"] is not None and e["sin"] is not None and e["n_con"] >= 20 and e["n_sin"] >= 20 \
                and e["con"] - e["sin"] >= 0.04:
            metodo = e["metodo"]
            ajustes.append(f"{e['metodo']} te hace recordar {e['con'] - e['sin']:.0%} más: úsalo en cada tema nuevo de hoy.")
            break
    if lp["pulso_media"] is not None and lp["pulso_media"] < 0.6:
        ajustes.append("Tu pulso diario está bajo: antes de cada tema nuevo, repasa 5 min el anterior.")
    # texto que leen las lecciones y el tutor para adaptarse
    notas = []
    if recuperar:
        notas.append("debe recuperar o reforzar: " + ", ".join(f"{t['t']} ({t['motivo']})" for t in recuperar[:4]))
    if fmt["recomendado"] == "esencial":
        notas.append("no alcanza a terminar las lecciones largas: ve al grano, lo esencial primero")
    if metodo:
        notas.append(f"le funciona especialmente bien: {metodo.lower()}")
    debiles = [x["t"] for x in d["olvidando"][:4]]
    if debiles:
        notas.append("temas que se le están olvidando: " + ", ".join(debiles))
    if mejor:
        notas.append(f"aprende mejor en la {mejor['franja']}")
    plan = {"nuevos": n, "base": base_n, "ajustes": ajustes, "recuperar": recuperar, "bloque": bloque,
            "mejor_franja": mejor["franja"] if mejor else None, "metodo": metodo, "pendientes": pendientes,
            "adaptacion": "; ".join(notas)}
    _cache[usuario] = (time.time(), plan)
    return plan


def invalidar(usuario):
    _cache.pop(usuario, None)


def olvidados_recientes(usuario):
    """Temas fallados en el último chequeo o en pulsos de 14 días, que no se
    han vuelto a estudiar después."""
    desde = time.time() - 14 * DIA
    fallos = filas("""SELECT tema, MAX(fecha) f FROM actividad WHERE usuario=? AND fecha>? AND tema IS NOT NULL
                      AND tipo='chequeo_tema' AND valor=0 GROUP BY tema""", (usuario, desde))
    fallos += filas("""SELECT t.tema, MAX(r.fecha) f FROM repaso r JOIN tarjeta t ON t.id=r.tarjeta
                       WHERE r.usuario=? AND r.fecha>? AND r.nota=1 AND r.origen IN ('pulso','chequeo')
                       AND t.tema IS NOT NULL GROUP BY t.tema""", (usuario, desde))
    out, vistos = [], set()
    for f in sorted(fallos, key=lambda x: -x["f"]):
        if f["tema"] in vistos:
            continue
        vistos.add(f["tema"])
        despues = fila("""SELECT 1 FROM actividad WHERE usuario=? AND tema=? AND fecha>? AND tipo IN ('quiz','leccion')""",
                       (usuario, f["tema"], f["f"]))
        t = cur.tema(f["tema"], usuario)
        if t and not despues:
            out.append({"id": t["id"], "t": t["t"], "area": t["area"]})
    return out[:3]


# ------------------------------------------------------- plan del día
def plan_del_dia(usuario, perfil, congelar=True):
    """Los temas de hoy quedan fijos al primer cálculo del día (así «terminé
    lo de hoy» tiene sentido); las sesiones extra se agregan al final."""
    clave = f"plan:{usuario}:{hoy_clave()}"
    plan = kv_get(clave)
    if plan is not None and not (plan["temas"] or plan["extra"] or plan["recuperar"]):
        plan = None   # un plan vacío (sin áreas activas aún) no se congela
    if plan is None:
        adapt = plan_adaptativo(usuario, perfil)
        temas = [t["id"] for t in cur.recomendar(usuario, perfil, adapt["nuevos"])]
        plan = {"recuperar": [t["id"] for t in adapt["recuperar"]], "temas": temas, "extra": [],
                "motivos": {t["id"]: t.get("motivo", "") for t in adapt["recuperar"]}}
        if congelar:
            kv_set(clave, plan)
    return plan


def agregar_sesion(usuario, perfil, cantidad):
    plan = plan_del_dia(usuario, perfil)
    ya = set(plan["temas"] + plan["extra"] + plan["recuperar"])
    nuevos = [t["id"] for t in cur.recomendar(usuario, perfil, cantidad, excluir=ya)]
    plan["extra"] += nuevos
    kv_set(f"plan:{usuario}:{hoy_clave()}", plan)
    return nuevos


# ------------------------------------------- cambios en la forma de aprender
def instantanea(usuario, guardar=True):
    d = an.analitica(usuario)
    lp = largo_plazo(usuario)
    tot = sum(m["min"] for m in d["metodos"]) or 1
    fr = [f for f in d["franjas"] if f["repasos"] >= 20 and f["retencion"] is not None]
    datos = {
        "retencion": d["resultados"]["repaso"], "quiz": d["resultados"]["quiz"], "feynman": d["resultados"]["feynman"],
        "apuntes": d["resultados"]["apuntes"], "seg_tarjeta": d["seg_por_tarjeta"],
        "sesion_min": d["sesiones"]["mediana"], "sesiones_semana": d["sesiones"]["por_semana"],
        "hora_inicio": d["sesiones"]["hora_tipica"], "minutos_30": d["minutos_30"],
        "mejor_franja": max(fr, key=lambda f: f["retencion"])["franja"] if len(fr) >= 2 else None,
        "metodos": {m["id"]: round(m["min"] / tot, 3) for m in d["metodos"]},
        "pulso": lp["pulso_media"], "ret_1dia": lp["retencion_1dia"],
        "ret_largo": next((c["retencion"] for c in reversed(lp["curva_edad"]) if c["retencion"] is not None and c["n"] >= 10), None),
        "dias_activos_14": d["dias_activos_14"],
        "niveles": {x["id"]: x["nivel"] for x in niveles(usuario)["areas"]}}
    if guardar:
        ejecutar("INSERT OR REPLACE INTO instantanea(usuario,semana,datos,creada) VALUES(?,?,?,?)",
                 (usuario, an.clave_semana(), json.dumps(datos), time.time()))
    return datos


NOMBRES = {"retencion": ("Retención en repasos", "%"), "ret_1dia": ("Recuerdo a 1-2 días", "%"),
           "ret_largo": ("Recuerdo a largo plazo", "%"), "pulso": ("Pulso diario", "%"), "quiz": ("Quizzes", "%"),
           "feynman": ("Explicaciones Feynman", "%"), "seg_tarjeta": ("Segundos por tarjeta", "s"),
           "sesion_min": ("Duración de sesión", "min"), "sesiones_semana": ("Sesiones por semana", ""),
           "minutos_30": ("Minutos en 30 días", "min"), "dias_activos_14": ("Días activos de 14", "")}


def cambios(usuario):
    """Compara tu forma de aprender ahora con hace ~4 y ~12 semanas."""
    hist = filas("SELECT semana, datos, creada FROM instantanea WHERE usuario=? ORDER BY creada", (usuario,))
    ahora_d = instantanea(usuario, guardar=False)
    def cerca(semanas):
        objetivo = time.time() - semanas * 7 * DIA
        cand = [h for h in hist if h["creada"] <= objetivo + 3 * DIA]
        return json.loads(cand[-1]["datos"]) | {"_semana": cand[-1]["semana"]} if cand else None
    hace4, hace12 = cerca(4), cerca(12)
    filas_ = []
    for k, (nom, u) in NOMBRES.items():
        filas_.append({"clave": k, "nombre": nom, "unidad": u, "ahora": ahora_d.get(k),
                       "hace4": hace4.get(k) if hace4 else None, "hace12": hace12.get(k) if hace12 else None})
    notas = []
    ref = hace4 or hace12
    if ref:
        for f in filas_:
            a, b = f["ahora"], f["hace4"] if hace4 else f["hace12"]
            if a is None or b is None:
                continue
            if f["unidad"] == "%" and abs(a - b) >= 0.05:
                notas.append(f"{f['nombre']}: {b:.0%} → {a:.0%} ({'mejor' if a > b else 'peor'}).")
            elif f["unidad"] in ("min", "s", "") and b and abs(a - b) / max(abs(b), 1) >= 0.25:
                notas.append(f"{f['nombre']}: {b:g} → {a:g}{(' ' + f['unidad']) if f['unidad'] else ''}.")
        if ref.get("mejor_franja") and ahora_d.get("mejor_franja") and ref["mejor_franja"] != ahora_d["mejor_franja"]:
            notas.append(f"Tu mejor franja cambió de la {ref['mejor_franja']} a la {ahora_d['mejor_franja']}: "
                         "ajusta tu horario de estudio.")
        mref, mnow = ref.get("metodos", {}), ahora_d.get("metodos", {})
        for m in set(mref) | set(mnow):
            if abs(mnow.get(m, 0) - mref.get(m, 0)) >= 0.15:
                notas.append(f"Ahora dedicas {mnow.get(m, 0):.0%} del tiempo a {an.METODOS.get(m, m).split(' ', 1)[-1].lower()} "
                             f"(antes {mref.get(m, 0):.0%}).")
    return {"filas": filas_, "notas": notas, "ahora_mejor_franja": ahora_d.get("mejor_franja"),
            "hace4_semana": hace4.get("_semana") if hace4 else None, "hace12_semana": hace12.get("_semana") if hace12 else None,
            "historial": [{"semana": h["semana"], **json.loads(h["datos"])} for h in hist[-26:]]}


# --------------------------------------------------------------- reportes
DICCIONARIO = [
    ("perfil", "Tu perfil: situación, metas, estilo, prioridad de cada área, ritmo diario.",
     "La IA lo lee en cada lección, corrección y tutor; decide qué temas te tocan."),
    ("avance", "Estado de cada tema (nuevo, visto, dominado, probado), mejores puntajes de quiz y Feynman.",
     "Calcula el dominio de módulos y áreas, desbloquea módulos y elige lo siguiente."),
    ("tarjeta", "Tus tarjetas de repaso con su estabilidad y dificultad (FSRS) y cuándo vencen.",
     "Programa cada repaso justo antes de olvidar; estima qué estás olvidando."),
    ("repaso", "Cada repaso: nota (1-4), segundos, probabilidad predicha, días desde el anterior, origen.",
     "Retención real, curva del olvido, mejor hora, pulso, recuerdo a largo plazo."),
    ("actividad", "Eventos: minutos por método y hora, lecciones, quizzes, Feynman, apuntes, pruebas, chequeos.",
     "Panel «Cómo aprendes», sesiones, racha, plan adaptativo."),
    ("leccion", "Lecciones generadas (texto, ejercicios, fuentes). Compartidas entre cuentas.",
     "Se reutilizan; no se escriben dos veces."),
    ("cuaderno", "Tus apuntes a mano (PNG + trazos) y su transcripción y evaluación.",
     "Evaluación de apuntes, tarjetas propuestas, puntajes."),
    ("tarea", "Tareas de práctica creadas en Repasar (tema, dificultad, ejercicios con pistas y soluciones).",
     "Practicar lo que se te olvida; sus entregas se corrigen como las de las lecciones."),
    ("chat", "Conversaciones con el tutor.", "Contexto del tutor en el mismo hilo."),
    ("entrega", "Tus soluciones a los ejercicios de práctica (texto, foto o cuaderno), por ejercicio y versión, con su corrección.",
     "Corrección por la IA, historial de versiones, puntaje de práctica en el panel."),
    ("objetivo / area_extra", "Tus objetivos y las rutas que la IA armó para ellos.",
     "Progreso por objetivo; da prioridad a sus módulos al elegir temas."),
    ("chequeo", "Chequeos semanales: preguntas, respuestas, resultado e informe del coach.",
     "Detecta olvidos (vuelven al repaso), evalúa el largo plazo, alimenta el plan adaptativo."),
    ("instantanea", "Foto semanal de tu forma de aprender (retención, horarios, métodos, sesiones).",
     "Muestra cómo cambia tu forma de aprender con el tiempo."),
    ("codigo_ejercicio / codigo_intento", "Ejercicios de código de la práctica (enunciado, casos) y tus intentos: tu código, cuántos casos pasó y si viste la solución.",
     "Verificación objetiva (el código se ejecuta); métrica «ejercicios resueltos sin ver la solución»."),
    ("prueba_diferida", "Pruebas diferidas (a los 3, 14 y 45 días de dominar un tema): sus preguntas, tus respuestas y el resultado.",
     "Estado de dominio 5 «domina» y la métrica de pruebas diferidas aprobadas."),
    ("nota", "Notas sobre ti guardadas por Hermes o por ti.", "Contexto adicional para Hermes."),
    ("noticia / sintesis", "Noticias descargadas y su análisis (no son datos personales).",
     "Pestaña Noticias."),
]
TABLAS_USUARIO = ["perfil", "avance", "tarjeta", "repaso", "actividad", "cuaderno", "entrega", "tarea", "chat", "objetivo", "area_extra",
                  "chequeo", "instantanea", "nota", "codigo_ejercicio", "codigo_intento", "prueba_diferida"]



# ------------------------------------------------------------------ series y calibración para el reporte
SEMANAS_REPORTE = 12


def limpiar_titulos(texto):
    """Los modelos a veces escriben «## ## Título» (el prompt enumeraba los títulos en una sola línea): se deja uno."""
    return re.sub(r"(?m)^(#{1,6})[ \t]+#{1,6}[ \t]+", r"\1 ", texto or "")


def series_reporte(usuario, semanas=SEMANAS_REPORTE):
    """Lo que dibuja el reporte, desde los datos crudos (no desde las fotos diarias de `metrica_valor`, que son nuevas):
    minutos por día (calendario de actividad), minutos y retención por semana. Cada lista trae también sus fechas."""
    hoy = datetime.now().date()
    dias_n = semanas * 7
    lunes = hoy - timedelta(days=hoy.weekday())
    inicio = lunes - timedelta(weeks=semanas - 1)
    t0 = datetime.combine(inicio, datetime.min.time()).timestamp()
    dia_de = lambda ts: (datetime.fromtimestamp(ts - 4 * 3600)).date()   # la madrugada cuenta para el día anterior  # noqa: E731
    minutos = {}
    for e in filas("SELECT ts, valor FROM evento WHERE usuario=? AND tipo='tiempo' AND ts>=? AND valor>0", (usuario, t0)):
        minutos[dia_de(e["ts"])] = minutos.get(dia_de(e["ts"]), 0) + e["valor"] / 60
    activos = {dia_de(e["ts"]) for e in filas(
        "SELECT ts FROM evento WHERE usuario=? AND ts>=? AND tipo IN ('tiempo','repaso','lectura','quiz','prueba','practica','entrega','apunte','leccion','chequeo_tema','pulso')",
        (usuario, t0))}
    dias = []
    for k in range(dias_n):
        d = inicio + timedelta(days=k)
        if d > hoy:
            break
        dias.append({"fecha": d.isoformat(), "min": round(minutos.get(d, 0), 1), "activo": d in activos or minutos.get(d, 0) > 0})
    sem = []
    for k in range(semanas):
        a = inicio + timedelta(weeks=k)
        ds = [x for x in dias if a.isoformat() <= x["fecha"] < (a + timedelta(days=7)).isoformat()]
        ta = datetime.combine(a, datetime.min.time()).timestamp()
        rp = filas("SELECT nota FROM repaso WHERE usuario=? AND fecha>=? AND fecha<?", (usuario, ta, ta + 7 * 86400))
        sem.append({"desde": a.isoformat(), "min": round(sum(x["min"] for x in ds)), "dias_activos": sum(1 for x in ds if x["activo"]),
                    "repasos": len(rp), "retencion": round(sum(1 for r in rp if (r["nota"] or 0) >= 2) / len(rp), 3) if len(rp) >= 5 else None})
    return {"dias": dias, "semanas": sem}


NIVELES_CONFIANZA = {"adivino": 0.3, "dudo": 0.6, "seguro": 0.9}


def calibracion(usuario, dias=90):
    """¿Tu seguridad coincide con tu acierto? Brier de las respuestas con confianza declarada (0 = perfecto; 0,25 = decir
    siempre «50 %»), la sobreconfianza (seguridad media menos acierto medio) y el acierto real por nivel declarado."""
    desde = time.time() - dias * 86400
    rows = filas("SELECT valor, detalle FROM actividad WHERE usuario=? AND tipo='calibracion' AND fecha>=? AND valor IS NOT NULL",
                 (usuario, desde))
    pares = []
    for r in rows:
        try:
            p = float(json.loads(r["detalle"] or "{}").get("p"))
        except (TypeError, ValueError):
            continue
        pares.append((p, 1.0 if r["valor"] >= 0.5 else 0.0))
    if not pares:
        return {"n": 0, "niveles": [], "brier": None, "sobreconfianza": None}
    niveles = []
    for nombre, p in NIVELES_CONFIANZA.items():
        g = [a for q, a in pares if abs(q - p) < 1e-6]
        niveles.append({"nivel": nombre, "p": p, "n": len(g), "acierto": round(sum(g) / len(g), 3) if g else None})
    return {"n": len(pares), "niveles": niveles, "brier": round(sum((p - a) ** 2 for p, a in pares) / len(pares), 3),
            "sobreconfianza": round(sum(p for p, _ in pares) / len(pares) - sum(a for _, a in pares) / len(pares), 3)}



# ------------------------------------------------------------------ tablero: metas con fecha estimada, dominio en el tiempo
def _primeras_fechas(usuario):
    """Cuándo se dominó y cuándo se exploró por primera vez cada tema. `avance.actualizado` no sirve para esto: cambia con
    cada repetición de un quiz o cada nueva marca, y un tema dominado en septiembre y repasado hoy parecería progreso de hoy.
    Se usa el historial de actividad (el primer quiz ≥ umbral; el primer rastro de estudio) y solo si no hay se cae a `avance`."""
    dom = {r["tema"]: r["t"] for r in filas(
        "SELECT tema, MIN(fecha) t FROM actividad WHERE usuario=? AND tipo='quiz' AND valor>=? AND tema IS NOT NULL GROUP BY tema",
        (usuario, cur.UMBRAL_DOMINIO))}
    exp = {r["tema"]: r["t"] for r in filas(
        "SELECT tema, MIN(fecha) t FROM actividad WHERE usuario=? AND tema IS NOT NULL "
        "AND tipo IN ('quiz','leccion','lectura','practica','feynman','prueba') GROUP BY tema", (usuario,))}
    return dom, exp


def _fechas_dominio(usuario):
    """{tema: fecha del primer dominio} de los temas dominados ESTUDIANDO (los «probados» en una prueba de nivel no cuentan:
    costaron casi nada e inflarían el ritmo, igual que en `aa.ritmo`)."""
    dom, _ = _primeras_fechas(usuario)
    return {r["tema"]: dom.get(r["tema"]) or r["actualizado"] or 0 for r in filas(
        "SELECT tema, actualizado FROM avance WHERE usuario=? AND estado='dominado'", (usuario,))}


def _ritmo_temas(usuario, dias):
    """Temas dominados estudiando por semana en los últimos `dias` (el ritmo real, con las semanas en blanco incluidas)."""
    desde = time.time() - dias * 86400
    return sum(1 for t in _fechas_dominio(usuario).values() if t > desde) / (dias / 7)


def _semanas_con_avance(usuario, semanas=8):
    """En cuántas de las últimas semanas se dominó al menos un tema: un ritmo hecho de una sola racha no es un ritmo."""
    desde = time.time() - semanas * 7 * 86400
    return len({int((t - desde) // (7 * 86400)) for t in _fechas_dominio(usuario).values() if t > desde})


def _fecha_logro(faltan, ritmo_sem, hoy=None):
    hoy = hoy or datetime.now().date()
    if faltan <= 0:
        return hoy
    if ritmo_sem <= 0:
        return None
    return hoy + timedelta(days=math.ceil(faltan / ritmo_sem * 7 - 1e-9))   # si falta algo, no es hoy


def proyeccion_metas(usuario):
    """Para cada meta activa: avance, temas que faltan y la fecha estimada en que se completaría a tu ritmo real.
    Da un rango (ritmo de las últimas 2 semanas, de 4 y de 8: el más rápido y el más lento) y dice cuánta confianza
    merece: con menos de 3 temas dominados en 8 semanas es una cifra frágil y se rotula así."""
    r2, r4, r8 = _ritmo_temas(usuario, 14), _ritmo_temas(usuario, 28), _ritmo_temas(usuario, 56)
    base = r4 if r4 > 0 else r8
    min_tema = aa.ritmo(usuario)["min_por_tema"]
    out = []
    for o in filas("SELECT * FROM objetivo WHERE usuario=? AND estado='activo' ORDER BY id", (usuario,)):
        e = cur.estado_objetivo(usuario, o)
        faltan = e["temas_total"] - e["temas_hechos"]
        rs = [x for x in (r2, r4, r8) if x > 0]
        optim, pesim = (max(rs), min(rs)) if rs else (0, 0)
        f_base, f_op, f_pe = _fecha_logro(faltan, base), _fecha_logro(faltan, optim), _fecha_logro(faltan, pesim)
        dominados_8, sem_av = round(r8 * 8), _semanas_con_avance(usuario)
        out.append({"id": e["id"], "titulo": e["titulo"], "progreso": e["progreso"], "temas_total": e["temas_total"],
                    "temas_hechos": e["temas_hechos"], "faltan": faltan, "ritmo_semana": round(base, 2),
                    "fecha": f_base.isoformat() if f_base else None, "pronto": f_op.isoformat() if f_op else None,
                    "tarde": f_pe.isoformat() if f_pe else None,
                    "confianza": "alta" if dominados_8 >= 8 and sem_av >= 4 else "media" if dominados_8 >= 3 and sem_av >= 2 else "baja",
                    "semanas_con_avance": sem_av,
                    "para_12_meses": {"temas_semana": round(faltan / 52, 1), "min_semana": round(faltan / 52 * min_tema),
                                      "min_por_tema": min_tema},
                    "nota": ("Sin temas dominados en las últimas semanas: no hay ritmo para proyectar una fecha." if not rs else
                             f"A {base:.1f} temas dominados estudiando por semana (últimas 4 semanas; avanzaste en {sem_av} de las últimas 8).")})
    return out


def dominio_en_el_tiempo(usuario, semanas=SEMANAS_REPORTE):
    """Temas dominados y explorados acumulados al final de cada semana, por la fecha de su PRIMER dominio / primera exploración
    (no por la última vez que se tocaron)."""
    hoy = datetime.now().date()
    lunes = hoy - timedelta(days=hoy.weekday())
    inicio = lunes - timedelta(weeks=semanas - 1)
    dom, exp = _primeras_fechas(usuario)
    fechas_dom, fechas_exp = [], []
    for r in filas("SELECT tema, estado, actualizado, visto FROM avance WHERE usuario=?", (usuario,)):
        if r["estado"] in ("dominado", "probado"):
            fechas_dom.append(dom.get(r["tema"]) or r["actualizado"] or 0)
        if r["estado"] in ("visto", "dominado", "probado"):
            fechas_exp.append(min([x for x in (exp.get(r["tema"]), r["visto"]) if x] or [r["actualizado"] or 0]))
    out = []
    for k in range(semanas):
        fin = datetime.combine(inicio + timedelta(weeks=k + 1), datetime.min.time()).timestamp()
        out.append({"hasta": (inicio + timedelta(weeks=k + 1) - timedelta(days=1)).isoformat(),
                    "dominados": sum(1 for t in fechas_dom if t < fin), "explorados": sum(1 for t in fechas_exp if t < fin)})
    return out


def tablero(usuario, perfil):
    d = an.analitica(usuario)
    lp = largo_plazo(usuario)
    plan = plan_adaptativo(usuario, perfil)
    return {"generado": time.time(), "series": series_reporte(usuario), "dominio_tiempo": dominio_en_el_tiempo(usuario),
            "metas": proyeccion_metas(usuario), "calibracion": calibracion(usuario), "estados": estados.estados_persona(usuario),
            "curva_edad": lp["curva_edad"], "analitica": {k: d[k] for k in ("minutos_30", "dias_activos_14")},
            "resultados": d["resultados"], "pendientes": plan["pendientes"]}



def semaforos(d, plan, calib, dominio):
    """Los cinco indicadores del resumen ejecutivo (reporte en pantalla y resumen semanal): estado «ok / atencion / riesgo / nd»,
    siempre con su palabra y su umbral. Una sola fuente de verdad para la web y para el mensaje del celular."""
    def nivel(v, ok, at, mayor=True):
        if v is None:
            return "nd"
        return "ok" if (v >= ok if mayor else v <= ok) else "atencion" if (v >= at if mayor else v <= at) else "riesgo"
    ret, pend, dias = d["resultados"].get("repaso"), (plan or {}).get("pendientes"), d["dias_activos_14"]
    dom, exp = dominio["dominados"], dominio["explorados"]
    cal_n = calib["n"]
    return [
        {"id": "constancia", "nombre": "Constancia", "valor": f"{dias}/14 días", "estado": nivel(dias, 10, 6),
         "lectura": "días activos en 2 semanas", "tip": "Verde desde 10 días; ámbar de 6 a 9; rojo con menos de 6."},
        {"id": "retencion", "nombre": "Retención en repasos", "valor": "—" if ret is None else f"{round(ret * 100)}%", "estado": nivel(ret, 0.85, 0.7),
         "lectura": "de lo repasado se recordó", "tip": "Verde desde 85 %; ámbar de 70 a 84 %; rojo por debajo."},
        {"id": "atrasados", "nombre": "Repasos atrasados", "valor": "—" if pend is None else str(pend), "estado": "nd" if pend is None else nivel(pend, 20, 50, False),
         "lectura": "tarjetas vencidas", "tip": "Verde hasta 20; ámbar hasta 50; rojo con más."},
        {"id": "dominado", "nombre": "Dominado vs. explorado", "valor": f"{dom}/{exp}", "estado": "nd" if exp < 5 else nivel(dom / exp, 0.5, 0.25),
         "lectura": "temas dominados de los que abriste", "tip": "Abrir un tema no es dominarlo. Verde desde la mitad dominada."},
        {"id": "calibracion", "nombre": "Calibración de tu seguridad", "valor": "—" if calib["brier"] is None else f"{calib['brier']:.2f}".replace(".", ","),
         "estado": "nd" if cal_n < 10 else nivel(calib["brier"], 0.15, 0.25, False),
         "lectura": (f"{cal_n} de 10 respuestas con confianza" if cal_n < 10 else "tiendes a creer que sabes más" if calib["sobreconfianza"] > 0.08
                     else "sabes más de lo que crees" if calib["sobreconfianza"] < -0.08 else "tu seguridad coincide con tu acierto"),
         "tip": "Brier: 0 es perfecto y 0,25 equivale a decir siempre «50 %». Verde por debajo de 0,15."},
    ]


ICONO_SEMAFORO = {"ok": "✔", "atencion": "▲", "riesgo": "✖", "nd": "…"}
PALABRA_SEMAFORO = {"ok": "Bien", "atencion": "Atención", "riesgo": "Riesgo", "nd": "Sin datos aún"}


def resumen_semanal(usuario, perfil, hoy=None):
    """Texto corto (sin IA) del resumen ejecutivo de la semana, para el celular: semáforos, tiempo frente a la semana anterior,
    metas con fecha estimada y un siguiente paso. Lo recoge el cron semanal de Hermes y lo entrega a tu Telegram."""
    r = datos_reporte(usuario, perfil)
    s = r["series"]["semanas"]
    esta, previa = s[-1], (s[-2] if len(s) > 1 else None)
    hoy = hoy or datetime.now().date()
    lunes = hoy - timedelta(days=hoy.weekday())
    meses = ("ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic")
    f = lambda d_: f"{d_.day} {meses[d_.month - 1]}"  # noqa: E731
    L = [f"📊 Tu semana en la Academia ({f(lunes)} – {f(lunes + timedelta(days=6))})", ""]
    for x in r["semaforos"]:
        L.append(f"{ICONO_SEMAFORO[x['estado']]} {x['nombre']}: " + (f"{x['valor']} — {PALABRA_SEMAFORO[x['estado']].lower()} ({x['lectura']})"
                                                                  if x["valor"] != "—" else f"sin datos aún ({x['lectura']})"))
    delta = ""
    if previa is not None and (previa["min"] or esta["min"]):
        dif = esta["min"] - previa["min"]
        delta = f" ({'+' if dif >= 0 else ''}{dif} min frente a la semana anterior)"
    L += ["", f"⏱️ Esta semana: {esta['min']} min en {esta['dias_activos']} días{delta}."]
    metas = proyeccion_metas(usuario)
    if metas:
        L += ["", "🎯 Metas:"]
        for m in metas:
            if m["fecha"]:
                a = (datetime.fromisoformat(m["fecha"]).date() - hoy).days / 365
                cuando = "a este ritmo, más de 5 años" if a > 5 else "a este ritmo, hacia " + datetime.fromisoformat(m["fecha"]).strftime("%m/%Y")
            else:
                cuando = "sin ritmo con el que proyectar una fecha"
            L.append(f"• {m['titulo'] if len(m['titulo']) <= 50 else m['titulo'][:49] + '…'}: {round(m['progreso'] * 100)} % ({m['faltan']} temas faltan) — {cuando} · confianza {m['confianza']}.")
    if r["necesidades"]:
        L += ["", "👉 Lo primero: " + r["necesidades"][0]]
    L += ["", "Todo sale de tus datos; las fechas son estimaciones, no promesas."]
    return "\n".join(L) + "\n"


def kpi_reporte(d):
    """Cifras con las que se escribió un análisis: sirven para avisar cuando el texto ya no describe la realidad."""
    return {"minutos_30": d["minutos_30"], "dias_activos_14": d["dias_activos_14"]}


def _informe_ia(usuario, d):
    """El análisis guardado, con los títulos arreglados, su antigüedad y si las cifras de hoy se alejaron de las de entonces."""
    r = kv_get(f"reporte_ia:{usuario}")
    if not r:
        return None
    r = dict(r, texto=limpiar_titulos(r.get("texto")))
    r["dias"] = max(0, int((time.time() - (r.get("fecha") or 0)) // 86400))
    antes, ahora = r.get("kpi"), kpi_reporte(d)
    cambio = False
    if antes:
        cambio = any(abs((ahora[k] or 0) - (antes.get(k) or 0)) > max(30 if k == "minutos_30" else 3, 0.5 * (antes.get(k) or 0))
                     for k in ahora)
    r["desactualizado"] = r["dias"] >= 7 or cambio
    r["motivo"] = (f"se escribió hace {r['dias']} días" if r["dias"] >= 7 else "") + (
        (" y " if r["dias"] >= 7 else "") + "tus cifras cambiaron mucho desde entonces" if cambio else "")
    return r


def datos_reporte(usuario, perfil):
    d = an.analitica(usuario)
    lp = largo_plazo(usuario)
    plan = plan_adaptativo(usuario, perfil)
    mias = cur.areas_de(usuario)
    mapa = [a for a in cur.mapa(usuario) if a["id"] in mias]
    conteos = []
    for nombre, que, uso in DICCIONARIO:
        n = None
        tabla = nombre.split(" / ")[0]
        if tabla in TABLAS_USUARIO:
            n = fila(f"SELECT COUNT(*) n FROM {tabla} WHERE usuario=?", (usuario,))["n"]
        conteos.append({"tabla": nombre, "que": que, "uso": uso, "filas": n})
    pesos = perfil.get("pesos", {})
    necesidades = []
    for a in mapa:
        w = pesos.get(a["id"], 0)
        if w >= 2 and a["dominio"] < 0.1:
            necesidades.append(f"{a['nombre']}: prioridad {w} pero dominio {a['dominio']:.0%}. Empieza su ruta o haz su prueba de nivel.")
    if d["olvidando"]:
        necesidades.append("Temas que se te están olvidando: " + ", ".join(x["t"] for x in d["olvidando"][:5]) + ".")
    if plan["pendientes"] > 50:
        necesidades.append(f"{plan['pendientes']} repasos atrasados.")
    if d["dias_activos_14"] < 7:
        necesidades.append(f"Constancia: {d['dias_activos_14']} de 14 días activos.")
    for o in filas("SELECT * FROM objetivo WHERE usuario=? AND estado='activo'", (usuario,)):
        e = cur.estado_objetivo(usuario, o)
        faltan = [p for p in e["pasos"] if p["estado"] != "completo"]
        necesidades.append(f"Objetivo «{e['titulo']}»: {e['progreso']:.0%}; faltan {len(faltan)} módulos "
                           f"({e['temas_total'] - e['temas_hechos']} temas).")
    areas = sorted(({"nombre": a["nombre"], "dominio": a["dominio"], "grupo": a["grupo"],
                     "dominados": sum(1 for m in a["modulos"] for t in m["temas"] if t["dominio"] >= 0.8),
                     "temas": sum(len(m["temas"]) for m in a["modulos"])} for a in mapa), key=lambda x: -x["dominio"])
    calib = calibracion(usuario)
    dominio = {"dominados": sum(a["dominados"] for a in areas), "temas": sum(a["temas"] for a in areas),
               "explorados": fila("SELECT COUNT(*) n FROM avance WHERE usuario=? AND estado IN ('visto','dominado','probado')", (usuario,))["n"]}
    return {"generado": time.time(), "usuario": usuario, "perfil": {k: perfil.get(k) for k in ("nombre", "situacion", "metas", "estilo")},
            "analitica": d, "largo_plazo": lp, "plan": plan, "cambios": cambios(usuario), "areas": areas,
            "necesidades": necesidades, "diccionario": conteos,
            "chequeos": an.historial(usuario)[:12],
            "informe_ia": _informe_ia(usuario, d), "niveles": niveles(usuario),
            "series": series_reporte(usuario), "calibracion": calib, "dominio": dominio,
            "semaforos": semaforos(d, plan, calib, dominio)}


def reporte_markdown(r):
    d, lp = r["analitica"], r["largo_plazo"]
    pct = lambda x: "—" if x is None else f"{x:.0%}"  # noqa: E731
    L = [f"# Reporte de desarrollo — {r['perfil'].get('nombre') or r['usuario']}",
         f"Generado: {datetime.fromtimestamp(r['generado']):%Y-%m-%d %H:%M}", "",
         "## Resumen", f"- Minutos (30 días): {d['minutos_30']} · días activos (14): {d['dias_activos_14']}",
         f"- Retención en repasos (30 d): {pct(d['resultados']['repaso'])} · recuerdo a 1-2 días: {pct(lp['retencion_1dia'])} "
         f"· pulso diario: {pct(lp['pulso_media'])}",
         f"- Recuerdo verificado más antiguo: {lp['recuerdo_mas_antiguo']['dias']} días" if lp["recuerdo_mas_antiguo"] else
         "- Recuerdo verificado más antiguo: aún sin datos", "",
         "## Desarrollo por área"] + [f"- {a['nombre']}: {a['dominio']:.0%} ({a['dominados']}/{a['temas']} temas)"
                                      for a in r["areas"]] + [
         "", "## Nivel profesional por área"] + [f"- {x['nombre']}: {x['etiqueta']}" for x in r["niveles"]["areas"] if x["nivel"] or x.get("examen")] + [
         "", f"## Nivel frente al mercado de hoy ({datetime.now():%Y})"] + [
         f"- {x['nombre']}: según el currículo {x['etiqueta']}; según lo que piden hoy {x['mercado']['etiqueta']} "
         f"({x['mercado']['progreso_siguiente']:.0%} hacia {x['mercado']['rol_siguiente'] or 'el máximo'}). "
         f"Brechas: {'; '.join(b['competencia'] for b in x['mercado']['brechas'][:4]) or 'ninguna'}. "
         f"Fuera del currículo: {'; '.join(b['competencia'] for b in x['mercado']['fuera_del_curriculo'][:3]) or 'nada'}. "
         f"Cambios en 5 años: {'; '.join(x['mercado']['cambios_5_anios'][:3])}"
         for x in r["niveles"]["areas"] if x.get("mercado")] + [
         f"- Meta «{m['titulo']}»: {m['etiqueta']}" for m in r["niveles"]["metas"]] + [
         "", "## Corto plazo", f"- Pulso diario medio (30 d): {pct(lp['pulso_media'])}",
         f"- Recuerdo a 1-2 días: {pct(lp['retencion_1dia'])} ({lp['n_1dia']} repasos)",
         "", "## Largo plazo (retención según la edad del conocimiento)"] + [
         f"- {c['edad']}: {pct(c['retencion'])} ({c['n']} repasos)" for c in lp["curva_edad"]] + [
         f"- Temas de hace más de 1 mes en chequeos: {pct(lp['chequeo_temas_viejos'])} ({lp['n_chequeo_viejos']})",
         "", "## Cómo aprendes"] + [f"- {m['nombre']}: {m['min']} min ({m['usos']} veces)" for m in d["metodos"]] + [
         f"- Sesión típica: {d['sesiones']['mediana']} min · {d['sesiones']['por_semana']} sesiones/semana"] + [
         f"- {f['franja'].capitalize()}: {pct(f['retencion'])} recordado ({f['repasos']} repasos)" for f in d["franjas"]] + [
         "", "## Cómo lees (30 días)", f"- Velocidad en español: {d['lectura']['wpm_base']} palabras/min"
         + ("" if d["lectura"]["propia"] else " (estimada, aún sin datos propios)"),
         f"- Lecturas terminadas: {d['lectura']['completas']}/{d['lectura']['sesiones']}"] + [
         f"- {v['nombre']}: {v['valor'] if v['valor'] is not None else '—'} {v['unidad']} ({v['min']} min)" for v in d["lectura"]["velocidades"]] + [
         f"- {m['nombre']}: {m['completas']}/{m['sesiones']} terminadas · "
         f"{'—' if m['avance_10min'] is None else str(m['avance_10min']) + ' % del texto cada 10 min'}" for m in d["lectura"]["metodos"]] + [
         "", "## Cómo ha cambiado tu forma de aprender"] + (
         [f"- {n}" for n in r["cambios"]["notas"]] or ["- Aún no hay suficientes semanas para comparar."]) + [
         "", "## Necesidades"] + ([f"- {n}" for n in r["necesidades"]] or ["- Nada urgente."]) + [
         "", "## Recomendaciones"] + [f"- {c}" for c in d["consejos"]] + [f"- {a}" for a in r["plan"]["ajustes"]] + [
         "", "## Qué datos se guardan y cómo se usan", "| Dato | Qué es | Para qué se usa | Registros |",
         "|---|---|---|---|"] + [f"| {x['tabla']} | {x['que']} | {x['uso']} | {x['filas'] if x['filas'] is not None else '—'} |"
                                for x in r["diccionario"]]
    if r.get("informe_ia"):
        L += ["", "## Análisis de la IA", r["informe_ia"]["texto"]]
    return "\n".join(L) + "\n"


def exportar_zip(usuario, carpeta_cuaderno):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        todo = {}
        for t in TABLAS_USUARIO:
            rows = filas(f"SELECT * FROM {t} WHERE usuario=?", (usuario,))
            todo[t] = rows
            if rows:
                s = io.StringIO()
                w = csv.DictWriter(s, fieldnames=list(rows[0].keys()))
                w.writeheader()
                w.writerows(rows)
                z.writestr(f"csv/{t}.csv", s.getvalue())
        temas = {r["tema"] for r in todo["avance"]} | {r["tema"] for r in todo["tarjeta"] if r["tema"]}
        todo["leccion"] = [r for r in filas("SELECT * FROM leccion WHERE usuario=?", (usuario,)) if r["tema"] in temas]
        z.writestr("datos.json", json.dumps(todo, ensure_ascii=False, indent=1, default=str))
        for n in todo["cuaderno"]:
            p = Path(n["imagen"] or "")
            if p.is_file() and carpeta_cuaderno in p.parents:
                z.write(p, f"cuaderno/{n['id']}.png")
        for e in todo["entrega"]:
            p = Path(e["imagen"] or "")
            if e["tipo"] == "imagen" and p.is_file():
                z.write(p, f"entregas/{e['id']}-ej{e['ejercicio']}-v{e['version']}{p.suffix}")
        z.writestr("LEEME.md", "# Tus datos de la Academia\n\nExportado el "
                   f"{datetime.now():%Y-%m-%d %H:%M} para {usuario}.\n\n- `datos.json`: todo en un archivo.\n"
                   "- `csv/`: una tabla por archivo (ábrelo en Excel/LibreOffice). Fechas en segundos Unix.\n"
                   "- `cuaderno/`: tus apuntes a mano en PNG.\n\n## Qué es cada tabla\n\n"
                   + "\n".join(f"- **{t}** — {q} Uso: {u}" for t, q, u in DICCIONARIO) + "\n")
    return buf.getvalue()


# ------------------------------------------------ nivel profesional por área
UMBRAL_NIVEL = 0.7   # dominio medio que debe tener cada nivel para darlo por alcanzado
PROFESIONAL = [
    ("Aprendiz", "Aún sin las bases del área"),
    ("Técnico", "Bases sólidas: nivel técnico / bachillerato avanzado"),
    ("Tecnólogo · universitario", "Nivel de estudiante universitario intermedio o tecnólogo"),
    ("Profesional junior", "Lo que domina un recién egresado"),
    ("Profesional senior · especialista", "Nivel de especialista con experiencia"),
    ("Experto · referente", "Domina la frontera del área"),
]


def _nivel_de(modulos, avs, idioma=False):
    """modulos: lista de dicts del currículo. Devuelve nivel alcanzado 0-5,
    dominio por nivel y progreso hacia el siguiente."""
    por_nivel = {}
    for m in modulos:
        por_nivel.setdefault(m["nivel"], []).extend(cur.dominio_tema(avs.get(t["id"])) for t in m["temas_obj"])
    dom = {k: sum(v) / len(v) for k, v in por_nivel.items() if v}
    alcanzado = 0
    for k in range(1, 6):
        if k not in dom:
            continue
        if dom[k] >= UMBRAL_NIVEL:
            alcanzado = k
        else:
            break
    sig = next((k for k in range(alcanzado + 1, 6) if k in dom), None)
    out = {"nivel": alcanzado, "por_nivel": {k: round(v, 3) for k, v in dom.items()},
           "siguiente": sig, "progreso_siguiente": round(dom[sig] / UMBRAL_NIVEL, 3) if sig else 1.0}
    if idioma:   # idiomas: nombre del examen del último módulo dominado (HSK 2, N4, B1…)
        hechos = [m for m in sorted(modulos, key=lambda m: m["nivel"])
                  if m["temas_obj"] and sum(cur.dominio_tema(avs.get(t["id"])) for t in m["temas_obj"]) / len(m["temas_obj"]) >= UMBRAL_NIVEL]
        out["examen"] = hechos[-1]["t"] if hechos else None
    out["etiqueta"], out["explicacion"] = PROFESIONAL[alcanzado]
    if sig:
        out["proximo"] = PROFESIONAL[sig][0]
    if idioma:
        primero = min(modulos, key=lambda m: m["nivel"])["t"] if modulos else ""
        out["etiqueta"] = out["examen"] or "Sin verificar"
        out["explicacion"] = (f"Nivel verificado en la app (examen de referencia)" if out["examen"]
                              else f"Aún no verificado: haz la prueba de nivel de «{primero}» si ya lo sabes")
        siguiente = next((m for m in sorted(modulos, key=lambda m: m["nivel"])
                          if not out["examen"] or m["nivel"] > (sig or 0) - 1), None)
        out["proximo"] = siguiente["t"] if siguiente and siguiente["t"] != out["examen"] else out.get("proximo")
    return out


def niveles(usuario):
    import mercado
    avs = cur.avances(usuario)
    areas_ = []
    mias = cur.areas_de(usuario)
    for a in cur.areas(usuario).values():
        if a.get("objetivo") or a["id"] not in mias:   # solo las áreas de esta persona
            continue
        n = _nivel_de(a["modulos"], avs, a.get("grupo") == "Idiomas")
        # nivel frente a lo que el mercado pide HOY (referente renovado cada mes con búsqueda web)
        n["mercado"] = None if a.get("grupo") == "Idiomas" else mercado.evaluar(usuario, a["id"], avs)
        areas_.append({"id": a["id"], "nombre": a["nombre"], "icono": a.get("icono"), "grupo": a.get("grupo"),
                       "color": a.get("color"), **n})
    metas = []
    for o in filas("SELECT * FROM objetivo WHERE usuario=? AND estado='activo'", (usuario,)):
        plan = json.loads(o["plan"] or "{}")
        refs = cur.cierre_prerrequisitos(plan.get("modulos", []) + plan.get("extra", []), usuario)
        mods = [m for m in (cur.modulo(r, usuario) for r in refs) if m]
        metas.append({"id": o["id"], "titulo": o["titulo"], **_nivel_de(mods, avs)})
    return {"areas": areas_, "metas": metas, "escala": [{"nivel": i, "etiqueta": e, "explicacion": x}
                                                         for i, (e, x) in enumerate(PROFESIONAL)]}


def actualizar_niveles(usuario):
    """Registra subidas/bajadas de nivel (corre en la actualización diaria y
    tras cada chequeo): quedan en el historial."""
    actual = niveles(usuario)
    previo = kv_get(f"niveles:{usuario}") or {}
    nuevo, cambios_ = {}, []
    for x in actual["areas"] + [dict(m, id=f"meta{m['id']}", nombre=m["titulo"]) for m in actual["metas"]]:
        clave = x["id"]
        valor = [x["nivel"], x.get("examen")]
        nuevo[clave] = valor
        antes = previo.get(clave)
        if antes is not None and antes != valor:
            cambios_.append(x)
            ejecutar("INSERT INTO actividad(usuario,tipo,area,valor,detalle,fecha) VALUES(?,?,?,?,?,?)",
                     (usuario, "nivel", None if clave.startswith("meta") else clave, x["nivel"],
                      json.dumps({"id": clave, "nombre": x["nombre"], "de": antes[0], "a": x["nivel"],
                                  "etiqueta": x["etiqueta"], "examen": x.get("examen"),
                                  "examen_antes": antes[1]}, ensure_ascii=False), time.time()))
    kv_set(f"niveles:{usuario}", nuevo)
    return cambios_


def historial_niveles(usuario, n=30):
    out = []
    for r in filas("SELECT detalle, fecha FROM actividad WHERE usuario=? AND tipo='nivel' ORDER BY id DESC LIMIT ?",
                   (usuario, n)):
        d = json.loads(r["detalle"])
        d["fecha"] = r["fecha"]
        out.append(d)
    return out


def reiniciar_plan_si_no_empezo(usuario):
    """Al cambiar prioridades: rehace el plan de hoy si todavía no estudiaste nada de él."""
    clave = f"plan:{usuario}:{hoy_clave()}"
    plan = kv_get(clave)
    if not plan:
        return
    ids = plan["temas"] + plan["extra"] + plan["recuperar"]
    hecho = any(fila("SELECT 1 FROM avance WHERE usuario=? AND tema=? AND visto>=?", (usuario, t, inicio_hoy()))
                for t in ids)
    if not hecho:
        ejecutar("DELETE FROM kv WHERE k=?", (clave,))
        invalidar(usuario)
