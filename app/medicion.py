"""Banco de pruebas de la IA (fase F2): mide con datos, no con fe, qué modelo escribe mejor cada tarea.

Cada «variante» es un modelo (IA local, Gemini con razonamiento bajo/medio/alto) con o sin skills como contexto. Todas
reciben EXACTAMENTE lo mismo: el mismo tema, las mismas ideas y las mismas fuentes congeladas, de modo que la única
diferencia es el modelo. Se mide en tres capas:

1. **Comprobaciones objetivas** (`revisar_parte`, `revisar_ejercicios`): citas que apuntan a fuentes que existen, enlaces
   inventados, estructura pedida, respuestas desplegables, fórmulas balanceadas, repeticiones, idioma y longitud.
2. **Juez** (`juzgar`): un modelo califica con rúbrica las lecciones ANÓNIMAS y en orden aleatorio, en dos rondas con
   orden distinto. Un modelo puede favorecer su propio estilo: por eso es solo un apoyo.
3. **Lectura ciega de la persona** (`preparar_ciega`): la verdad de fondo. Las lecciones se muestran sin nombre de modelo.

Privacidad: aquí solo viajan temas generales y fuentes públicas (nunca perfil, tutor, apuntes, entregas ni cartera).
No toca la cola ni la base real: guarda sus resultados en `datos/medicion/<corrida>/` (o `ACADEMIA_MEDICION`).

    python3 app/medicion.py congelar            busca y guarda las fuentes de cada tema (una sola vez)
    python3 app/medicion.py correr  [--temas bayes,bst] [--variantes local,g38-alto] [--tareas parte,ejercicios]
    python3 app/medicion.py juzgar  [--juez g35-alto]
    python3 app/medicion.py informe
    python3 app/medicion.py ciega   [--n 4]

«congelar» se ejecuta con `ACADEMIA_DATOS` apuntando a una carpeta temporal (la búsqueda de papers guarda caché en la
base); «correr» y «juzgar» con los datos reales, porque ahí está la clave de la API (este módulo nunca la imprime).
"""
import argparse
import json
import os
import random
import re
import statistics
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))

import config  # noqa: E402
import nube  # noqa: E402

MEDICION = Path(os.environ.get("ACADEMIA_MEDICION") or RAIZ / "datos" / "medicion")
SKILLS_DIR = Path(os.environ.get("ACADEMIA_SKILLS") or RAIZ.parent.parent / "skills-compartidas" / "skills")
SKILLS_USADAS = ("ensenar-para-dominar", "investigar-con-fuentes", "verificar-afirmaciones")
TOPE_SKILLS = 9000          # caracteres: un contexto largo gasta tokens en cada llamada y diluye la instrucción

# ------------------------------------------------------------------ temas (generales, verificables, sin datos personales)
TEMAS = {
    "bayes": {"t": "Teorema de Bayes", "area": "Probabilidad",
              "d": "Actualizar la probabilidad de una hipótesis con evidencia: probabilidad condicional, prior, verosimilitud y posterior",
              "ideas": ["definición de probabilidad condicional y derivación del teorema", "falacia de la tasa base en pruebas médicas",
                        "ejemplo con prior, sensibilidad y especificidad", "distinción entre P(A|B) y P(B|A)"]},
    "bst": {"t": "Árboles binarios de búsqueda y balanceo", "area": "Estructuras de datos",
            "d": "Inserción, búsqueda y borrado en un BST; por qué el orden de inserción importa y cómo el balanceo garantiza O(log n)",
            "ideas": ["invariante del BST y recorrido inorden", "complejidad en el caso medio y en el peor caso",
                      "rotaciones y árboles AVL", "ejemplo de inserción paso a paso"]},
    "newton": {"t": "Segunda ley de Newton y diagramas de cuerpo libre", "area": "Física",
               "d": "F = ma como relación vectorial entre fuerza neta y aceleración; cómo plantear un problema con diagrama de cuerpo libre",
               "ideas": ["fuerza neta, masa y aceleración como vectores", "pasos para un diagrama de cuerpo libre",
                         "plano inclinado con rozamiento", "unidades y errores típicos"]},
    "inflacion": {"t": "Inflación y tasas de interés reales", "area": "Economía",
                  "d": "Cómo se mide la inflación, qué es la tasa real frente a la nominal y qué efecto tiene sobre ahorro y deuda",
                  "ideas": ["índice de precios y cálculo de la inflación", "ecuación de Fisher (tasa real y nominal)",
                            "efecto sobre ahorradores y deudores", "ejemplo numérico con datos concretos"]},
    "retroprop": {"t": "Redes neuronales: retropropagación", "area": "Inteligencia artificial",
                  "d": "Cómo una red aprende ajustando pesos con el gradiente de una función de pérdida usando la regla de la cadena",
                  "ideas": ["función de pérdida y descenso del gradiente", "regla de la cadena aplicada capa por capa",
                            "ejemplo numérico con una neurona", "gradientes que se desvanecen"]},
    "kant": {"t": "El imperativo categórico de Kant", "area": "Ética",
             "d": "La ética deontológica de Kant: universalizabilidad, humanidad como fin y autonomía de la voluntad",
             "ideas": ["imperativo hipotético frente a categórico", "fórmula de la ley universal y la de la humanidad",
                       "ejemplo de la promesa falsa", "objeciones clásicas y respuestas"]},
}

