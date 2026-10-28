"""Motor adaptativo: decide QUÉ estudiar, CUÁNTO y DE QUÉ FORMA para cada persona, con sus datos.

Hay más conocimiento del que cabe en una vida, así que la Academia optimiza «aprendizaje por minuto»:

- Dominio vivo: el dominio de un tema decae con el olvido real (retenibilidad FSRS de sus tarjetas). Un tema
  «dominado» hace 4 meses y olvidado no cuenta igual que uno fresco.
- Refuerzo de requisitos: si lo que vas a estudiar se apoya en algo que se te está olvidando, eso va primero
  (es la causa más común de no entender un tema nuevo).
- Lectura adaptativa por partes: cada parte de la lección termina con «¿lo entendiste?»; lo que no quedó claro se
  explica de otra forma (más simple, con un ejemplo o en un esquema) y vuelve al plan.
- Diagnóstico previo (pretest): unas preguntas antes de leer; si ya lo sabes, te ahorras la lectura.
- Ritmo real: minutos que de verdad te cuesta cada tema, para no planear más de lo que cabe en tu día.
- Horizonte: cuánto falta para cada nivel profesional a tu ritmo, repartido vs. enfocado.
- Formato: si las lecciones completas no se terminan, se recomienda el modo esencial.
"""
import json
import re
import statistics
import time

import curriculo as cur
import fsrs
import ia
import lectura
from base import ejecutar, fila, filas, kv_get, kv_set, registrar

DIA = 86400
MIN_TEMA_INICIAL = 45      # minutos por tema mientras no hay datos propios (lección + quiz + práctica)
FRACCION_NUEVO = 0.65      # parte del tiempo diario que va a temas nuevos (el resto: repaso y práctica)
UMBRAL_OLVIDO = 0.7        # retenibilidad por debajo de la cual un requisito «se está olvidando»
ESTADOS_PARTE = {"sabido": 1.0, "dudoso": 0.5, "no": 0.0}

ejecutar("""CREATE TABLE IF NOT EXISTS parte_estado (
  usuario TEXT, tema TEXT, parte INTEGER, estado TEXT, segundos REAL, fecha REAL,
  PRIMARY KEY (usuario, tema, parte))""")
ejecutar("""CREATE TABLE IF NOT EXISTS leccion_rapida (
  usuario TEXT, tema TEXT, texto TEXT, version INTEGER, fecha REAL, PRIMARY KEY (usuario, tema))""")
ejecutar("""CREATE TABLE IF NOT EXISTS reexplicacion (
  id INTEGER PRIMARY KEY AUTOINCREMENT, usuario TEXT, tema TEXT, parte INTEGER, estilo TEXT,
  duda TEXT, texto TEXT, fecha REAL)""")


# ------------------------------------------------------------ dominio vivo
def memoria_por_tema(usuario, ahora=None):
    """tema → retenibilidad media ACTUAL de sus tarjetas ya repasadas (None si no tiene)."""
    ahora = ahora or time.time()
    acc = {}
    for t in filas("""SELECT tema, estabilidad, ultimo FROM tarjeta WHERE usuario=? AND suspendida=0
                      AND estabilidad IS NOT NULL AND tema IS NOT NULL""", (usuario,)):
        r = fsrs.retenibilidad((ahora - (t["ultimo"] or ahora)) / DIA, t["estabilidad"])
        acc.setdefault(t["tema"], []).append(r)
    return {k: sum(v) / len(v) for k, v in acc.items()}


def dominio_vivo(av, memoria):
    """Dominio 0..1 corregido por el olvido: con memoria 1 vale lo mismo; con memoria 0 queda en el 40 %
    (lo que se olvida se reaprende mucho más rápido que lo nuevo)."""
    d = cur.dominio_tema(av)
    return d if memoria is None else d * (0.4 + 0.6 * memoria)


