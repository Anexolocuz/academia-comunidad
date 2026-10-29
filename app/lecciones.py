"""Todo lo que la IA escribe o corrige: lecciones, ejercicios, tarjetas,
corrección de respuestas abiertas, técnica Feynman, prueba de nivel,
apuntes a mano (visión), tutor y planes de objetivos.

Cada función recibe `ctx` (ia.Contexto) y corre dentro de la cola de la IA.
"""
import base64
import json
import re
import time

import curriculo as cur
import ia
from base import ejecutar, fila, filas, kv_get, kv_set

NIVEL_TXT = cur.NIVELES


def texto_perfil(perfil):
    p = perfil or {}
    partes = [f"Estudiante: {p.get('nombre') or 'el usuario'}."]
    if p.get("situacion"):
        partes.append(f"Situación: {p['situacion']}")
    if p.get("metas"):
        partes.append(f"Metas: {p['metas']}")
    if p.get("estilo"):
        partes.append(f"Prefiere: {p['estilo']}")
    if p.get("adaptacion"):
        partes.append(f"Lo que muestran sus datos de aprendizaje: {p['adaptacion']}. Adáptate a esto "
                      "(conecta con lo que olvidó si viene al caso, usa el método que le funciona).")
    # Marcas: la API opcional (nube.py) cambia este bloque por una versión sin nombre; la IA local las quita.
    return "[[PERFIL]]" + " ".join(partes) + "[[/PERFIL]]"


SISTEMA_BASE = (
    "Eres el tutor personal de una academia privada que corre en el PC del estudiante. "
    "Tu objetivo: que cada estudiante alcance SUS metas (las de su perfil, si las da) con bases sólidas "
    "en lo que estudia. "
    "Enseñas con rigor y claridad, en español, usando las técnicas con mejor evidencia: "
    "intuición antes que fórmula, ejemplos resueltos, práctica de recuperación, conexiones entre áreas "
    "y aplicaciones reales (en su vida, su trabajo y sus metas). Escribe fórmulas en LaTeX con $...$ o $$...$$. "
    "Si no estás seguro de un dato, dilo; nunca inventes cifras, fechas, citas ni fuentes.")


def _fuentes_para(t, area):
    """Fuentes de partida de una lección: búsqueda agresiva (verificacion.py) en español, con Wikipedia, .edu y .gov,
    ordenada por fiabilidad y con máximo 2 por dominio."""
    if area.get("grupo") == "Idiomas":
        return []
    import verificacion as vf
    q = f'{t["t"]} {t["d"]}'.strip()
    return vf.buscar_fuentes([q, f'{t["t"]} {area["nombre"]}'], n=6, academicas=False, leer=False)


def contexto_tema(tid, usuario):
    t = cur.tema(tid, usuario)
    if not t:
        raise ValueError(f"tema desconocido: {tid}")
    area = cur.areas(usuario)[t["area"]]
    m = cur.modulo(t["modulo"], usuario)
    return t, area, m


# --------------------------------------------------------------- lección
VERSION_LECCION = 2   # 1 = lección corta de una pasada; 2 = a fondo, escrita por partes con papers
VERSION_MAXIMA = 3    # 3 = máxima profundidad (botón «🔬 Máxima profundidad» de la lección o del módulo)
# Cuánto se extiende cada tipo de lección a fondo
PROFUNDIDAD = {
    VERSION_LECCION: {"partes": (4, 6), "palabras": "800-1200", "tokens": 3000, "web": 3, "papers": 2,
                      "papers_tema": 4, "cierre": "1000-1600", "ejercicios": "5 ejercicios graduados: 2 básicos, 2 intermedios y 1 reto"},
    VERSION_MAXIMA: {"partes": (6, 8), "palabras": "1300-1900", "tokens": 4600, "web": 4, "papers": 3,
                     "papers_tema": 6, "cierre": "1600-2400", "ejercicios": "8 ejercicios graduados: 3 básicos, 3 intermedios y 2 retos"},
}


def _guardar_anterior(previa):
    if previa and previa["completa"] != 0:
        ejecutar("""INSERT INTO leccion_anterior(tema,contenido,ejercicios,fuentes,version,creado,reemplazada,usuario)
                    VALUES(?,?,?,?,?,?,?,?)""", (previa["tema"], previa["contenido"], previa["ejercicios"],
                                                previa["fuentes"], previa["version"] or 1, previa["creado"], time.time(),
                                                previa["usuario"]))


def generar_leccion(ctx, tid, usuario, perfil, forzar=False, maxima=False):
    previa = fila("SELECT * FROM leccion WHERE usuario=? AND tema=?", (usuario, tid))
    t, area, m = contexto_tema(tid, usuario)
    if maxima and previa and (previa["version"] or 1) >= VERSION_MAXIMA and previa["completa"] != 0:
        return {"tema": tid, "ya": True}   # ya está a máxima profundidad
    if previa and not forzar and not maxima and previa["completa"] != 0:
        if previa["ejercicios"] is None:  # quedó a medias (p. ej. se reinició el PC): solo faltan ejercicios
            ctx.fase("Creando ejercicios y tarjetas")
            ej = generar_ejercicios(ctx, t, area, previa["contenido"])
            ejecutar("UPDATE leccion SET ejercicios=? WHERE usuario=? AND tema=?",
                     (json.dumps(ej, ensure_ascii=False), usuario, tid))
        return {"tema": tid, "ya": True}
    _guardar_anterior(previa)
    if area.get("idioma"):
        return _leccion_idioma(ctx, t, area, m, perfil, usuario)
    return _leccion_a_fondo(ctx, t, area, m, perfil, usuario, VERSION_MAXIMA if maxima else VERSION_LECCION)


def _leccion_idioma(ctx, t, area, m, perfil, usuario):
    tid = t["id"]
    vecinos = [x["t"] for x in m["temas_obj"]]
    guia = (
        f"Lección de {area['nombre']} ({area.get('examen', '')}) para hispanohablante, completa y profunda. Estructura en markdown:\n"
        "## 🎯 Qué vas a poder decir/entender\n## 🗣 Pronunciación y escritura (sonidos difíciles para hispanohablantes, "
        "trazos/romanización, tonos o acento si aplica)\n"
        "## 📘 Gramática explicada a fondo: la regla, POR QUÉ funciona así, tablas (conjugaciones, partículas, casos…), "
        "excepciones, y al menos 8 ejemplos (escritura original, romanización, traducción)\n"
        "## 🧩 Vocabulario clave (tabla: palabra | pronunciación | significado | ejemplo), 15-25 palabras, agrupadas por tema\n"
        "## 💬 Diálogo realista (10-14 líneas) con romanización y traducción, y notas sobre las expresiones que usa\n"
        "## 📖 Lectura (8-12 frases) con su traducción debajo\n## 🔍 Matices: registro formal/informal, cuándo NO usar esto\n"
        "## ⚠️ Errores típicos de hispanohablantes\n"
        "## 🏋️ Practica tú (8 ejercicios: traducir, completar, transformar y uno de redactar; soluciones dentro de "
        "<details><summary>Solución</summary>...</details>)\n## 🌏 Nota cultural")
    prompt = (f"Área: {area['nombre']} · Módulo: {m['t']} (nivel {m['nivel']}: {NIVEL_TXT[m['nivel']]})\n"
              f"Tema: **{t['t']}** — {t['d']}\nTemas del módulo, en orden: {', '.join(vecinos)}\n"
              f"{texto_perfil(perfil)}\n\n{guia}\n\nExtensión: 1800-2600 palabras. Ve directo al contenido, sin saludo.")
    ctx.fase("Escribiendo la lección")
    mensajes = [{"role": "system", "content": SISTEMA_BASE}, {"role": "user", "content": prompt}]
    contenido = ctx.chat(mensajes, max_tokens=6000, temperatura=0.5)
    ejecutar("""INSERT INTO leccion(usuario,tema,contenido,ejercicios,fuentes,modelo,creado,version,completa,plan)
                VALUES(?,?,?,NULL,'[]',?,?,?,1,NULL)
                ON CONFLICT(usuario,tema) DO UPDATE SET contenido=excluded.contenido, ejercicios=NULL, fuentes='[]',
                modelo=excluded.modelo, creado=excluded.creado, version=excluded.version, completa=1, plan=NULL""",
             (usuario, tid, contenido, str(ia.MODELO), time.time(), VERSION_LECCION))
    ctx.fase("Creando ejercicios y tarjetas")
    ejercicios = generar_ejercicios(ctx, t, area, contenido, mensajes)
    ejecutar("UPDATE leccion SET ejercicios=? WHERE usuario=? AND tema=?",
             (json.dumps(ejercicios, ensure_ascii=False), usuario, tid))
    return {"tema": tid}