# consulta académica en inglés para los papers (OpenAlex indexa sobre todo en inglés; la lección real también la traduce)
CONSULTA_EN = {"bayes": "Bayes theorem base rate fallacy conditional probability", "bst": "balanced binary search tree AVL rotations",
               "newton": "Newton second law free body diagram teaching", "inflacion": "real interest rate Fisher equation inflation",
               "retroprop": "backpropagation gradient descent neural network", "kant": "Kant categorical imperative universalizability"}

# ------------------------------------------------------------------ variantes
# clave → modelo, esfuerzo de razonamiento y si lleva skills («+sk»)
BASE_VARIANTES = {
    "local": {"proveedor": "local", "modelo": None, "esfuerzo": ""},
    "g38-bajo": {"proveedor": "google", "modelo": "gemini-3.8-flash", "esfuerzo": "low"},
    "g38-medio": {"proveedor": "google", "modelo": "gemini-3.8-flash", "esfuerzo": "medium"},
    "g38-alto": {"proveedor": "google", "modelo": "gemini-3.8-flash", "esfuerzo": "high"},
    "g35-alto": {"proveedor": "google", "modelo": "gemini-3.5-flash", "esfuerzo": "high"},
}
PRECIO_POR_MODELO = {"gemini-3.8-flash": (0.75, 3.75)}     # USD por millón (entrada, salida); lo demás, estimación alta
ESPERAS_TRANSITORIAS = (5, 15, 45)


def variante(clave):
    base, _, sk = clave.partition("+")
    if base not in BASE_VARIANTES or sk not in ("", "sk"):
        raise ValueError(f"variante desconocida: {clave}")
    return {"clave": clave, **BASE_VARIANTES[base], "skills": sk == "sk"}


# ------------------------------------------------------------------ skills como contexto
def cargar_skills(nombres=SKILLS_USADAS, carpeta=None, tope=TOPE_SKILLS):
    """Texto de las skills (sin la cabecera YAML) para anteponerlo a las instrucciones del modelo. Reparte el tope
    entre las skills para que ninguna se quede fuera; recorta por párrafos completos, no a mitad de frase."""
    carpeta = Path(carpeta or SKILLS_DIR)
    cuerpos = []
    for n in nombres:
        # la colección las agrupa por etapa (09-ensenanza/…): se busca la skill por nombre en cualquier subcarpeta
        ruta = next(iter(sorted(carpeta.glob(f"*/{n}/SKILL.md"))), None) or carpeta / n / "SKILL.md"
        try:
            t = ruta.read_text(encoding="utf-8")
        except OSError:
            continue
        if t.startswith("---"):
            fin = t.find("\n---", 3)
            t = t[fin + 4:] if fin != -1 else t
        cuerpos.append((n, t.strip()))
    if not cuerpos:
        return ""
    cupo = tope // len(cuerpos)
    salida = []
    for n, t in cuerpos:
        if len(t) > cupo:
            t = t[:cupo].rsplit("\n\n", 1)[0]
        salida.append(f"### Método: {n}\n{t}")
    return ("Sigue estos métodos de trabajo en todo lo que escribas (son tu manera de enseñar, investigar y comprobar):\n\n"
            + "\n\n".join(salida))


# ------------------------------------------------------------------ llamadas a los modelos
def _precio(modelo):
    return PRECIO_POR_MODELO.get(modelo) or nube.PRECIO_DEFECTO


def _gpu_libre_para_local(max_espera=1200):
    """No se pide la IA local si otro modelo (p. ej. el de otra aplicación) está cargado: pedirla lo descargaría en pleno uso."""
    import ia
    fin = time.time() + max_espera
    while True:
        try:
            with urllib.request.urlopen(ia.LLAMA() + "/running", timeout=5) as r:
                cargados = [m["model"] for m in json.loads(r.read()).get("running", [])]
        except Exception:  # noqa: BLE001 - si no se puede saber, se intenta igual
            return
        if all(m == str(ia.MODELO) for m in cargados):
            return
        if time.time() > fin:
            raise TimeoutError(f"la GPU la usa otro modelo ({', '.join(cargados)})")
        time.sleep(30)