# ------------------------------------------------------- refuerzo de requisitos
def requisitos_olvidados(usuario, n=2):
    """Temas ya aprendidos de los módulos que son requisito directo de lo que estás por estudiar (frontera de
    tus áreas activas) y que se te están olvidando. Repasarlos antes evita no entender lo nuevo."""
    avs = cur.avances(usuario)
    mem = memoria_por_tema(usuario)
    mias = cur.areas_de(usuario)
    candidatos = {}
    for a in cur.areas(usuario).values():
        if a["id"] not in mias:
            continue
        for m in a["modulos"]:
            if not cur.desbloqueado(m, avs, usuario) or cur.dominio_modulo(m, avs) >= cur.UMBRAL_DOMINIO:
                continue
            for p in m["pre"]:
                pm = cur.modulo(p, usuario)
                if not pm:
                    continue
                for t in pm["temas_obj"]:
                    r = mem.get(t["id"])
                    if r is not None and r < UMBRAL_OLVIDO and cur.dominio_tema(avs.get(t["id"])) >= 0.5:
                        if t["id"] not in candidatos or candidatos[t["id"]][0] > r:
                            candidatos[t["id"]] = (r, t, m["t"])
    out = []
    for r, t, para in sorted(candidatos.values(), key=lambda x: x[0])[:n]:
        out.append({"id": t["id"], "t": t["t"], "area": t["area"],
                    "motivo": f"requisito de «{para}» que se te está olvidando (memoria {r:.0%})"})
    return out


def partes_no_entendidas(usuario, dias=21):
    """Temas con partes marcadas «no lo entendí» que no se han superado después (quiz ≥ 80 %)."""
    desde = time.time() - dias * DIA
    out = []
    for r in filas("""SELECT tema, MAX(fecha) f, COUNT(*) n FROM parte_estado WHERE usuario=? AND estado='no'
                      AND fecha>? GROUP BY tema ORDER BY f DESC""", (usuario, desde)):
        av = fila("SELECT quiz, actualizado FROM avance WHERE usuario=? AND tema=?", (usuario, r["tema"])) or {}
        if (av.get("quiz") or 0) >= cur.UMBRAL_DOMINIO and (av.get("actualizado") or 0) > r["f"]:
            continue
        t = cur.tema(r["tema"], usuario)
        if t:
            out.append({"id": t["id"], "t": t["t"], "area": t["area"],
                        "motivo": f"{r['n']} parte(s) que marcaste «no lo entendí»"})
    return out


# ------------------------------------------------------------------ ritmo real
def ritmo(usuario, dias=60):
    """Minutos reales que te cuesta cada tema nuevo (tiempo de estudio activo / temas aprendidos)."""
    desde = time.time() - dias * DIA
    seg = fila("SELECT IFNULL(SUM(valor),0) s FROM actividad WHERE usuario=? AND tipo='tiempo' AND fecha>?",
               (usuario, desde))["s"]
    # temas aprendidos estudiando (no los probados en una prueba de nivel, que cuestan casi nada)
    aprendidos = 0.0
    for r in filas("""SELECT estado, quiz FROM avance WHERE usuario=? AND actualizado>? AND estado IN ('visto','dominado')""",
                   (usuario, desde)):
        aprendidos += 1.0 if r["estado"] == "dominado" else 0.6
    activos = filas("""SELECT DISTINCT date(fecha,'unixepoch','localtime') d FROM actividad WHERE usuario=?
                       AND tipo='tiempo' AND fecha>?""", (usuario, desde))
    # promedio por día CALENDARIO desde que empezó (los días sin estudiar cuentan como 0: es el ritmo real)
    primero = fila("SELECT MIN(fecha) f FROM actividad WHERE usuario=? AND tipo='tiempo' AND fecha>?",
                   (usuario, desde))["f"] or time.time()
    min_dia_real = seg / 60 / max(1.0, (time.time() - primero) / DIA)
    medido = aprendidos >= 3 and seg >= 3600
    min_tema = max(15, min(240, seg / 60 / aprendidos)) if medido else MIN_TEMA_INICIAL
    return {"min_por_tema": round(min_tema), "medido": medido, "temas": round(aprendidos, 1),
            "minutos": round(seg / 60), "dias_activos": len(activos), "min_dia_real": round(min_dia_real)}