ESQUEMA_PLAN = {"type": "object", "properties": {
    "pregunta_guia": {"type": "string"},
    "prerrequisitos": {"type": "array", "maxItems": 5, "items": {"type": "string"}},
    "objetivos": {"type": "array", "minItems": 4, "maxItems": 7, "items": {"type": "string"}},
    "consulta_cientifica": {"type": "string"},
    "partes": {"type": "array", "minItems": 4, "maxItems": 6, "items": {"type": "object", "properties": {
        "titulo": {"type": "string"},
        "ideas": {"type": "array", "minItems": 3, "maxItems": 7, "items": {"type": "string"}},
        "busqueda": {"type": "string"},
        "busqueda_en": {"type": "string"}},
        "required": ["titulo", "ideas", "busqueda", "busqueda_en"]}}},
    "required": ["pregunta_guia", "prerrequisitos", "objetivos", "consulta_cientifica", "partes"]}


def _fuentes_web(texto, vistas, n):
    import verificacion as vf
    out = []
    for f in vf.buscar_fuentes([texto], n=n + 3, academicas=False, leer=False):
        if f["url"] not in vistas:
            vistas.add(f["url"])
            out.append(f)
    return out[:n]


def _papers(consulta, vistas, n):
    import ciencia
    out = []
    for p in ciencia.buscar(consulta, n + 2):
        k = p["doi"] or p["url"]
        if k and k not in vistas:
            vistas.add(k)
            out.append(p)
    return out[:n]


def limpiar_citas(texto, n_web, n_papers):
    """Quita las citas [n] o [Pn] que apuntan a una fuente que no existe (la IA a veces cita de más): una cita
    falsa da apariencia de respaldo que no tiene. No toca índices de código o matemáticas (`x[3]`, `a[1]`)."""
    def web(m):
        return m.group(0) if int(m.group(1)) <= n_web else ""

    def pap(m):
        return m.group(0) if int(m.group(1)) <= n_papers else ""
    texto = re.sub(r"(?<![\w\)\]])\[(\d{1,3})\]", web, texto)
    return re.sub(r"(?<![\w\)\]])\[P(\d{1,3})\]", pap, texto)


def _bloque(fuentes, papers, w0, p0):
    partes = []
    if fuentes:
        partes.append("Fuentes web (cítalas como [n]):\n" + "\n".join(
            f"[{w0 + i}] {f['titulo']} — {f['url']}\n{f['texto']}" for i, f in enumerate(fuentes)))
    if papers:
        import ciencia
        partes.append("Documentos científicos reales de OpenAlex (cítalos como [Pn] SOLO si de verdad tratan esto; "
                      "usa lo que dice su resumen, sin inventar resultados):\n" + ciencia.bloque_prompt(papers, p0))
    return "\n\n".join(partes)