def _local(mensajes, max_tokens, temperatura, esquema):
    import ia
    _gpu_libre_para_local()
    cuerpo = {"model": str(ia.MODELO), "messages": mensajes, "stream": False, "max_tokens": max_tokens,
              "temperature": temperatura, "chat_template_kwargs": {"enable_thinking": False}}
    if esquema:
        cuerpo["response_format"] = {"type": "json_schema", "json_schema": {"name": "salida", "schema": esquema}}
    req = urllib.request.Request(f"{ia.LLAMA()}/v1/chat/completions", data=json.dumps(cuerpo).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=1800) as r:
        j = json.loads(r.read())
    u = j.get("usage") or {}
    return (j["choices"][0]["message"]["content"] or "").strip(), u.get("prompt_tokens", 0), u.get("completion_tokens", 0)


def _api(v, mensajes, max_tokens, temperatura, esquema):
    ficha = nube.PROVEEDORES["google"]
    p = {"id": "google", "tipo": ficha["tipo"], "url": ficha["url"], "modelo": v["modelo"]}
    clave = nube.secretos.obtener("claves_ia", "google")
    if not clave:
        raise nube.ErrorNube("no hay clave de Gemini configurada")
    if v["esfuerzo"]:     # los tokens de razonamiento salen del mismo tope (igual que en nube._chat_una_vez)
        max_tokens = min(64000, max_tokens + {"low": 2000, "medium": 6000, "high": 12000}[v["esfuerzo"]])
    op = {"temperatura": False, "semilla": False, "stream_options": True, "max_completion": False,
          "razonamiento": v["esfuerzo"]}
    modo = "json_schema" if esquema else "ninguno"
    for _ in range(4):
        msgs = nube._con_esquema(mensajes, esquema) if esquema and modo != "json_schema" else mensajes
        try:
            return nube._openai(None, p, clave, msgs, max_tokens, temperatura, esquema, False, None, modo, op)
        except nube._Reajustar as e:
            if e.que == "esquema":
                modo = {"json_schema": "json_object", "json_object": "ninguno"}.get(modo)
                if modo is None:
                    raise nube.ErrorNube(e.detalle) from None
            else:
                op[e.que] = e.valor
    raise nube.ErrorNube("el servicio rechazó los parámetros varias veces")


def llamar(v, mensajes, max_tokens, temperatura=0.5, esquema=None):
    """Una llamada medida. Nunca lanza: un fallo es un dato (se anota y NO se sustituye por otro modelo, o la medición
    quedaría contaminada). Devuelve {texto, tin, tout, seg, error, costo_usd}."""
    t0 = time.time()
    texto, tin, tout, err = "", 0, 0, None
    for espera in (*ESPERAS_TRANSITORIAS, None):
        try:
            if v["proveedor"] == "local":
                texto, tin, tout = _local(mensajes, max_tokens, temperatura, esquema)
            else:
                texto, tin, tout = _api(v, mensajes, max_tokens, temperatura, esquema)
            err = None
            break
        except urllib.error.HTTPError as e:
            err = f"HTTP {e.code}"
            if e.code not in (429, 500, 502, 503, 504) or espera is None:
                break
            time.sleep(espera)
        except nube.ErrorNube as e:
            err = str(e)[:300]
            if getattr(e, "code", 0) not in (429, 500, 502, 503, 504) or espera is None:
                break
            time.sleep(espera)
        except Exception as e:  # noqa: BLE001 - tiempo agotado, red, JSON roto: todo es un dato de la medición
            err = f"{type(e).__name__}: {e}"[:300]
            break
    pin, pout = (0.0, 0.0) if v["proveedor"] == "local" else _precio(v["modelo"])
    return {"texto": texto, "tin": tin, "tout": tout, "seg": round(time.time() - t0, 1), "error": err,
            "costo_usd": round((tin * pin + tout * pout) / 1e6, 5)}


# ------------------------------------------------------------------ fuentes congeladas
def ruta_fuentes(tema):
    return MEDICION / "fuentes" / f"{tema}.json"