# ------------------------------------------------------------- formato de lectura
def formato(usuario):
    """¿Esta persona termina las lecciones completas? Si no, se le recomienda el modo esencial (y paso a paso)."""
    ses = [s for s in filas("""SELECT avance, segundos, palabras FROM lectura WHERE usuario=? AND metodo='leccion'
                               AND fin>? AND segundos>60""", (usuario, time.time() - 45 * DIA))]
    lar = fila("""SELECT AVG(LENGTH(contenido)) c, COUNT(*) n FROM leccion WHERE usuario=? AND ejercicios IS NOT NULL""",
               (usuario,))
    palabras = (lar["c"] or 0) / 6.2          # ~6,2 caracteres por palabra en español con markdown
    wpm = lectura.wpm_base(usuario)
    min_leccion = round(palabras / wpm) if palabras else None
    avance = statistics.mean(s["avance"] or 0 for s in ses) if ses else None
    preferido = None
    razon = ""
    if avance is not None and len(ses) >= 2 and avance < 0.6:
        preferido = "esencial"
        razon = (f"En tus últimas lecturas llegaste en promedio al {avance:.0%} de la lección: léela paso a paso "
                 "(una parte por sesión, con comprobación) y empieza por la vista previa de 10 min para ver el mapa.")
    elif min_leccion and min_leccion > 45:
        preferido = "esencial"
        razon = (f"Tus lecciones completas toman ~{min_leccion} min a tu velocidad ({wpm} palabras/min): léelas paso "
                 "a paso (una parte por sesión, con comprobación) y empieza por la vista previa de 10 min.")
    return {"recomendado": preferido or "completo", "razon": razon, "min_leccion": min_leccion,
            "avance_medio": round(avance, 2) if avance is not None else None, "wpm": wpm}


# ----------------------------------------------------------------- partes
def guardar_parte(usuario, tid, parte, estado, segundos=None):
    if estado not in ESTADOS_PARTE:
        raise ValueError("estado desconocido")
    ejecutar("""INSERT INTO parte_estado(usuario,tema,parte,estado,segundos,fecha) VALUES(?,?,?,?,?,?)
                ON CONFLICT(usuario,tema,parte) DO UPDATE SET estado=excluded.estado,
                segundos=COALESCE(excluded.segundos, parte_estado.segundos), fecha=excluded.fecha""",
             (usuario, tid, int(parte), estado, segundos, time.time()))
    t = cur.tema(tid, usuario)
    registrar(usuario, "parte", tid, t["area"] if t else None, ESTADOS_PARTE[estado], {"parte": int(parte)})


def partes_de(usuario, tid):
    estados = {r["parte"]: r["estado"] for r in filas(
        "SELECT parte, estado FROM parte_estado WHERE usuario=? AND tema=?", (usuario, tid))}
    reex = filas("""SELECT id, parte, estilo, duda, texto, fecha FROM reexplicacion WHERE usuario=? AND tema=?
                    ORDER BY id""", (usuario, tid))
    rap = rapida_de(usuario, tid)
    return {"estados": estados, "reexplicaciones": reex, "diagnostico": kv_get(f"diag:{usuario}:{tid}"),
            "rapida": rap["texto"] if rap else None}


def texto_parte(contenido, parte):
    """El markdown de «## Parte N · …» hasta el siguiente título de nivel 2."""
    bloques, actual = [], None
    for linea in (contenido or "").splitlines():
        if linea.startswith("## "):
            actual = [linea]
            bloques.append(actual)
        elif actual is not None:
            actual.append(linea)
    partes = [b for b in bloques if b[0][3:].lstrip().lower().startswith("parte ")]
    if 1 <= parte <= len(partes):
        return "\n".join(partes[parte - 1])
    return None


ESTILOS = {
    "simple": ("🪶 Más simple", "Explícala de nuevo MUCHO más simple: sin jerga (o defínela), frases cortas, una analogía "
                               "cotidiana potente, y construye paso a paso desde lo que ya sabe. Nada de relleno."),
    "ejemplo": ("🔧 Con un ejemplo", "Explícala a través de UN ejemplo concreto y realista, resuelto paso a paso con "
                                    "números (o código, o un caso real), diciendo en cada paso qué idea del tema se usa y por qué."),
    "esquema": ("🗺️ En un esquema", "Explícala como un esquema visual en markdown: un mapa de ideas jerárquico, una tabla "
                                   "comparativa o un diagrama de flujo con flechas (→). Cada nodo con una línea de explicación."),
}