def _leccion_a_fondo(ctx, t, area, m, perfil, usuario, version=VERSION_LECCION):
    """Lección profunda en 3 pasos dentro de UNA conversación (llama.cpp reusa la caché):
    1) plan: el tema dividido en 4-6 partes con sus ideas concretas;
    2) cada parte escrita aparte, con fuentes web y papers propios (~800-1200 palabras);
    3) cierre: integración, caso integrador, investigación, horizonte y práctica.
    Se guarda tras cada parte (completa=0) para poder leer mientras escribe."""
    P = PROFUNDIDAD[version]
    tid = t["id"]
    vecinos = [x["t"] for x in m["temas_obj"]]
    ctx.fase("Buscando fuentes y documentos científicos")
    vistas_w, vistas_p = set(), set()
    import aportadas
    fuentes = [f for f in aportadas.fuentes_de(usuario, tid) + _fuentes_para(t, area)
               if not (f["url"] in vistas_w or vistas_w.add(f["url"]))]    # las que aportó la persona, primero
    nivel_txt = NIVEL_TXT[m["nivel"]]
    prompt_plan = (
        f"Área: {area['nombre']} · Módulo: {m['t']} (nivel {m['nivel']}: {nivel_txt})\n"
        f"Tema: **{t['t']}** — {t['d']}\nTemas del módulo, en orden: {', '.join(vecinos)}\n{texto_perfil(perfil)}\n\n"
        "Vas a escribir una lección A FONDO sobre este tema, por partes, como un buen capítulo de libro universitario: "
        "que cubra TODAS las partes del tema y permita entender cosas complejas, no solo rascar la superficie. "
        "Primero planéala. Devuelve JSON:\n"
        f"- partes: {P['partes'][0]}-{P['partes'][1]} partes que juntas cubran el tema COMPLETO, de los fundamentos rigurosos a lo avanzado (matices, "
        "casos límite, métodos, origen de la idea si aporta). Cada parte con 'ideas' concretas a desarrollar (afirmaciones, "
        "fórmulas, mecanismos, distinciones; no títulos vagos), 'busqueda' = consulta web corta en español y "
        "'busqueda_en' = consulta académica en inglés (3-7 términos técnicos) para buscar artículos científicos.\n"
        "- objetivos: lo que el estudiante podrá hacer al final (verbos medibles: calcular, demostrar, diseñar, comparar…).\n"
        "- pregunta_guia: la gran pregunta que la lección responde.\n- prerrequisitos: lo que conviene saber antes.\n"
        "- consulta_cientifica: consulta académica en inglés para el tema completo.\n"
        f"Ajusta la profundidad al nivel {m['nivel']} ({nivel_txt}): en Fundamentos, rigor y claridad sin dar nada por "
        "sabido; en niveles altos, formalismo, derivaciones y estado del arte. JSON compacto."
        + ("\n\n" + _bloque(fuentes, [], 1, 1) if fuentes else ""))
    mensajes = [{"role": "system", "content": SISTEMA_BASE}, {"role": "user", "content": prompt_plan}]
    ctx.fase("Planeando la lección a fondo")
    esquema = json.loads(json.dumps(ESQUEMA_PLAN))
    esquema["properties"]["partes"]["minItems"], esquema["properties"]["partes"]["maxItems"] = P["partes"]
    plan = ctx.chat(mensajes, max_tokens=4200 if version >= VERSION_MAXIMA else 3200, temperatura=0.4, esquema=esquema)
    mensajes.append({"role": "assistant", "content": json.dumps(plan, ensure_ascii=False)})
    papers = _papers(plan.get("consulta_cientifica"), vistas_p, P["papers_tema"])
    partes = plan["partes"]
    cabecera = ("## 🎯 Objetivos\n" + "\n".join(f"{i + 1}. {o}" for i, o in enumerate(plan["objetivos"]))
                + "\n\n## 🗺️ Mapa de la lección\n"
                + f"> **Pregunta guía:** {plan['pregunta_guia']}\n\n"
                + (f"**Conviene saber antes:** {'; '.join(plan['prerrequisitos'])}\n\n" if plan["prerrequisitos"] else "")
                + "\n".join(f"{i + 1}. **{p['titulo']}** — {'; '.join(p['ideas'][:4])}" for i, p in enumerate(partes)))
    textos = [cabecera]
    todas_f, todos_p = list(fuentes), list(papers)

    def guardar(completa):
        texto = "\n\n".join(textos)
        if completa:   # solo al cerrar: mientras escribe, las fuentes de las partes siguientes aún no existen
            texto = limpiar_citas(texto, len(todas_f), len(todos_p))
        # papers: al final solo quedan los que la IA de verdad citó ([Pn]); los demás no venían al caso
        lista = ([{"titulo": f["titulo"], "url": f["url"]} for f in todas_f]
                 + [{"titulo": p["titulo"], "url": p["url"], "tipo": "paper", "autores": p["autores"], "anio": p["anio"],
                     "revista": p["revista"], "citas": p["citas"], "abierto": p["abierto"], "n": f"P{i + 1}"}
                    for i, p in enumerate(todos_p) if not completa or re.search(rf"\[P{i + 1}\]", texto)])
        ejecutar("""INSERT INTO leccion(usuario,tema,contenido,ejercicios,fuentes,modelo,creado,version,completa,plan)
                    VALUES(?,?,?,NULL,?,?,?,?,?,?)
                    ON CONFLICT(usuario,tema) DO UPDATE SET contenido=excluded.contenido, ejercicios=NULL,
                    fuentes=excluded.fuentes, modelo=excluded.modelo, creado=excluded.creado,
                    version=excluded.version, completa=excluded.completa, plan=excluded.plan""",
                 (usuario, tid, texto, json.dumps(lista, ensure_ascii=False), str(ia.MODELO), time.time(),
                  version, completa, json.dumps(plan, ensure_ascii=False)))

    guardar(0)
    for i, p in enumerate(partes):
        ctx.fase(f"Buscando fuentes de la parte {i + 1}/{len(partes)}")
        nf = _fuentes_web(f"{p['busqueda']}", vistas_w, P["web"])
        np_ = _papers(p["busqueda_en"], vistas_p, P["papers"])
        w0, p0 = len(todas_f) + 1, len(todos_p) + 1
        todas_f += nf
        todos_p += np_
        extra = _bloque(nf, np_, w0, p0)
        if i == 0 and papers:
            extra = _bloque([], papers, 1, 1) + ("\n\n" + extra if extra else "")
        prompt = (
            f"Escribe ahora la PARTE {i + 1} de {len(partes)}: «{p['titulo']}».\nIdeas que debe desarrollar a fondo: "
            + "; ".join(p["ideas"]) + "\n\nFormato markdown, exactamente así:\n"
            f"## Parte {i + 1} · {p['titulo']}\n### 🧠 Intuición (analogía o imagen mental)\n"
            "### 📘 Desarrollo (definiciones precisas; fórmulas en LaTeX; deriva o justifica paso a paso de dónde sale "
            "cada resultado y POR QUÉ funciona; distingue conceptos parecidos; usa tablas si comparan cosas)\n"
            "### ✍️ Ejemplos resueltos (al menos 2 con datos concretos, el segundo más difícil; muestra cada paso y "
            "comprueba el resultado)\n### ⚠️ Matices, casos límite y errores típicos\n"
            + ("### 🔍 Más a fondo (la demostración o derivación COMPLETA del resultado central; de dónde viene la idea: "
               "quién la desarrolló, qué problema resolvía y cómo evolucionó; y un ejemplo avanzado o aplicación real "
               "de alto nivel, con datos)\n" if version >= VERSION_MAXIMA else "") +
            "### ✅ Comprueba (2 preguntas rápidas; respuesta dentro de <details><summary>Respuesta</summary>...</details>)\n\n"
            f"Extensión: {P['palabras']} palabras. Construye sobre las partes anteriores sin repetirlas. Cita [n] o [Pn] donde "
            "uses una fuente. Sin saludo ni resumen final."
            + (f"\n\n{extra}" if extra else ""))
        mensajes.append({"role": "user", "content": prompt})
        ctx.fase(f"Escribiendo parte {i + 1}/{len(partes)}: {p['titulo'][:50]}")
        texto = ctx.chat(mensajes, max_tokens=P["tokens"], temperatura=0.5)
        mensajes.append({"role": "assistant", "content": texto})
        textos.append(texto)
        guardar(0)
    lista_p = "\n".join(f"[P{i + 1}] {p['autores']} ({p['anio']}). {p['titulo']}. {p['revista']}. {p['url']}"
                        for i, p in enumerate(todos_p))
    lista_w = "\n".join(f"[{i + 1}] {f['titulo']} — {f['url']}" for i, f in enumerate(todas_f))
    prompt_cierre = (
        "Ahora cierra la lección. Formato markdown, exactamente estos títulos:\n"
        "## 🧩 Cómo encaja todo (relaciona las partes entre sí en una tabla o esquema y responde la pregunta guía)\n"
        "## ⚙️ Caso integrador (un problema realista, ligado a las metas y la vida del estudiante, que necesite VARIAS "
        "partes; resuelto paso a paso con datos concretos)\n"
        "## 🔬 Lo que dice la investigación (de los documentos científicos [Pn] que de verdad tratan el tema: qué "
        "estudiaron, qué encontraron según su resumen y qué aporta a la lección; si ninguno aplica, dilo en una frase)\n"
        "## 🔗 Conexiones con otras áreas\n## 🚀 Horizonte (preguntas abiertas y cómo se usa hoy en la frontera; solo lo "
        "respaldado por fuentes o bien establecido)\n"
        f"## 🏋️ Practica tú ({P['ejercicios']}. Cada uno en su párrafo como "
        "«**Ejercicio n (nivel):** enunciado con todos los datos», seguido de "
        "<details><summary>Solución</summary>solución completa paso a paso</details>)\n"
        "## 📚 Fuentes y lecturas (lista las fuentes que citaste con su enlace; los documentos científicos con autores, "
        "año, título y enlace DOI; y como máximo 2 libros o cursos clásicos que estés seguro de que existen)\n\n"
        f"Extensión: {P['cierre']} palabras.\n\nFuentes web disponibles:\n" + (lista_w or "(ninguna)")
        + "\n\nDocumentos científicos disponibles:\n" + (lista_p or "(ninguno)"))
    mensajes.append({"role": "user", "content": prompt_cierre})
    ctx.fase("Escribiendo el cierre: caso integrador, investigación y práctica")
    cierre = ctx.chat(mensajes, max_tokens=6500 if version >= VERSION_MAXIMA else 4500, temperatura=0.5)
    textos.append(cierre)
    guardar(1)
    ctx.fase("Creando ejercicios y tarjetas")
    ejercicios = generar_ejercicios(ctx, t, area, cierre, mensajes)
    ejecutar("UPDATE leccion SET ejercicios=? WHERE usuario=? AND tema=?",
             (json.dumps(ejercicios, ensure_ascii=False), usuario, tid))
    return {"tema": tid}