def congelar(temas=None, pausa=3.0):
    """Busca UNA vez las fuentes de cada tema y las guarda: todas las variantes leen las mismas."""
    import base
    base.iniciar()          # la búsqueda de papers guarda su caché en la base: debe ser la temporal, no la real
    import ciencia
    import verificacion as vf
    for tid in temas or TEMAS:
        destino = ruta_fuentes(tid)
        if destino.exists():
            previo = json.loads(destino.read_text(encoding="utf-8"))
            if previo.get("fuentes") and previo.get("papers"):
                continue          # completo; si le faltaba algo (una búsqueda rechazada) se intenta de nuevo
        t = TEMAS[tid]
        web = vf.buscar_fuentes([f'{t["t"]} {t["d"]}'.strip(), f'{t["t"]} {t["area"]}'], n=4, academicas=False, leer=False)
        time.sleep(pausa)
        papers = []
        for espera in (0, 60, 180):        # OpenAlex responde 429 si se le pide seguido: se reintenta con calma
            time.sleep(espera)
            papers = ciencia.buscar(CONSULTA_EN.get(tid, t["t"]), 3)
            if papers:
                break
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_text(json.dumps({"fuentes": web, "papers": papers}, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"fuentes de «{tid}»: {len(web)} web, {len(papers)} papers")
        time.sleep(pausa)


def leer_fuentes(tema):
    return json.loads(ruta_fuentes(tema).read_text(encoding="utf-8"))


# ------------------------------------------------------------------ las tareas
def mensajes_parte(tid, fuentes, con_skills):
    """La misma petición que hace la lección real para una parte (lecciones._leccion_a_fondo), con ideas y fuentes fijas."""
    import lecciones
    t = TEMAS[tid]
    P = lecciones.PROFUNDIDAD[lecciones.VERSION_LECCION]
    extra = lecciones._bloque(fuentes["fuentes"], fuentes["papers"], 1, 1)
    prompt = (
        f"Área: {t['area']} · Tema: **{t['t']}** — {t['d']}\nEstudiante anónimo.\n\n"
        f"Escribe ahora la PARTE 1 de 1: «{t['t']}».\nIdeas que debe desarrollar a fondo: " + "; ".join(t["ideas"])
        + "\n\nFormato markdown, exactamente así:\n"
        f"## Parte 1 · {t['t']}\n### 🧠 Intuición (analogía o imagen mental)\n"
        "### 📘 Desarrollo (definiciones precisas; fórmulas en LaTeX; deriva o justifica paso a paso de dónde sale "
        "cada resultado y POR QUÉ funciona; distingue conceptos parecidos; usa tablas si comparan cosas)\n"
        "### ✍️ Ejemplos resueltos (al menos 2 con datos concretos, el segundo más difícil; muestra cada paso y "
        "comprueba el resultado)\n### ⚠️ Matices, casos límite y errores típicos\n"
        "### ✅ Comprueba (2 preguntas rápidas; respuesta dentro de <details><summary>Respuesta</summary>...</details>)\n\n"
        f"Extensión: {P['palabras']} palabras. Cita [n] o [Pn] donde uses una fuente. Sin saludo ni resumen final."
        + (f"\n\n{extra}" if extra else ""))
    return _con_sistema(lecciones.SISTEMA_BASE, prompt, con_skills), P["tokens"]


def _con_sistema(base, prompt, con_skills):
    sistema = base + (("\n\n" + cargar_skills()) if con_skills else "")
    return [{"role": "system", "content": sistema}, {"role": "user", "content": prompt}]


class _Ctx:
    """Adaptador para reutilizar `lecciones.generar_ejercicios` tal cual, pero contra la variante medida."""
    def __init__(self, v):
        self.v, self.ultimo = v, None

    def chat(self, mensajes, max_tokens=1800, temperatura=0.6, esquema=None, mostrar=True, semilla=None):
        self.ultimo = llamar(self.v, mensajes, max_tokens, temperatura, esquema)
        if self.ultimo["error"]:
            raise RuntimeError(self.ultimo["error"])
        import ia
        return ia.parsear_json(self.ultimo["texto"]) if esquema else self.ultimo["texto"]

    def fase(self, _texto):
        pass


def hacer_parte(v, tid):
    msgs, tokens = mensajes_parte(tid, leer_fuentes(tid), v["skills"])
    return llamar(v, msgs, tokens, 0.5)


def hacer_ejercicios(v, tid, leccion):
    import lecciones
    t = TEMAS[tid]
    ctx = _Ctx(v)
    t0 = time.time()
    try:
        datos = lecciones.generar_ejercicios(ctx, {"t": t["t"]}, {"nombre": t["area"]}, leccion)
        r = dict(ctx.ultimo or {}, error=None)
        r["texto"] = json.dumps(datos, ensure_ascii=False)
    except Exception as e:  # noqa: BLE001
        r = dict(ctx.ultimo or {"tin": 0, "tout": 0, "costo_usd": 0.0}, texto="", error=str(e)[:300])
    r["seg"] = round(time.time() - t0, 1)
    return r


# ------------------------------------------------------------------ comprobaciones objetivas
SECCIONES = ("Intuición", "Desarrollo", "Ejemplos resueltos", "Matices", "Comprueba")
_PALABRAS_ES = {"el", "la", "de", "que", "en", "los", "las", "un", "una", "por", "con", "para", "es", "se", "del", "al", "como"}
_PALABRAS_EN = {"the", "of", "and", "to", "is", "in", "that", "for", "with", "this", "are", "which", "from"}


def revisar_parte(texto, fuentes, rango_palabras=(800, 1200)):
    """Mide lo comprobable por programa. Devuelve {métrica: valor} y `objetivo` (0-100, mezcla simple y transparente)."""
    nweb, npap = len(fuentes.get("fuentes", [])), len(fuentes.get("papers", []))
    palabras = re.findall(r"\w+", texto.lower())
    n = len(palabras)
    citas_web = {int(x) for x in re.findall(r"(?<![\w\)\]])\[(\d{1,3})\]", texto)}
    citas_pap = {int(x) for x in re.findall(r"(?<![\w\)\]])\[P(\d{1,3})\]", texto)}
    falsas = len([c for c in citas_web if c > nweb]) + len([c for c in citas_pap if c > npap])
    conocidas = {f["url"].split("#")[0].rstrip("/") for f in fuentes.get("fuentes", [])}
    conocidas |= {(p.get("url") or "").split("#")[0].rstrip("/") for p in fuentes.get("papers", [])}
    conocidas |= {"https://doi.org/" + p["doi"].split("doi.org/")[-1] for p in fuentes.get("papers", []) if p.get("doi")}
    urls = {u.rstrip(".,;)").split("#")[0].rstrip("/") for u in re.findall(r"https?://[^\s)>\]]+", texto)}
    inventadas = len([u for u in urls if u not in conocidas])
    sin_bloques = re.sub(r"\$\$.*?\$\$", "", texto, flags=re.S)
    desbalance_dolares = (sin_bloques.count("$") - sin_bloques.count("\\$")) % 2
    es = sum(w in _PALABRAS_ES for w in palabras)
    en = sum(w in _PALABRAS_EN for w in palabras)
    m = {
        "palabras": n,
        "secciones": sum(1 for s in SECCIONES if s.lower() in texto.lower()) / len(SECCIONES),
        "respuestas": len(re.findall(r"<details>", texto)),
        "citas": len(citas_web) + len(citas_pap),
        "citas_falsas": falsas,
        "enlaces_inventados": inventadas,
        "formula_desbalanceada": int(bool(desbalance_dolares) or sin_bloques.count("{") != sin_bloques.count("}")
                                     and "$" in sin_bloques),
        "bucle": int(_hay_bucle(texto)),
        "en_español": round(es / max(es + en, 1), 2),
    }
    p = 100.0
    p -= 30 * (1 - m["secciones"])
    p -= 10 if m["respuestas"] < 2 else 0
    p -= 12 * min(falsas, 3)
    p -= 15 * min(inventadas, 3)
    p -= 8 * m["formula_desbalanceada"]
    p -= 40 * m["bucle"]
    p -= 25 if m["en_español"] < 0.7 else 0
    p -= 10 if m["citas"] == 0 and (nweb or npap) else 0
    lo, hi = rango_palabras
    if n < lo * 0.7 or n > hi * 1.6:
        p -= 15
    m["objetivo"] = max(0, round(p))
    return m


def _hay_bucle(texto):
    import ia
    return ia.en_bucle(texto)


def revisar_ejercicios(datos):
    """Estructura del quiz y las tarjetas: la corrección de las respuestas la juzga el juez."""
    quiz = datos.get("quiz") or [] if isinstance(datos, dict) else []
    tarjetas = datos.get("tarjetas") or [] if isinstance(datos, dict) else []
    if not quiz and not tarjetas:
        return {"preguntas": 0, "tarjetas": 0, "objetivo": 0}
    opcion = [q for q in quiz if q.get("tipo") == "opcion"]
    malas = 0
    for q in opcion:
        ops = q.get("opciones") or []
        if len(ops) != 4 or len(set(map(str.strip, ops))) < 4 or not 0 <= q.get("correcta", -1) < len(ops):
            malas += 1
    posiciones = {q.get("correcta") for q in opcion}
    vacias = sum(1 for q in quiz if not (q.get("explicacion") or "").strip())
    tarj_malas = sum(1 for c in tarjetas if len((c.get("frente") or "").strip()) < 8 or not (c.get("reverso") or "").strip())
    p = 100.0 - 15 * min(malas, 4) - 10 * min(vacias, 3) - 5 * min(tarj_malas, 4)
    p -= 10 if len(opcion) >= 4 and len(posiciones) == 1 else 0     # todas las respuestas en la misma posición
    p -= 20 if len(quiz) < 5 or len(tarjetas) < 5 else 0
    return {"preguntas": len(quiz), "tarjetas": len(tarjetas), "opciones_mal": malas, "sin_explicacion": vacias,
            "tarjetas_mal": tarj_malas, "respuesta_siempre_igual": int(len(opcion) >= 4 and len(posiciones) == 1),
            "objetivo": max(0, round(p))}


# ------------------------------------------------------------------ registro de resultados
def carpeta(corrida):
    d = MEDICION / corrida
    d.mkdir(parents=True, exist_ok=True)
    return d


def leer_resultados(corrida):
    f = carpeta(corrida) / "resultados.jsonl"
    if not f.exists():
        return []
    ultimos = {}
    for x in f.read_text(encoding="utf-8").splitlines():
        if x.strip():
            r = json.loads(x)
            ultimos[(r["tema"], r["variante"], r["tarea"])] = r      # un reintento reemplaza al fallo anterior
    return list(ultimos.values())


def anotar(corrida, fila):
    with (carpeta(corrida) / "resultados.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps(fila, ensure_ascii=False) + "\n")


def correr(corrida, temas, variantes, tareas=("parte", "ejercicios"), pausa=2.0):
    """Genera y revisa. Reanudable: lo que ya está en `resultados.jsonl` no se repite. Los fallos también se anotan."""
    hechos = {(r["tema"], r["variante"], r["tarea"]) for r in leer_resultados(corrida) if not r["error"]}
    for tid in temas:
        fuentes = leer_fuentes(tid)
        for clave in variantes:
            v = variante(clave)
            leccion = None
            for tarea in tareas:
                if (tid, clave, tarea) in hechos:
                    continue
                if tarea == "parte":
                    r = hacer_parte(v, tid)
                    rev = revisar_parte(r["texto"], fuentes) if not r["error"] else {"objetivo": 0}
                    leccion = r["texto"]
                else:
                    if leccion is None:        # los ejercicios se hacen sobre la parte de esta misma variante
                        prev = [x for x in leer_resultados(corrida)
                                if (x["tema"], x["variante"], x["tarea"]) == (tid, clave, "parte") and not x["error"]]
                        leccion = prev[-1]["texto"] if prev else ""
                    if not leccion:
                        continue
                    r = hacer_ejercicios(v, tid, leccion)
                    try:
                        rev = revisar_ejercicios(json.loads(r["texto"])) if not r["error"] else {"objetivo": 0}
                    except ValueError:
                        rev = {"objetivo": 0}
                anotar(corrida, {"tema": tid, "variante": clave, "tarea": tarea, "cuando": time.strftime("%Y-%m-%d %H:%M"),
                                 **{k: r[k] for k in ("texto", "tin", "tout", "seg", "error", "costo_usd")}, "revision": rev})
                print(f"{tid:10} {clave:12} {tarea:10} {r['seg']:6.1f}s  objetivo={rev['objetivo']:3}"
                      + (f"  ERROR {r['error']}" if r["error"] else ""), flush=True)
                time.sleep(pausa if v["proveedor"] != "local" else 0)


# ------------------------------------------------------------------ juez
CRITERIOS = ("exactitud", "profundidad", "claridad", "ejemplos", "fuentes")
ESQUEMA_JUEZ = {"type": "object", "properties": {"lecciones": {"type": "array", "items": {"type": "object", "properties": {
    "id": {"type": "string"}, **{c: {"type": "integer", "minimum": 1, "maximum": 5} for c in CRITERIOS},
    "errores": {"type": "array", "items": {"type": "string"}}},
    "required": ["id", *CRITERIOS, "errores"]}}}, "required": ["lecciones"]}


def anonimizar(items, semilla):
    """items: [(variante, texto)] → ([(id, texto)], {id: variante}) con orden e identificadores al azar."""
    rnd = random.Random(semilla)
    barajados = list(items)
    rnd.shuffle(barajados)
    letras = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    ids = {letras[i]: v for i, (v, _) in enumerate(barajados)}
    return [(letras[i], t) for i, (_, t) in enumerate(barajados)], ids


def mensajes_juez(tid, anonimas, fuentes):
    t = TEMAS[tid]
    cuerpo = "\n\n".join(f"=== LECCIÓN {i} ===\n{tx}" for i, tx in anonimas)
    prompt = (
        f"Eres un profesor universitario exigente. Tema: «{t['t']}» ({t['area']}). Califica CADA lección de 1 a 5 en:\n"
        "- exactitud: ¿lo que afirma es correcto? Revisa fórmulas, cifras y cada paso de los ejemplos resueltos.\n"
        "- profundidad: ¿explica el porqué o solo enumera?\n- claridad: ¿se entiende a la primera, con buena progresión?\n"
        "- ejemplos: ¿son correctos, concretos y difíciles de forma gradual?\n"
        "- fuentes: ¿cita solo lo que las fuentes dadas respaldan?\n"
        "En «errores» lista cada error factual o de cálculo que encuentres, citando la frase (lista vacía si no hay). "
        "No premies la longitud. Responde solo JSON.\n\nFuentes disponibles:\n"
        + "\n".join(f"- {f['titulo']} — {f['url']}" for f in fuentes["fuentes"])
        + "\n\n" + cuerpo)
    return [{"role": "system", "content": "Eres un evaluador imparcial y riguroso. Respondes solo JSON."},
            {"role": "user", "content": prompt}]


def juzgar(corrida, juez="g35-alto", rondas=2):
    """Califica por tema las lecciones de todas las variantes, anónimas y barajadas, `rondas` veces con otro orden."""
    v = variante(juez)
    res = [r for r in leer_resultados(corrida) if r["tarea"] == "parte" and not r["error"] and r["texto"]]
    previos = {(j["tema"], j["ronda"]) for j in leer_juicios(corrida)}
    for tid in sorted({r["tema"] for r in res}):
        items = [(r["variante"], r["texto"]) for r in res if r["tema"] == tid]
        if len(items) < 2:
            continue
        for ronda in range(rondas):
            if (tid, ronda) in previos:
                continue
            anon, claves = anonimizar(items, f"{corrida}:{tid}:{ronda}")
            r = llamar(v, mensajes_juez(tid, anon, leer_fuentes(tid)), 3500, 0.2, ESQUEMA_JUEZ)
            if r["error"]:
                print(f"juez {tid} ronda {ronda}: ERROR {r['error']}")
                continue
            try:
                import ia
                datos = ia.parsear_json(r["texto"])
            except ValueError as e:
                print(f"juez {tid} ronda {ronda}: respuesta ilegible ({e})")
                continue
            with (carpeta(corrida) / "juicios.jsonl").open("a", encoding="utf-8") as f:
                f.write(json.dumps({"tema": tid, "ronda": ronda, "juez": juez, "claves": claves,
                                    "lecciones": datos.get("lecciones", []), "costo_usd": r["costo_usd"]},
                                   ensure_ascii=False) + "\n")
            print(f"juez {tid} ronda {ronda}: {len(datos.get('lecciones', []))} lecciones calificadas", flush=True)
            time.sleep(2)


def leer_juicios(corrida):
    f = carpeta(corrida) / "juicios.jsonl"
    return [json.loads(x) for x in f.read_text(encoding="utf-8").splitlines() if x.strip()] if f.exists() else []


# ------------------------------------------------------------------ informe
def resumen(resultados, juicios):
    """{variante: métricas medias}. Nada se inventa: sin datos, None."""
    por = {}
    for r in resultados:
        d = por.setdefault(r["variante"], {"n": 0, "fallos": 0, "seg": [], "obj_parte": [], "obj_ej": [], "tin": 0,
                                           "tout": 0, "costo": 0.0, "citas_falsas": 0, "inventados": 0})
        d["n"] += 1
        d["fallos"] += 1 if r["error"] else 0
        d["costo"] += r["costo_usd"]
        d["tin"] += r["tin"]
        d["tout"] += r["tout"]
        if r["error"]:
            continue
        d["seg"].append(r["seg"])
        (d["obj_parte"] if r["tarea"] == "parte" else d["obj_ej"]).append(r["revision"]["objetivo"])
        d["citas_falsas"] += r["revision"].get("citas_falsas", 0)
        d["inventados"] += r["revision"].get("enlaces_inventados", 0)
    juez = {}
    for j in juicios:
        for fila in j["lecciones"]:
            var = j["claves"].get(fila["id"])
            if var:
                juez.setdefault(var, {c: [] for c in CRITERIOS} | {"errores": 0})
                for c in CRITERIOS:
                    juez[var][c].append(fila[c])
                juez[var]["errores"] += len(fila.get("errores", []))
    out = {}
    for var, d in por.items():
        media = lambda xs: round(statistics.mean(xs), 2) if xs else None   # noqa: E731
        jd = juez.get(var)
        out[var] = {"tareas": d["n"], "fallos": d["fallos"], "seg_medio": media(d["seg"]),
                    "objetivo_parte": media(d["obj_parte"]), "objetivo_ejercicios": media(d["obj_ej"]),
                    "citas_falsas": d["citas_falsas"], "enlaces_inventados": d["inventados"],
                    "juez": {c: media(jd[c]) for c in CRITERIOS} if jd else None,
                    "juez_global": media([x for c in CRITERIOS for x in jd[c]]) if jd else None,
                    "errores_detectados": jd["errores"] if jd else None,
                    "tokens_salida": d["tout"], "costo_usd": round(d["costo"], 4)}
    return out


def informe(corrida):
    res, jui = leer_resultados(corrida), leer_juicios(corrida)
    r = resumen(res, jui)
    lineas = [f"# Informe de la corrida «{corrida}»", "",
              f"{len(res)} tareas, {len(jui)} juicios. Costo en USD a precio de lista (el plan gratuito no cobra).", "",
              "| Variante | Fallos | Segundos | Objetivo (parte) | Objetivo (ejercicios) | Juez (1-5) | Errores del juez | Citas falsas | Enlaces inventados | Costo USD |",
              "|---|---|---|---|---|---|---|---|---|---|"]
    for var, d in sorted(r.items(), key=lambda kv: -(kv[1]["juez_global"] or 0)):
        lineas.append(f"| {var} | {d['fallos']}/{d['tareas']} | {d['seg_medio']} | {d['objetivo_parte']} | "
                      f"{d['objetivo_ejercicios']} | {d['juez_global']} | {d['errores_detectados']} | {d['citas_falsas']} | "
                      f"{d['enlaces_inventados']} | {d['costo_usd']} |")
    texto = "\n".join(lineas) + "\n"
    (carpeta(corrida) / "informe.md").write_text(texto, encoding="utf-8")
    return texto


# ------------------------------------------------------------------ lectura ciega
def preparar_ciega(corrida, n_temas=4, semilla=7):
    """Archivos para leer SIN saber qué modelo escribió cada lección: `ciega/<tema>.md` y la clave aparte."""
    res = [r for r in leer_resultados(corrida) if r["tarea"] == "parte" and not r["error"] and r["texto"]]
    temas = sorted({r["tema"] for r in res})
    random.Random(semilla).shuffle(temas)
    clave = {}
    d = carpeta(corrida) / "ciega"
    d.mkdir(exist_ok=True)
    for tid in temas[:n_temas]:
        items = [(r["variante"], r["texto"]) for r in res if r["tema"] == tid]
        anon, ids = anonimizar(items, f"ciega:{corrida}:{tid}")
        clave[tid] = ids
        (d / f"{tid}.md").write_text(
            f"# {TEMAS[tid]['t']}\n\nLee cada lección y anota cuál es la mejor, cuál la peor y si alguna tiene un error.\n\n"
            + "\n\n---\n\n".join(f"## Lección {i}\n\n{tx}" for i, tx in anon), encoding="utf-8")
    (carpeta(corrida) / "clave_ciega.json").write_text(json.dumps(clave, ensure_ascii=False, indent=1), encoding="utf-8")
    return sorted(clave)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("orden", choices=["congelar", "correr", "juzgar", "informe", "ciega"])
    ap.add_argument("--corrida", default=time.strftime("%Y-%m-%d"))
    ap.add_argument("--temas", default=",".join(TEMAS))
    ap.add_argument("--variantes", default="local,g38-bajo,g38-medio,g38-alto")
    ap.add_argument("--tareas", default="parte,ejercicios")
    ap.add_argument("--juez", default="g35-alto")
    ap.add_argument("--n", type=int, default=4)
    ap.add_argument("--pausa", type=float, default=2.0, help="segundos entre pedidos a la API (el plan gratuito tiene límite por minuto)")
    a = ap.parse_args(argv)
    temas = [t for t in a.temas.split(",") if t]
    if a.orden == "congelar":
        congelar(temas)
    elif a.orden == "correr":
        correr(a.corrida, temas, a.variantes.split(","), a.tareas.split(","), a.pausa)
    elif a.orden == "juzgar":
        juzgar(a.corrida, a.juez)
    elif a.orden == "informe":
        print(informe(a.corrida))
    else:
        print("lecciones para leer:", ", ".join(preparar_ciega(a.corrida, a.n)))


if __name__ == "__main__":
    main()