def reexplicar(ctx, usuario, perfil, tid, parte, estilo, duda=""):
    import lecciones as lec
    lecc = fila("SELECT contenido FROM leccion WHERE usuario=? AND tema=?", (usuario, tid))
    t = cur.tema(tid, usuario)
    if not lecc or not t:
        raise ValueError("lección no encontrada")
    texto = texto_parte(lecc["contenido"], int(parte))
    if not texto:
        raise ValueError("parte no encontrada")
    nombre, instr = ESTILOS.get(estilo, ESTILOS["simple"])
    ctx.fase(f"Explicando la parte {parte} de otra forma ({nombre})")
    prompt = (f"{lec.texto_perfil(perfil)}\n\nEl estudiante leyó esta parte de la lección «{t['t']}» y NO la entendió "
              f"bien.{(' Su duda: ' + duda.strip()[:600]) if duda and duda.strip() else ''}\n\n{instr}\n\n"
              "Reglas: 250-450 palabras; ve directo a lo que suele trabarse; termina con «👉 Compruébalo:» y UNA "
              "pregunta corta para que verifique si ya lo entendió (con la respuesta oculta en una línea que empiece "
              "por «Respuesta:»). Fórmulas en LaTeX con $...$.\n\n--- PARTE ORIGINAL ---\n" + texto[:9000])
    salida = ctx.chat([{"role": "system", "content": lec.SISTEMA_BASE}, {"role": "user", "content": prompt}],
                      max_tokens=1100, temperatura=0.5)
    ejecutar("""INSERT INTO reexplicacion(usuario,tema,parte,estilo,duda,texto,fecha) VALUES(?,?,?,?,?,?,?)""",
             (usuario, tid, int(parte), estilo, duda or "", salida, time.time()))
    return {"texto": salida, "estilo": estilo, "parte": int(parte)}


# ------------------------------------------------------------- ruta rápida
def _secciones(contenido):
    """[(titulo_h2, texto)] de la lección."""
    out, actual = [], None
    for linea in (contenido or "").splitlines():
        if linea.startswith("## "):
            actual = [linea[3:].strip(), []]
            out.append(actual)
        elif actual is not None:
            actual[1].append(linea)
    return [(t, "\n".join(c)) for t, c in out]


def _recortar_parte(texto, limite=2600):
    """Lo central de una parte para el resumen: intuición y desarrollo enteros hasta el límite, sin «más a fondo»,
    matices ni autoevaluación (eso no es lo esencial)."""
    trozos, saltar = [], False
    for linea in texto.splitlines():
        if linea.startswith("### "):
            saltar = bool(re.search(r"m[aá]s a fondo|matices|comprueba|casos l[ií]mite", linea, re.I))
        if not saltar:
            trozos.append(linea)
    return "\n".join(trozos)[:limite]


def ruta_rapida(ctx, usuario, perfil, tid):
    """Vista previa de 10-15 min de una lección ya escrita: lo esencial de CADA parte, un ejemplo mínimo y las
    fórmulas clave. Es el mapa antes de estudiar a fondo (organizador previo) y el repaso después; no reemplaza la
    lección completa."""
    import lecciones as lec
    lecc = fila("SELECT contenido, version FROM leccion WHERE usuario=? AND tema=? AND completa!=0", (usuario, tid))
    t = cur.tema(tid, usuario)
    if not lecc or not t:
        raise ValueError("la lección aún no está completa")
    secs = _secciones(lecc["contenido"])
    partes = [(ti, tx) for ti, tx in secs if ti.lower().startswith("parte ")]
    objetivos = next((tx for ti, tx in secs if "objetivo" in ti.lower()), "")[:1200]
    encaja = next((tx for ti, tx in secs if "encaja" in ti.lower()), "")[:1500]
    material = "\n\n".join(f"## {ti}\n{_recortar_parte(tx)}" for ti, tx in partes)
    ctx.fase("Escribiendo la ruta rápida (10-15 min de lectura)")
    prompt = (f"{lec.texto_perfil(perfil)}\n\nCondensa esta lección sobre «{t['t']}» en una RUTA RÁPIDA de 900-1300 "
              "palabras (10-15 min de lectura) para alguien que tiene poco tiempo y quiere lo esencial que más rinde.\n"
              "Estructura en markdown:\n"
              "## ⚡ En una frase\n(la idea central)\n"
              "## 🧠 Lo esencial, parte por parte\nUn bloque «### Parte N · título» por CADA parte, con 3-6 viñetas: "
              "solo las ideas que hay que saber (con su porqué, no solo el qué) y la fórmula clave si la hay.\n"
              "## ✍️ Un ejemplo mínimo\n(uno solo, resuelto en pocos pasos)\n"
              "## ⚠️ El error que más se comete\n"
              "## 🔁 Para fijarlo\n3 preguntas de recuperación (sin respuesta) que cubran lo más importante.\n"
              "Empieza DIRECTAMENTE con «## ⚡ En una frase»: sin saludo, sin preámbulo y sin repetir su perfil. "
              "No inventes datos que no estén en la lección. Fórmulas en LaTeX con $...$.\n\n"
              f"--- OBJETIVOS ---\n{objetivos}\n\n--- PARTES (recortadas) ---\n{material[:22000]}\n\n"
              f"--- CÓMO ENCAJA TODO ---\n{encaja}")
    texto = ctx.chat([{"role": "system", "content": lec.SISTEMA_BASE}, {"role": "user", "content": prompt}],
                     max_tokens=2600, temperatura=0.4)
    i = texto.find("## ")
    if i > 0:
        texto = texto[i:]          # sin saludo ni preámbulo, aunque el modelo lo ponga
    ejecutar("""INSERT INTO leccion_rapida(usuario,tema,texto,version,fecha) VALUES(?,?,?,?,?)
                ON CONFLICT(usuario,tema) DO UPDATE SET texto=excluded.texto, version=excluded.version,
                fecha=excluded.fecha""", (usuario, tid, texto, lecc["version"] or 1, time.time()))
    return {"texto": texto}