ESQUEMA_EJERCICIOS = {
    "type": "object",
    "properties": {
        "quiz": {"type": "array", "minItems": 5, "maxItems": 10, "items": {
            "type": "object",
            "properties": {
                "tipo": {"type": "string", "enum": ["opcion", "abierta"]},
                "pregunta": {"type": "string"},
                "opciones": {"type": "array", "items": {"type": "string"}, "maxItems": 4},
                "correcta": {"type": "integer", "minimum": 0, "maximum": 3},
                "explicacion": {"type": "string"}},
            "required": ["tipo", "pregunta", "opciones", "correcta", "explicacion"]}},
        "tarjetas": {"type": "array", "minItems": 5, "maxItems": 18, "items": {
            "type": "object",
            "properties": {"frente": {"type": "string"}, "reverso": {"type": "string"}},
            "required": ["frente", "reverso"]}}},
    "required": ["quiz", "tarjetas"]}


def generar_ejercicios(ctx, t, area, contenido, previos=None):
    idioma = area.get("idioma")
    extra = (f"Las tarjetas de idioma: frente = palabra o frase en {area['nombre']} (escritura original), "
             "reverso = pronunciación/romanización + significado + ejemplo corto." if idioma else
             "Las tarjetas: pregunta concreta en el frente (no 'define X' genérico; mejor '¿por qué...?', "
             "'¿qué pasa si...?', fórmulas, unidades, casos), respuesta corta y precisa al reverso.")
    prompt = (
        f"Con base en TODA esta lección sobre «{t['t']}» (todas sus partes, no solo la última), crea:\n"
        "1) quiz: 8 preguntas que repartan las partes de la lección: 5 de tipo 'opcion' (4 opciones plausibles, "
        "'correcta' = índice 0-3, distractores basados en errores comunes) y 3 de tipo 'abierta' (opciones = [], "
        "correcta = 0) que exijan aplicar, derivar o explicar el porqué, no memorizar. 'explicacion' = por qué es "
        "correcta (para las abiertas: la respuesta modelo).\n"
        f"2) tarjetas: 10 a 16 tarjetas para repetición espaciada que cubran cada parte. {extra}\n"
        "Fórmulas en LaTeX corto entre $...$, sin \\text. Responde solo JSON compacto.")
    if previos:  # misma conversación: llama.cpp reutiliza la caché y no relee la lección
        mensajes = previos + [{"role": "assistant", "content": contenido}, {"role": "user", "content": prompt}]
    else:
        mensajes = [{"role": "system", "content": SISTEMA_BASE},
                    {"role": "user", "content": prompt + "\n\nLECCIÓN:\n" + contenido[:30000]}]
    return ctx.chat(mensajes, max_tokens=4500, temperatura=0.4, esquema=ESQUEMA_EJERCICIOS)


# ------------------------------------------------------- corregir respuestas
ESQUEMA_NOTA = {"type": "object", "properties": {
    "puntaje": {"type": "integer", "minimum": 0, "maximum": 100},
    "bien": {"type": "string"}, "mal": {"type": "string"}, "falto": {"type": "string"},
    "siguiente": {"type": "string"}},
    "required": ["puntaje", "bien", "mal", "falto", "siguiente"]}


def corregir(ctx, tid, usuario, pregunta, modelo_resp, respuesta, modo="abierta"):
    t, area, _ = contexto_tema(tid, usuario)
    if modo == "feynman":
        instr = ("Técnica Feynman: el estudiante explicó el tema con sus palabras como si enseñara a alguien de 12 años, "
                 "siguiendo esta guía: qué es en una frase, por qué funciona, un ejemplo propio, una analogía, dónde se usa "
                 "y un error común. Evalúa: exactitud, claridad, si cubre los objetivos de la lección (abajo), si usa "
                 "analogías propias, si explica el porqué y no solo el qué, y los huecos de comprensión. Sé exigente pero "
                 "motivador; en 'falto' di qué objetivos no cubrió.")
    else:
        instr = "Corrige la respuesta abierta del estudiante comparándola con la respuesta modelo. Acepta formas equivalentes."
    prompt = (f"Tema: {t['t']} ({area['nombre']}).\n{instr}\n\nPregunta: {pregunta}\n"
              f"Respuesta modelo / referencia: {modelo_resp or '(usa tu conocimiento)'}\n"
              f"Respuesta del estudiante: {respuesta}\n\n"
              "Devuelve JSON: puntaje 0-100, bien (qué hizo bien), mal (errores concretos), "
              "falto (qué faltó), siguiente (un consejo accionable). Frases cortas.")
    return ctx.chat([{"role": "system", "content": SISTEMA_BASE}, {"role": "user", "content": prompt}],
                    max_tokens=700, temperatura=0.2, esquema=ESQUEMA_NOTA)


# ------------------------------------------------------------ prueba de nivel
ejecutar("""CREATE TABLE IF NOT EXISTS prueba_nivel (
  id INTEGER PRIMARY KEY AUTOINCREMENT, usuario TEXT, ref TEXT, datos TEXT, respuestas TEXT DEFAULT '{}',
  estado TEXT DEFAULT 'lista', resultado TEXT, creada REAL, terminada REAL)""")   # lista | terminada
APROBAR_PRUEBA = 0.95   # % mínimo para dar por superado el módulo completo
PREGUNTAS_POR_TEMA = 2  # un tema cuenta como sabido solo si acierta todas sus preguntas


def esquema_prueba(n_temas):
    n = n_temas * PREGUNTAS_POR_TEMA
    return {"type": "object", "properties": {"preguntas": {
        "type": "array", "minItems": n, "maxItems": n, "items": {"type": "object", "properties": {
            "tema": {"type": "integer", "minimum": 0, "maximum": n_temas - 1},
            "pregunta": {"type": "string"},
            "opciones": {"type": "array", "minItems": 4, "maxItems": 4, "items": {"type": "string"}},
            "correcta": {"type": "integer", "minimum": 0, "maximum": 3},
            "explicacion": {"type": "string"}},
            "required": ["tema", "pregunta", "opciones", "correcta", "explicacion"]}}},
        "required": ["preguntas"]}


ENFOQUES = ["casos de ingeniería", "situaciones de la vida diaria", "negocios y finanzas", "detección de errores en un razonamiento",
            "comparar dos conceptos parecidos", "predecir qué pasa si cambia un dato", "interpretar un resultado o gráfica descrita",
            "contraejemplos y casos límite", "cálculo con números nuevos", "elegir el método correcto para un problema"]


def prueba_nivel(ctx, ref, usuario):
    """Cada intento trae preguntas NUEVAS: se guardan las ya hechas en este módulo y se le prohíben a la IA,
    con otro enfoque y otra semilla. Si ya pasaste temas del módulo, solo pregunta los que faltan."""
    import random
    m = cur.modulo(ref, usuario)
    area = cur.areas(usuario)[m["area"]]
    avs = cur.avances(usuario)
    todos = m["temas_obj"]
    temas = [t for t in todos if cur.dominio_tema(avs.get(t["id"])) < cur.UMBRAL_DOMINIO] or todos
    clave = f"prueba_hechas:{usuario}:{ref}"
    hechas = kv_get(clave) or []
    enfoques = random.sample(ENFOQUES, 3)
    lista = "\n".join(f"{i}. {t['t']} — {t['d']}" for i, t in enumerate(temas))
    prompt = (f"Prueba de nivel para saltarse el módulo «{m['t']}» de {area['nombre']} si ya se domina.\n"
              f"Temas a evaluar (índice. tema):\n{lista}\n\n"
              f"Crea EXACTAMENTE {PREGUNTAS_POR_TEMA} preguntas de opción múltiple POR CADA TEMA "
              f"({len(temas) * PREGUNTAS_POR_TEMA} en total), en el orden de los temas ('tema' = su índice): una de "
              "comprensión del concepto y otra de aplicación o cálculo. Dificultad media-alta: deben distinguir a quien "
              "realmente domina el tema de quien solo lo vio una vez. 4 opciones plausibles con errores típicos como "
              f"distractores; explicación de 1-2 frases. Para variar, usa sobre todo estos enfoques: {', '.join(enfoques)}. "
              "Cambia el orden de la opción correcta. Fórmulas en LaTeX corto entre $...$. JSON compacto."
              + ("\n\nEstas preguntas YA se usaron en intentos anteriores: NO las repitas ni hagas variantes con los mismos "
                 "datos; pregunta otros aspectos del tema, con otros números y situaciones:\n- "
                 + "\n- ".join(h[:160] for h in hechas[-40:]) if hechas else ""))
    r = ctx.chat([{"role": "system", "content": SISTEMA_BASE}, {"role": "user", "content": prompt}],
                 max_tokens=700 * len(temas) + 600, temperatura=0.85, esquema=esquema_prueba(len(temas)),
                 semilla=random.randint(1, 2 ** 31))
    for p in r["preguntas"]:                       # índice local → índice real del tema en el módulo
        p["tema"] = temas[min(p["tema"], len(temas) - 1)]["i"]
    kv_set(clave, (hechas + [p["pregunta"] for p in r["preguntas"]])[-80:])
    kv_set(f"prueba_temas:{usuario}:{ref}", [t["i"] for t in temas])
    r["temas"] = [{"i": t["i"], "t": t["t"]} for t in temas]
    r["ya_sabidos"] = [t["t"] for t in todos if t not in temas]
    r["intento"] = len(hechas) // max(1, len(temas) * PREGUNTAS_POR_TEMA) + 1
    r["aprobar"] = APROBAR_PRUEBA
    # guardada en la base: se puede cerrar la ventana, cambiar de equipo y retomarla donde iba
    r["id"] = ejecutar("INSERT INTO prueba_nivel(usuario,ref,datos,creada) VALUES(?,?,?,?)",
                       (usuario, ref, json.dumps(r, ensure_ascii=False), time.time())).lastrowid
    return r


# -------------------------------------------------------------------- tutor
def tutor(ctx, usuario, perfil, hilo, mensaje, tid=None, web=False):
    historia = filas("SELECT rol, texto FROM chat WHERE usuario=? AND hilo=? ORDER BY id DESC LIMIT 16",
                     (usuario, hilo))[::-1]
    sistema = SISTEMA_BASE + "\n" + texto_perfil(perfil)
    if tid:
        t, area, m = contexto_tema(tid, usuario)
        sistema += f"\nTema actual: {t['t']} ({area['nombre']} › {m['t']})."
        lec = fila("SELECT contenido FROM leccion WHERE usuario=? AND tema=?", (usuario, tid))
        if lec:
            sistema += "\nLección que el estudiante está leyendo:\n" + lec["contenido"][:20000]
    sistema += ("\nModo tutor socrático: si el estudiante pregunta algo que puede deducir, guíalo con una pregunta "
                "antes de dar la respuesta completa (salvo que pida la respuesta directa). Respuestas concisas.")
    if web:
        ctx.fase("Buscando en la web")
        res = ia.buscar_web(mensaje, n=5)
        if res:
            sistema += "\nResultados web de hoy (cita como [n] con enlace si los usas):\n" + "\n".join(
                f"[{i + 1}] {r['titulo']} — {r['url']}\n{r['texto']}" for i, r in enumerate(res))
    msgs = [{"role": "system", "content": sistema}]
    msgs += [{"role": "user" if h["rol"] == "usuario" else "assistant", "content": h["texto"]} for h in historia]
    msgs.append({"role": "user", "content": mensaje})
    ejecutar("INSERT INTO chat(usuario,hilo,rol,texto,fecha) VALUES(?,?,?,?,?)",
             (usuario, hilo, "usuario", mensaje, time.time()))
    ctx.fase("Pensando")
    r = ctx.chat(msgs, max_tokens=1500, temperatura=0.6)
    ejecutar("INSERT INTO chat(usuario,hilo,rol,texto,fecha) VALUES(?,?,?,?,?)",
             (usuario, hilo, "tutor", r, time.time()))
    return {"texto": r}


# ------------------------------------------------------ cuaderno (visión)
ESQUEMA_APUNTE = {"type": "object", "properties": {
    "transcripcion": {"type": "string"},
    "titulo": {"type": "string"},
    "puntaje": {"type": "integer", "minimum": 0, "maximum": 100},
    "correcto": {"type": "array", "items": {"type": "string"}, "maxItems": 6},
    "errores": {"type": "array", "items": {"type": "string"}, "maxItems": 8},
    "mejoras": {"type": "array", "items": {"type": "string"}, "maxItems": 5},
    "tarjetas": {"type": "array", "maxItems": 6, "items": {"type": "object", "properties": {
        "frente": {"type": "string"}, "reverso": {"type": "string"}}, "required": ["frente", "reverso"]}}},
    "required": ["transcripcion", "titulo", "puntaje", "correcto", "errores", "mejoras", "tarjetas"]}


def evaluar_apunte(ctx, ruta_png, tid, usuario, contexto=""):
    datos = base64.b64encode(open(ruta_png, "rb").read()).decode()
    tema_txt = ""
    if tid:
        t, area, m = contexto_tema(tid, usuario)
        tema_txt = f"Los apuntes son del tema «{t['t']}» ({area['nombre']} › {m['t']})."
    prompt = (
        "Estos son apuntes escritos a mano (con lápiz en tablet/celular) por el estudiante. "
        f"{tema_txt} {contexto}\n"
        "1) Transcríbelos fielmente a markdown (fórmulas en LaTeX; si hay dibujos o diagramas, descríbelos entre "
        "corchetes). Si una parte es ilegible escribe [ilegible].\n"
        "2) Evalúalos como profesor exigente: qué está correcto, errores conceptuales o de cálculo (específicos, citando "
        "lo escrito), y cómo mejorar los apuntes (organización, lo que falta).\n"
        "3) Propón hasta 6 tarjetas de repaso con lo más importante.\n"
        "puntaje 0-100 = calidad y exactitud. titulo = título corto para estos apuntes. Responde JSON compacto.")
    ctx.fase("Leyendo tu letra")
    return ctx.chat([{"role": "system", "content": SISTEMA_BASE}, {"role": "user", "content": [
        {"type": "text", "text": prompt},
        {"type": "image_url", "image_url": {"url": "data:image/png;base64," + datos}}]}],
        max_tokens=2500, temperatura=0.2, esquema=ESQUEMA_APUNTE)