def rapida_de(usuario, tid):
    r = fila("SELECT texto, version, fecha FROM leccion_rapida WHERE usuario=? AND tema=?", (usuario, tid))
    lecc = fila("SELECT version FROM leccion WHERE usuario=? AND tema=?", (usuario, tid))
    if r and lecc and (lecc["version"] or 1) != r["version"]:
        return None          # la lección se reescribió: la ruta rápida vieja ya no corresponde
    return r


def preparar_rapida(usuario, perfil, tid, prioridad=1):
    """Encola la ruta rápida si hace falta y no está ya en cola. Devuelve el trabajo (o None). Los idiomas no la
    llevan: sus lecciones no van por partes."""
    t = cur.tema(tid, usuario)
    if not t or cur.areas(usuario)[t["area"]].get("idioma"):
        return None
    if rapida_de(usuario, tid) or not fila(
            "SELECT 1 FROM leccion WHERE usuario=? AND tema=? AND completa!=0 AND ejercicios IS NOT NULL", (usuario, tid)):
        return None
    previo = next((x for x in ia.cola.trabajos.values() if x.tipo == "rapida" and x.etiqueta == tid
                   and x.usuario == usuario and x.estado in ("cola", "corriendo", "conflicto")), None)
    if previo:
        if prioridad == 0 and previo.prioridad > 0 and previo.estado == "cola":
            ia.cola.subir(previo)
        return previo
    return ia.nuevo("rapida", lambda ctx: ruta_rapida(ctx, usuario, perfil, tid), prioridad, usuario, tid)


def guardar_diagnostico(usuario, tid, bien, total, flojas, vistas=()):
    """`vistas` = índices de las preguntas del quiz que se usaron antes de leer: después no cuentan en la nota (ya se
    conocían sus respuestas y la inflarían)."""
    previo = kv_get(f"diag:{usuario}:{tid}") or {}
    vistas = sorted(set(previo.get("vistas", [])) | {int(x) for x in vistas if isinstance(x, int)})
    d = {"bien": int(bien), "total": int(total), "flojas": [int(x) for x in flojas][:12], "fecha": time.time(),
         "vistas": vistas}
    kv_set(f"diag:{usuario}:{tid}", d)
    t = cur.tema(tid, usuario)
    registrar(usuario, "diagnostico", tid, t["area"] if t else None, bien / max(1, total), d)
    return d