# ------------------------------------------------------------- objetivos
def planear_objetivo(ctx, usuario, perfil, titulo, descripcion):
    catalogo = cur.catalogo_modulos(usuario)
    refs = [r for r, _ in catalogo]
    texto_cat = "\n".join(f"{r} = {d}" for r, d in catalogo)
    esquema = {"type": "object", "properties": {
        "resumen": {"type": "string"},
        "modulos": {"type": "array", "minItems": 1, "maxItems": 14, "items": {"type": "object", "properties": {
            "ref": {"type": "string", "enum": refs}, "por_que": {"type": "string"}},
            "required": ["ref", "por_que"]}},
        "nuevos": {"type": "array", "maxItems": 8, "items": {"type": "object", "properties": {
            "t": {"type": "string"},
            "nivel": {"type": "integer", "minimum": 1, "maximum": 5},
            "por_que": {"type": "string"},
            "temas": {"type": "array", "minItems": 3, "maxItems": 7, "items": {"type": "string"}}},
            "required": ["t", "nivel", "por_que", "temas"]}}},
        "required": ["resumen", "modulos", "nuevos"]}
    prompt = (
        f"El estudiante quiere lograr este objetivo de aprendizaje:\n«{titulo}»\n{descripcion}\n\n{texto_perfil(perfil)}\n\n"
        "Diseña la ruta completa, de lo más básico a lo más avanzado y la frontera (horizonte):\n"
        "- 'modulos': módulos del catálogo que son NECESARIOS directamente para el objetivo (no hace falta listar sus "
        "prerrequisitos básicos: el sistema los agrega solo). Cada uno con 'por_que' de una frase.\n"
        "- 'nuevos': módulos específicos del objetivo que el catálogo NO cubre (habilidades concretas, herramientas, "
        "proyecto práctico final, y al menos uno de nivel 5 'horizonte' con el estado del arte). Todo en español. Cada uno con 3-7 temas "
        "con el formato 'Título|descripción corta'.\n"
        "- 'resumen': 2-3 frases sobre el camino y el proyecto final que demostrará el logro.\n"
        "Responde solo JSON compacto.\n\nCATÁLOGO (ref = descripción):\n" + texto_cat)
    ctx.fase("Diseñando la ruta")
    plan = ctx.chat([{"role": "system", "content": SISTEMA_BASE}, {"role": "user", "content": prompt}],
                    max_tokens=3000, temperatura=0.3, esquema=esquema)
    cur_id = ejecutar("INSERT INTO objetivo(usuario,titulo,descripcion,plan,creado) VALUES(?,?,?,?,?)",
                      (usuario, titulo, descripcion, "{}", time.time())).lastrowid
    area_id = f"obj{cur_id}"
    directos = [m["ref"] for m in plan["modulos"]]
    mods, extra, razones = [], [], {m["ref"]: m["por_que"] for m in plan["modulos"]}
    for i, n in enumerate(sorted(plan.get("nuevos", []), key=lambda x: x["nivel"])):
        mid = f"m{i}"
        menores = [d for d in directos if (cur.modulo(d, usuario) or {}).get("nivel", 9) <= n["nivel"]]
        pre = [f"{area_id}.{mods[-1]['id']}"] if mods else []
        pre += menores[:3] if not mods else []
        mods.append({"id": mid, "t": n["t"], "nivel": n["nivel"], "pre": pre, "temas": n["temas"]})
        extra.append(f"{area_id}.{mid}")
        razones[f"{area_id}.{mid}"] = n["por_que"]
    if mods:
        area = {"id": area_id, "nombre": f"🎯 {titulo}", "icono": "🎯", "grupo": "Mis objetivos",
                "color": "#f39c12", "descripcion": plan["resumen"], "objetivo": cur_id, "usuario": usuario,
                "recursos": [], "modulos": mods}
        ejecutar("INSERT OR REPLACE INTO area_extra(id,usuario,datos,creado) VALUES(?,?,?,?)",
                 (area_id, usuario, json.dumps(area, ensure_ascii=False), time.time()))
    ejecutar("UPDATE objetivo SET plan=? WHERE id=?", (json.dumps(
        {"resumen": plan["resumen"], "modulos": directos, "extra": extra, "razones": razones},
        ensure_ascii=False), cur_id))
    return {"objetivo": cur_id}


# ------------------------------------------------- práctica (entregas)
def seccion_practica(contenido):
    """La sección de ejercicios de la lección (enunciados + soluciones)."""
    import re
    m = (re.search(r"^##[^\n]*(?:🏋|Pr[aá]ctica t[uú])[^\n]*\n(.*?)(?=^## |\Z)", contenido or "", re.S | re.M)
         or re.search(r"^##[^\n]*Pr[aá]ctica[^\n]*\n(.*?)(?=^## |\Z)", contenido or "", re.S | re.M))
    return m.group(1).strip() if m else ""


def ejercicios_de(contenido):
    """Lista de ejercicios de la práctica: [{n, titulo, enunciado}], para que
    el estudiante elija a cuál entrega. Reconoce «**Ejercicio 1 (…):**»,
    «**Nivel 2 …:**» y listas numeradas."""
    import re
    sec = re.sub(r"<details>.*?</details>", "", seccion_practica(contenido), flags=re.S)
    out = []
    for par in re.split(r"\n\s*\n", sec):
        par = par.strip()
        m = re.match(r"^\*\*(.+?)\*\*:?\s*(.*)", par, re.S)
        if m and not re.match(r"(?i)soluci", m.group(1)):
            out.append({"titulo": m.group(1).strip(" :"), "enunciado": m.group(2).strip()})
            continue
        for item in re.findall(r"^\s*\d{1,2}[.)]\s+(.+)$", par, re.M):
            out.append({"titulo": "", "enunciado": item.strip()})
    for i, e in enumerate(out):
        m = re.match(r"^\*\*\(?(.+?)\)?:?\*\*:?\s*(.*)", e["enunciado"], re.S)
        if m and e["titulo"] in ("",) + tuple(f"Ejercicio {k}" for k in range(1, 30)):
            e["titulo"] = (e["titulo"] + " · " if e["titulo"] else "") + m.group(1).strip(" :()")
            e["enunciado"] = m.group(2)
        e["n"] = i + 1
        e["titulo"] = e["titulo"] or f"Ejercicio {i + 1}"
        e["enunciado"] = re.sub(r"\s+", " ", e["enunciado"])[:220]
    return out


ESQUEMA_ENTREGA = {"type": "object", "properties": {
    "transcripcion": {"type": "string"},
    "puntaje": {"type": "integer", "minimum": 0, "maximum": 100},
    "veredicto": {"type": "string", "enum": ["correcto", "parcialmente correcto", "incorrecto", "incompleto"]},
    "bien": {"type": "array", "maxItems": 5, "items": {"type": "string"}},
    "errores": {"type": "array", "maxItems": 6, "items": {"type": "string"}},
    "correccion": {"type": "string"},
    "siguiente": {"type": "string"}},
    "required": ["transcripcion", "puntaje", "veredicto", "bien", "errores", "correccion", "siguiente"]}


def corregir_entrega(ctx, e, usuario):
    t, area, _ = contexto_tema(e["tema"], usuario)
    if e.get("tarea"):
        tarea = fila("SELECT * FROM tarea WHERE id=?", (e["tarea"],))
        practica = texto_tarea(json.loads(tarea["ejercicios"])) if tarea else ""
    else:
        lec = fila("SELECT contenido FROM leccion WHERE usuario=? AND tema=?", (usuario, e["tema"]))
        practica = seccion_practica(lec["contenido"] if lec else "")
    practica = practica or "(sin enunciado guardado: evalúa la solución con tu conocimiento)"
    cual = f"el ejercicio {e['ejercicio']}" if str(e["ejercicio"]).isdigit() else f"este trabajo («{e['ejercicio']}»)"
    instr = (
        f"Tema: «{t['t']}» ({area['nombre']}). El estudiante entrega su solución a {cual} de la práctica de la lección "
        f"(versión {e['version']}).\n\nEJERCICIOS Y SOLUCIONES DE LA LECCIÓN:\n{practica[:9000]}\n\n"
        "Corrige como profesor exigente y justo: revisa planteamiento, procedimiento, cálculos, unidades y resultado. "
        "Acepta métodos distintos si son válidos. transcripcion = lo que entregó, en markdown (fórmulas en $...$ cortas; "
        "si es imagen, transcríbela; si algo es ilegible, [ilegible]). correccion = la solución correcta explicada paso a paso, "
        "breve. errores = concretos, citando lo que escribió. puntaje en escala de 0 a 100 (100 = perfecto; "
        "correcto ≈ 85-100, parcialmente correcto ≈ 50-84, incompleto ≈ 20-60, incorrecto ≈ 0-40). JSON compacto.")
    contenido = [{"type": "text", "text": instr}]
    if e["tipo"] in ("imagen", "cuaderno") and e["imagen"]:
        datos = base64.b64encode(open(e["imagen"], "rb").read()).decode()
        mime = "image/png" if e["imagen"].endswith(".png") else "image/jpeg"
        contenido.append({"type": "image_url", "image_url": {"url": f"data:{mime};base64,{datos}"}})
        ctx.fase("Leyendo tu solución")
    if e.get("texto"):
        contenido.append({"type": "text", "text": "SOLUCIÓN DEL ESTUDIANTE (texto):\n" + e["texto"]})
    ctx.fase("Corrigiendo")
    ev = ctx.chat([{"role": "system", "content": SISTEMA_BASE}, {"role": "user", "content": contenido}],
                  max_tokens=2200, temperatura=0.2, esquema=ESQUEMA_ENTREGA)
    return normalizar_puntaje(ev)


def normalizar_puntaje(ev):
    """El modelo a veces puntúa de 0 a 10: se reescala y se alinea con el veredicto."""
    p, v = ev.get("puntaje", 0), ev.get("veredicto")
    if p <= 10 and v != "incorrecto":
        p *= 10
    rangos = {"correcto": (80, 100), "parcialmente correcto": (40, 84), "incompleto": (10, 70), "incorrecto": (0, 45)}
    lo, hi = rangos.get(v, (0, 100))
    ev["puntaje"] = int(min(max(p, lo), hi))
    return ev


# ------------------------------------------- nueva área completa con IA
GRUPOS = ["Ingenierías", "Ciencias básicas", "Humanidades", "Negocios", "Idiomas", "Arte y diseño", "Salud", "Otros"]


def crear_area(ctx, usuario, perfil, nombre, descripcion):
    """Una carrera o área completa (no un objetivo puntual): 8-14 módulos de
    Fundamentos a Horizonte, enlazados con los prerrequisitos del currículo."""
    import re
    catalogo = cur.catalogo_modulos(usuario)
    refs = [r for r, _ in catalogo]
    esquema = {"type": "object", "properties": {
        "nombre": {"type": "string"}, "icono": {"type": "string"},
        "grupo": {"type": "string", "enum": GRUPOS}, "descripcion": {"type": "string"},
        "modulos": {"type": "array", "minItems": 8, "maxItems": 14, "items": {"type": "object", "properties": {
            "id": {"type": "string", "pattern": "^[a-z][a-z0-9_]{1,24}$"},
            "t": {"type": "string"},
            "nivel": {"type": "integer", "minimum": 1, "maximum": 5},
            "pre_propios": {"type": "array", "maxItems": 3, "items": {"type": "string"}},
            "pre_externos": {"type": "array", "maxItems": 2, "items": {"type": "string", "enum": refs}},
            "temas": {"type": "array", "minItems": 4, "maxItems": 7, "items": {"type": "string"}}},
            "required": ["id", "t", "nivel", "pre_propios", "pre_externos", "temas"]}}},
        "required": ["nombre", "icono", "grupo", "descripcion", "modulos"]}
    prompt = (
        f"Diseña el currículo COMPLETO del área/carrera «{nombre}». {descripcion}\n{texto_perfil(perfil)}\n\n"
        "Como el plan de estudios de una carrera universitaria de primer nivel más su frontera: 8-14 módulos que vayan "
        "del nivel 1 (Fundamentos) al 5 (Horizonte: estado del arte), pasando por 2 Intermedio, 3 Avanzado y 4 Experto. "
        "Cada módulo: id corto en minúsculas (snake_case), título, nivel, 4-7 temas con el formato 'Título|descripción corta', "
        "pre_propios (ids de módulos ANTERIORES de esta misma área) y pre_externos (módulos del catálogo existente que "
        "sean prerrequisito real; no repitas lo que el catálogo ya cubre: apóyate en él). icono = un emoji. "
        "Todo en español. JSON compacto.\n\nCATÁLOGO EXISTENTE (ref = descripción):\n"
        + "\n".join(f"{r} = {d}" for r, d in catalogo))
    ctx.fase("Diseñando el currículo del área")
    r = ctx.chat([{"role": "system", "content": SISTEMA_BASE}, {"role": "user", "content": prompt}],
                 max_tokens=4500, temperatura=0.3, esquema=esquema)
    base_id = re.sub(r"[^a-z0-9]+", "_", nombre.lower().translate(str.maketrans("áéíóúñü", "aeiounu"))).strip("_")[:24] or "area"
    area_id = f"p_{base_id}"
    ids = set()
    mods = []
    for m in sorted(r["modulos"], key=lambda m: m["nivel"]):
        mid = m["id"] if m["id"] not in ids else f"{m['id']}_{len(ids)}"
        pre = [p for p in m["pre_propios"] if p in ids] + [p for p in m["pre_externos"] if p in refs]
        ids.add(mid)
        mods.append({"id": mid, "t": m["t"], "nivel": m["nivel"], "pre": pre, "temas": m["temas"]})
    ctx.fase("Buscando recursos confiables")
    recursos = [{"t": x["titulo"], "u": x["url"]} for x in ia.buscar_web(f"{nombre} curso gratis universidad", n=8)
                if ia._confianza(x["url"]) > 1][:5]
    area = {"id": area_id, "nombre": r["nombre"] or nombre, "icono": (r["icono"] or "📘")[:2], "grupo": r["grupo"],
            "color": "#00a8a8", "descripcion": r["descripcion"], "usuario": usuario, "recursos": recursos, "modulos": mods}
    ejecutar("INSERT OR REPLACE INTO area_extra(id,usuario,datos,creado) VALUES(?,?,?,?)",
             (area_id, usuario, json.dumps(area, ensure_ascii=False), time.time()))
    return {"area": area_id}


# ---------------------------------------------- tareas de práctica (Repasar)
DIFICULTADES = {"basica": "básica (aplicar la idea directamente)",
                "intermedia": "intermedia (combinar 2 ideas, varios pasos)",
                "reto": "reto (problema abierto de ingeniería/negocios, como en un examen difícil o un trabajo real)"}