# ---------------------------------------------------------- ubicación por área
def inferir_requisitos(usuario, ref, todas=False):
    """Superaste la prueba de un módulo avanzado: sus requisitos de la MISMA área se dan por sabidos (solo los
    temas sin empezar). Es lo que permite ubicarte en un área con 3-4 pruebas en vez de una por módulo. Con
    `todas` (ubicarse en una META, que cruza áreas) se infieren también los requisitos de otras áreas."""
    m = cur.modulo(ref, usuario)
    if not m:
        return []
    marcados = []
    for r in cur.cierre_prerrequisitos([ref], usuario):
        pm = cur.modulo(r, usuario)
        if r == ref or not pm or (pm["area"] != m["area"] and not todas):
            continue
        for t in pm["temas_obj"]:
            av = fila("SELECT estado FROM avance WHERE usuario=? AND tema=?", (usuario, t["id"]))
            if not av or av["estado"] == "nuevo":
                cur.marcar(usuario, t["id"], estado="probado", quiz=1.0)
                marcados.append(t["id"])
    registrar(usuario, "ubicacion", None, m["area"], len(marcados), {"ref": ref, "inferidos": len(marcados)})
    return marcados


# ------------------------------------------------------------------ horizonte
def _temas_para_nivel(modulos, avs, mem, nivel):
    """Temas (equivalentes) que faltan para que cada nivel ≤ `nivel` llegue al 70 % de dominio vivo."""
    import adaptacion as ad
    falta = 0.0
    por_nivel = {}
    for m in modulos:
        por_nivel.setdefault(m["nivel"], []).extend(
            dominio_vivo(avs.get(t["id"]), mem.get(t["id"])) for t in m["temas_obj"])
    for k, doms in por_nivel.items():
        if k <= nivel and doms:
            falta += max(0.0, ad.UMBRAL_NIVEL * len(doms) - sum(doms))
    return falta


def horizonte(usuario, perfil, enfoque_n=3):
    """Cuánto falta para cada nivel profesional en cada área, a tu ritmo real, con tu prioridad actual
    (repartido) y si te enfocas en las `enfoque_n` áreas más importantes para ti."""
    import adaptacion as ad
    avs = cur.avances(usuario)
    mem = memoria_por_tema(usuario)
    rit = ritmo(usuario)
    pesos = perfil.get("pesos", {})
    metas = cur.areas_de_metas(usuario)
    minutos_meta = float(perfil.get("minutos_dia") or 60)
    min_real = rit["min_dia_real"] if rit["dias_activos"] >= 7 else None
    areas = []
    for a in cur.areas(usuario).values():
        if a.get("objetivo") or a["id"] not in cur.areas_de(usuario):
            continue
        w = cur.peso(a, pesos, usuario, metas)
        if w <= 0:
            continue
        nv = ad._nivel_de(a["modulos"], avs, a.get("grupo") == "Idiomas")
        niveles_ = []
        for k in range(nv["nivel"] + 1, 6):
            if not any(m["nivel"] == k for m in a["modulos"]):
                continue
            temas = _temas_para_nivel(a["modulos"], avs, mem, k)
            niveles_.append({"nivel": k, "etiqueta": ad.PROFESIONAL[k][0], "temas": round(temas, 1),
                             "horas": round(temas * rit["min_por_tema"] / 60, 1)})
        areas.append({"id": a["id"], "nombre": a["nombre"], "icono": a.get("icono"), "color": a.get("color"),
                      "peso": w, "meta": a["id"] in metas, "nivel": nv["nivel"], "nivel_nombre": nv["etiqueta"],
                      "niveles": niveles_})
    total_w = sum(x["peso"] for x in areas) or 1
    foco = sorted(areas, key=lambda x: (-x["peso"], not x["meta"], x["nombre"]))[:enfoque_n]
    foco_ids = {x["id"] for x in foco}
    foco_w = sum(x["peso"] for x in foco) or 1

    def dias(horas, parte, minutos):
        diario = minutos * FRACCION_NUEVO * parte
        return round(horas * 60 / diario) if diario > 0 else None

    for x in areas:
        for n in x["niveles"]:
            n["dias_repartido"] = dias(n["horas"], x["peso"] / total_w, minutos_meta)
            n["dias_real"] = dias(n["horas"], x["peso"] / total_w, min_real) if min_real else None
            n["dias_enfoque"] = dias(n["horas"], x["peso"] / foco_w, minutos_meta) if x["id"] in foco_ids else None
    # un número que lo resume: cuánto tomaría llevar TODAS tus áreas a profesional junior (nivel 3)
    horas_junior = sum(next((n["horas"] for n in x["niveles"] if n["nivel"] == 3), 0) for x in areas)
    anios_junior = round(horas_junior * 60 / (minutos_meta * FRACCION_NUEVO) / 365, 1) if areas else 0
    consejo = []
    if len(areas) > enfoque_n + 2:
        consejo.append(f"Tienes {len(areas)} áreas recibiendo temas nuevos. Repartir {round(minutos_meta)} min/día entre "
                       f"todas hace que cada una avance muy lento; enfocarte en {enfoque_n} y dejar el resto en "
                       "mantenimiento (prioridad 0: sin temas nuevos, pero sus tarjetas se siguen repasando para no "
                       "olvidar) multiplica la velocidad en lo que más te importa.")
    if min_real is not None and min_real < minutos_meta * 0.6:
        consejo.append(f"Tu meta es {round(minutos_meta)} min/día, pero en las últimas semanas estudiaste en promedio "
                       f"{min_real} min/día. Los plazos «a tu ritmo real» usan ese número: una meta alcanzable que "
                       "cumples vale más que una alta que no.")
    if not rit["medido"]:
        consejo.append(f"Todavía no hay datos suficientes de tu ritmo: se asumen {MIN_TEMA_INICIAL} min por tema. "
                       "Se ajusta solo cuando completes unos temas.")
    return {"areas": areas, "ritmo": rit, "minutos_meta": minutos_meta, "minutos_real": min_real,
            "enfoque": [x["id"] for x in foco], "enfoque_n": enfoque_n, "anios_junior_todo": anios_junior,
            "horas_junior_todo": round(horas_junior), "consejo": consejo, "fraccion_nuevo": FRACCION_NUEVO}