def texto_tarea(ejs):
    return "\n\n".join(f"**Ejercicio {i + 1}: {e['titulo']}**\n{e['enunciado']}\n\nSolución de referencia:\n{e['solucion']}"
                       for i, e in enumerate(ejs))


ESQUEMA_TAREA = {"type": "object", "properties": {
    "titulo": {"type": "string"},
    "ejercicios": {"type": "array", "minItems": 1, "maxItems": 8, "items": {"type": "object", "properties": {
        "titulo": {"type": "string"}, "enunciado": {"type": "string"},
        "pista": {"type": "string"}, "solucion": {"type": "string"}},
        "required": ["titulo", "enunciado", "pista", "solucion"]}}},
    "required": ["titulo", "ejercicios"]}


ESQUEMA_QUIZ_TAREA = {"type": "object", "properties": {
    "titulo": {"type": "string"},
    "ejercicios": {"type": "array", "minItems": 1, "maxItems": 15, "items": {"type": "object", "properties": {
        "pregunta": {"type": "string"},
        "opciones": {"type": "array", "minItems": 4, "maxItems": 4, "items": {"type": "string"}},
        "correcta": {"type": "integer", "minimum": 0, "maximum": 3},
        "explicacion": {"type": "string"}},
        "required": ["pregunta", "opciones", "correcta", "explicacion"]}}},
    "required": ["titulo", "ejercicios"]}


def crear_quiz_tarea(ctx, usuario, perfil, tid, dificultad, cantidad, enfoque):
    import random
    t, area, m = contexto_tema(tid, usuario)
    lec = fila("SELECT contenido FROM leccion WHERE usuario=? AND tema=?", (usuario, tid))
    previas = filas("SELECT ejercicios FROM tarea WHERE usuario=? AND tema=? AND tipo='quiz' ORDER BY id DESC LIMIT 4",
                    (usuario, tid))
    ya = [e.get("pregunta", "")[:140] for p in previas for e in json.loads(p["ejercicios"])][:40]
    fallos = filas("""SELECT t.frente FROM repaso r JOIN tarjeta t ON t.id=r.tarjeta WHERE r.usuario=? AND t.tema=?
                      AND r.nota=1 ORDER BY r.fecha DESC LIMIT 5""", (usuario, tid))
    prompt = (
        f"Crea un QUIZ de práctica de {cantidad} preguntas de opción múltiple sobre «{t['t']}» ({t['d']}) — "
        f"{area['nombre']} › {m['t']}.\nDificultad: {DIFICULTADES.get(dificultad, dificultad)}.\n{texto_perfil(perfil)}\n"
        + (f"Enfoque pedido por el estudiante: {enfoque}\n" if enfoque else "")
        + (f"Tarjetas que ha olvidado de este tema (refuérzalas): {'; '.join(f['frente'][:100] for f in fallos)}\n" if fallos else "")
        + (f"NO repitas estas preguntas de quizzes anteriores:\n- " + "\n- ".join(ya) + "\n" if ya else "")
        + "Preguntas de comprensión y aplicación (no de memoria literal), 4 opciones plausibles con errores típicos como "
        "distractores, la correcta en posiciones variadas, explicación de 1-2 frases. Fórmulas en LaTeX corto entre $...$. "
        "titulo = nombre corto del quiz. JSON compacto."
        + (f"\n\nLECCIÓN DE REFERENCIA (extracto):\n{lec['contenido'][:12000]}" if lec else ""))
    ctx.fase(f"Creando el quiz: {t['t']}")
    r = ctx.chat([{"role": "system", "content": SISTEMA_BASE}, {"role": "user", "content": prompt}],
                 max_tokens=350 * cantidad + 400, temperatura=0.8, esquema=ESQUEMA_QUIZ_TAREA,
                 semilla=random.randint(1, 2 ** 31))
    tid_db = ejecutar("""INSERT INTO tarea(usuario,tema,area,titulo,dificultad,enfoque,ejercicios,creado,tipo)
                         VALUES(?,?,?,?,?,?,?,?,'quiz')""", (usuario, tid, t["area"], r["titulo"], dificultad, enfoque,
                                                             json.dumps(r["ejercicios"], ensure_ascii=False), time.time())).lastrowid
    return {"tarea": tid_db}


def crear_tarea(ctx, usuario, perfil, tid, dificultad, cantidad, enfoque, tipo="desarrollo"):
    if tipo == "quiz":
        return crear_quiz_tarea(ctx, usuario, perfil, tid, dificultad, cantidad, enfoque)
    t, area, m = contexto_tema(tid, usuario)
    lec = fila("SELECT contenido FROM leccion WHERE usuario=? AND tema=?", (usuario, tid))
    previas = filas("""SELECT ejercicios FROM tarea WHERE usuario=? AND tema=? AND IFNULL(tipo,'desarrollo')='desarrollo'
                       ORDER BY id DESC LIMIT 3""", (usuario, tid))
    ya = [e["titulo"] for p in previas for e in json.loads(p["ejercicios"])]
    falladas = filas("""SELECT evaluacion FROM entrega WHERE usuario=? AND tema=? AND puntaje < 70
                        ORDER BY id DESC LIMIT 3""", (usuario, tid))
    errores = [x for f in falladas for x in (json.loads(f["evaluacion"] or "{}").get("errores") or [])][:6]
    idioma = area.get("idioma")
    prompt = (
        f"Crea una TAREA DE PRÁCTICA de {cantidad} ejercicio(s) sobre «{t['t']}» ({t['d']}) — {area['nombre']} › {m['t']}.\n"
        f"Dificultad: {DIFICULTADES.get(dificultad, dificultad)}.\n{texto_perfil(perfil)}\n"
        + (f"Enfoque pedido por el estudiante: {enfoque}\n" if enfoque else "")
        + (f"Errores que cometió antes en este tema (diseña ejercicios que los ataquen): {'; '.join(errores)}\n" if errores else "")
        + (f"No repitas estos ejercicios ya hechos: {'; '.join(ya)}\n" if ya else "")
        + ("Es un idioma: ejercicios de traducción, completar, ordenar frases o redactar, con la solución en el idioma.\n" if idioma else
           "Ejercicios con datos concretos y realistas (ingeniería, mecatrónica, sistemas o negocios), que se resuelvan "
           "a mano o en papel; nada de preguntas de memoria.\n")
        + "Cada ejercicio: titulo corto, enunciado completo (con todos los datos), pista (sin dar la respuesta) y "
        "solucion paso a paso con el resultado final. Fórmulas en LaTeX corto entre $...$. JSON compacto.\n"
        + (f"\nLECCIÓN DE REFERENCIA (extracto):\n{lec['contenido'][:12000]}" if lec else ""))
    ctx.fase(f"Creando la tarea: {t['t']}")
    r = ctx.chat([{"role": "system", "content": SISTEMA_BASE}, {"role": "user", "content": prompt}],
                 max_tokens=900 * cantidad + 500, temperatura=0.6, esquema=ESQUEMA_TAREA)
    tid_db = ejecutar("""INSERT INTO tarea(usuario,tema,area,titulo,dificultad,enfoque,ejercicios,creado)
                         VALUES(?,?,?,?,?,?,?,?)""", (usuario, tid, t["area"], r["titulo"], dificultad, enfoque,
                                                      json.dumps(r["ejercicios"], ensure_ascii=False), time.time())).lastrowid
    return {"tarea": tid_db}