# --------------------------------------------------- aprendizaje fuera de la Academia
ESQUEMA_EXTERNO = {"type": "object", "properties": {"equivalencias": {"type": "array", "items": {
    "type": "object", "properties": {
        "curso": {"type": "string"}, "ref": {"type": "string"},
        "confianza": {"type": "integer", "minimum": 1, "maximum": 3}, "nota": {"type": "string"}},
    "required": ["curso", "ref", "confianza", "nota"]}}}, "required": ["equivalencias"]}


def mapear_externo(ctx, usuario, texto):
    """Cursos, certificados o materias que la persona hizo en otro lado (Coursera, Platzi, DataCamp, la
    universidad…) → módulos de su ruta que probablemente ya sabe. No marca nada: propone una prueba de nivel
    corta por módulo (lo declarado se verifica, no se cree a ciegas)."""
    cat = cur.catalogo_modulos(usuario)
    refs = [r for r, _ in cat]
    esquema = json.loads(json.dumps(ESQUEMA_EXTERNO))
    esquema["properties"]["equivalencias"]["items"]["properties"]["ref"]["enum"] = refs
    ctx.fase("Relacionando lo que estudiaste fuera con tu ruta")
    lista = "\n".join(f"{r} = {d}" for r, d in cat)
    prompt = ("El estudiante cuenta lo que ya estudió fuera de la Academia (cursos en línea, certificados, materias "
              "de la universidad, trabajo). Relaciona cada cosa con los módulos del catálogo que CUBRE en buena parte "
              "(no los que solo toca de pasada). confianza: 3 = lo cubre casi entero, 2 = buena parte, 1 = una parte. "
              "Máximo 25 equivalencias, sin repetir ref. En 'nota', una frase de qué cubre y qué no.\n\n"
              f"Lo que estudió:\n{texto[:6000]}\n\nCatálogo (ref = área › módulo):\n{lista}")
    r = ctx.chat([{"role": "user", "content": prompt}], max_tokens=2500, temperatura=0.2, esquema=esquema)
    vistos, out = set(), []
    for e in r.get("equivalencias", []):
        m = cur.modulo(e["ref"], usuario)
        if not m or e["ref"] in vistos:
            continue
        vistos.add(e["ref"])
        out.append({**e, "modulo": m["t"], "area": cur.modulo_area_nombre(e["ref"], usuario), "nivel": m["nivel"]})
    out.sort(key=lambda x: (-x["confianza"], x["nivel"]))
    guardado = {"texto": texto[:6000], "equivalencias": out, "fecha": time.time()}
    kv_set(f"externo:{usuario}", guardado)
    return guardado


def externo(usuario):
    return kv_get(f"externo:{usuario}")


def reexplicar_trabajo(usuario, perfil, tid, parte, estilo, duda):
    return ia.nuevo("reexplicar", lambda ctx: reexplicar(ctx, usuario, perfil, tid, parte, estilo, duda),
                    0, usuario, tid)
