"""Currículo: áreas → módulos → temas, dominio, desbloqueo y recomendación.

Ids: área "mecatronica", módulo "mecatronica.control", tema "mecatronica.control.3".
Un módulo puede exigir módulos de otra área ("matematicas.edo").
Las áreas de los objetivos personales se guardan en la base (`area_extra`).
"""
import json
import re
import time
from pathlib import Path

from base import ejecutar, fila, filas

CARPETA = Path(__file__).resolve().parent.parent / "curriculo"
NIVELES = {1: "Fundamentos", 2: "Intermedio", 3: "Avanzado", 4: "Experto", 5: "Horizonte"}
UMBRAL_DESBLOQUEO = 0.6
UMBRAL_DOMINIO = 0.8

ejecutar("""CREATE TABLE IF NOT EXISTS area_extra (
  id TEXT PRIMARY KEY, usuario TEXT, datos TEXT, creado REAL)""")
ejecutar("""CREATE TABLE IF NOT EXISTS objetivo (
  id INTEGER PRIMARY KEY AUTOINCREMENT, usuario TEXT, titulo TEXT, descripcion TEXT,
  plan TEXT, estado TEXT DEFAULT 'activo', creado REAL)""")

_AREAS = {}


def _id(x):
    """Identificadores seguros (van dentro de enlaces y atributos HTML): las áreas creadas por la IA no se confían."""
    return re.sub(r"[^a-z0-9_.]", "_", str(x).lower())


def _normalizar(a):
    a["id"] = _id(a["id"])
    if not re.fullmatch(r"#[0-9a-fA-F]{3,8}", str(a.get("color", ""))):
        a["color"] = "#636e72"
    for m in a["modulos"]:
        m["id"] = _id(m["id"]).replace(".", "_")
        m["pre"] = [_id(p) for p in m.get("pre", [])]
        m["ref"] = f'{a["id"]}.{m["id"]}'
        m["area"] = a["id"]
        m["pre"] = [p if "." in p else f'{a["id"]}.{p}' for p in m.get("pre", [])]
        m["temas_obj"] = []
        for i, s in enumerate(m["temas"]):
            t, _, d = s.partition("|")
            m["temas_obj"].append({"id": f'{m["ref"]}.{i}', "t": t.strip(), "d": d.strip(),
                                   "modulo": m["ref"], "area": a["id"], "nivel": m["nivel"], "i": i})
    return a


def cargar():
    _AREAS.clear()
    for f in sorted(CARPETA.glob("*.json")):
        a = json.loads(f.read_text(encoding="utf-8"))
        _AREAS[a["id"]] = _normalizar(a)
    return _AREAS


def areas(usuario=None):
    if not _AREAS:
        cargar()
    out = dict(_AREAS)
    if usuario:
        for r in filas("SELECT id, datos FROM area_extra WHERE usuario=?", (usuario,)):
            out[r["id"]] = _normalizar(json.loads(r["datos"]))
    return out


def areas_de(usuario):
    """Áreas que son de ESTA persona (lo único que ve en todas las vistas): las que tiene en Ajustes,
    las que creó (áreas completas y objetivos), las que usan sus metas activas y aquellas en las que
    ya estudió algo. No hay catálogo: las áreas aparecen a medida que crea metas o áreas."""
    r = fila("SELECT datos FROM perfil WHERE usuario=?", (usuario,))
    ids = set(json.loads(r["datos"]).get("pesos", {})) if r else set()
    ids |= {x["id"] for x in filas("SELECT id FROM area_extra WHERE usuario=?", (usuario,))}
    ids |= areas_de_metas(usuario)
    ids |= {x["tema"].split(".")[0] for x in filas("SELECT tema FROM avance WHERE usuario=?", (usuario,))}
    return ids


def areas_de_metas(usuario):
    return {ref.split(".")[0] for ref in refs_objetivos(usuario)}


def peso(a, pesos, usuario, metas=()):
    """Prioridad efectiva: la de Ajustes; si aún no la eligió, 2 para sus áreas propias y las de sus metas."""
    return pesos.get(a["id"], 2 if a.get("usuario") == usuario or a["id"] in metas else 0)


def modulo(ref, usuario=None):
    a, _, m = ref.rpartition(".")
    area = areas(usuario).get(a)
    if not area:
        return None
    return next((x for x in area["modulos"] if x["id"] == m), None)


def tema(tid, usuario=None):
    ref, _, i = tid.rpartition(".")
    m = modulo(ref, usuario)
    if not m or not i.isdigit() or int(i) >= len(m["temas_obj"]):
        return None
    return m["temas_obj"][int(i)]


# ------------------------------------------------------------------ dominio
def avances(usuario):
    return {r["tema"]: r for r in filas("SELECT * FROM avance WHERE usuario=?", (usuario,))}


def dominio_tema(av):
    """0..1. Visto = 0.25; el quiz y la explicación Feynman suben el resto."""
    if not av:
        return 0.0
    if av["estado"] in ("dominado", "probado"):
        return 1.0
    q, f = av.get("quiz") or 0, av.get("feynman") or 0
    if av["estado"] == "visto" or q or f:
        return min(1.0, 0.25 + 0.5 * q + 0.25 * f)
    return 0.0


def dominio_modulo(m, avs):
    ts = m["temas_obj"]
    return sum(dominio_tema(avs.get(t["id"])) for t in ts) / len(ts) if ts else 0


def desbloqueado(m, avs, usuario=None):
    for p in m["pre"]:
        pm = modulo(p, usuario)
        if pm and dominio_modulo(pm, avs) < UMBRAL_DESBLOQUEO:
            return False
    return True


def marcar(usuario, tid, **campos):
    av = fila("SELECT * FROM avance WHERE usuario=? AND tema=?", (usuario, tid)) or {}
    nuevo = {"estado": av.get("estado", "nuevo"), "quiz": av.get("quiz"),
             "feynman": av.get("feynman"), "visto": av.get("visto")}
    for k, v in campos.items():
        if k in ("quiz", "feynman") and v is not None:
            v = max(v, nuevo.get(k) or 0)  # se guarda el mejor intento
        nuevo[k] = v
    if nuevo["estado"] == "nuevo" and (nuevo.get("visto") or nuevo.get("quiz")):
        nuevo["estado"] = "visto"
    if nuevo["estado"] == "visto" and (nuevo.get("quiz") or 0) >= UMBRAL_DOMINIO:
        nuevo["estado"] = "dominado"
    ejecutar("""INSERT INTO avance(usuario,tema,estado,quiz,feynman,visto,actualizado)
                VALUES(?,?,?,?,?,?,?) ON CONFLICT(usuario,tema) DO UPDATE SET
                estado=excluded.estado, quiz=excluded.quiz, feynman=excluded.feynman,
                visto=excluded.visto, actualizado=excluded.actualizado""",
             (usuario, tid, nuevo["estado"], nuevo["quiz"], nuevo["feynman"], nuevo["visto"], time.time()))
    return nuevo


def mapa(usuario):
    """Todo el currículo con dominio y bloqueo, para la pestaña Ruta."""
    avs = avances(usuario)
    out = []
    for a in areas(usuario).values():
        mods = []
        for m in a["modulos"]:
            mods.append({"ref": m["ref"], "t": m["t"], "nivel": m["nivel"], "pre": m["pre"],
                         "dominio": round(dominio_modulo(m, avs), 3),
                         "abierto": desbloqueado(m, avs, usuario),
                         "temas": [{"id": t["id"], "t": t["t"], "d": t["d"],
                                    "estado": (avs.get(t["id"]) or {}).get("estado", "nuevo"),
                                    "dominio": round(dominio_tema(avs.get(t["id"])), 2)}
                                   for t in m["temas_obj"]]})
        dom = sum(x["dominio"] * len(x["temas"]) for x in mods) / max(1, sum(len(x["temas"]) for x in mods))
        out.append({"id": a["id"], "nombre": a["nombre"], "icono": a.get("icono"), "color": a.get("color"),
                    "grupo": a.get("grupo"), "descripcion": a.get("descripcion"), "idioma": a.get("idioma"),
                    "recursos": a.get("recursos", []), "dominio": round(dom, 3), "modulos": mods,
                    "objetivo": a.get("objetivo"), "personal": bool(a.get("usuario"))})
    return out


# ------------------------------------------------------------- recomendación
def frontera(area, avs, usuario):
    """Siguientes temas por estudiar en un área, en orden de nivel."""
    out = []
    for m in sorted(area["modulos"], key=lambda m: m["nivel"]):
        if not desbloqueado(m, avs, usuario) or dominio_modulo(m, avs) >= UMBRAL_DOMINIO:
            continue
        for t in m["temas_obj"]:
            av = avs.get(t["id"])
            if not av or av["estado"] == "nuevo":
                out.append(t)
                break
        if len(out) >= 3:
            break
    return out


def ultimo_estudio_por_area(usuario):
    return {r["area"]: r["f"] for r in filas(
        "SELECT area, MAX(fecha) f FROM actividad WHERE usuario=? AND area IS NOT NULL GROUP BY area",
        (usuario,))}


def refs_objetivos(usuario):
    refs = set()
    for o in filas("SELECT plan FROM objetivo WHERE usuario=? AND estado='activo'", (usuario,)):
        try:
            refs.update(json.loads(o["plan"]).get("modulos", []))
        except (ValueError, TypeError):
            pass
    return refs


def recomendar(usuario, perfil, n=3, excluir=()):
    """Elige n temas nuevos intercalando áreas (interleaving): pesa la
    prioridad que diste a cada área, cuánto hace que no la tocas, y si sirve
    a uno de tus objetivos. Reserva un cupo para un idioma si hay activos.
    Con n grande (sesiones extra) toma también el 2.º y 3.er frente de cada área."""
    avs = avances(usuario)
    pesos = perfil.get("pesos", {})
    ultimos = ultimo_estudio_por_area(usuario)
    obj = refs_objetivos(usuario)
    ahora = time.time()
    excluir = set(excluir)
    cand = []
    metas = areas_de_metas(usuario)
    for a in areas(usuario).values():
        # áreas personales y las de tus metas: prioridad 2 si aún no la elegiste en Ajustes
        w = peso(a, pesos, usuario, metas)
        if w <= 0:
            continue
        fr = [t for t in frontera(a, avs, usuario) if t["id"] not in excluir]
        dias = (ahora - ultimos.get(a["id"], ahora - 7 * 86400)) / 86400
        for k, t in enumerate(fr):
            bonus = 2.0 if t["modulo"] in obj else 1.0
            cand.append((w * bonus * (1 + min(dias, 14)) / (1 + 2 * k), a.get("grupo") == "Idiomas", t))
    cand.sort(key=lambda x: -x[0])
    elegidos, areas_usadas, idiomas = [], set(), 0
    for ronda in (0, 1):   # ronda 0: un tema por área y máx. 1 idioma; ronda 1: rellenar
        for c in cand:
            if len(elegidos) >= n:
                break
            t = c[2]
            if t in elegidos:
                continue
            if ronda == 0 and (t["area"] in areas_usadas or (c[1] and idiomas >= max(1, n // 3))):
                continue
            elegidos.append(t)
            areas_usadas.add(t["area"])
            idiomas += c[1]
    # que haya un idioma si hay alguno activo y caben 2+
    if n >= 2 and not any(c[1] for c in cand if c[2] in elegidos):
        idioma = next((c for c in cand if c[1]), None)
        if idioma and elegidos:
            elegidos[-1] = idioma[2]
    return elegidos


# ------------------------------------------------------------------ objetivos
def catalogo_modulos(usuario=None):
    """Lista compacta para que la IA elija módulos existentes."""
    return [(m["ref"], f'{a["nombre"]} › {m["t"]} (nivel {m["nivel"]})')
            for a in areas(usuario).values() if not a.get("objetivo") for m in a["modulos"]]


def cierre_prerrequisitos(refs, usuario=None):
    """Todos los módulos necesarios, incluidos los prerrequisitos de los
    prerrequisitos, ordenados de lo más básico a lo más avanzado."""
    vistos, orden = set(), []

    def visitar(r):
        if r in vistos:
            return
        vistos.add(r)
        m = modulo(r, usuario)
        if not m:
            return
        for p in m["pre"]:
            visitar(p)
        orden.append(r)

    for r in refs:
        visitar(r)
    return orden


def estado_objetivo(usuario, o):
    plan = json.loads(o["plan"] or "{}")
    avs = avances(usuario)
    refs = cierre_prerrequisitos(plan.get("modulos", []) + plan.get("extra", []), usuario)
    pasos = []
    for r in refs:
        m = modulo(r, usuario)
        if not m:
            continue
        d = dominio_modulo(m, avs)
        hechos = [t["t"] for t in m["temas_obj"] if dominio_tema(avs.get(t["id"])) >= UMBRAL_DOMINIO]
        faltan = [{"id": t["id"], "t": t["t"]} for t in m["temas_obj"]
                  if dominio_tema(avs.get(t["id"])) < UMBRAL_DOMINIO]
        pasos.append({"ref": r, "t": m["t"], "nivel": m["nivel"], "nivel_nombre": NIVELES[m["nivel"]],
                      "area": modulo_area_nombre(r, usuario), "dominio": round(d, 3),
                      "estado": "completo" if d >= UMBRAL_DOMINIO else ("en curso" if d > 0 else "faltante"),
                      "abierto": desbloqueado(m, avs, usuario), "directo": r in plan.get("modulos", []) + plan.get("extra", []),
                      "por_que": plan.get("razones", {}).get(r, ""), "hechos": hechos, "faltan": faltan})
    pasos.sort(key=lambda p: (p["nivel"], refs.index(p["ref"])))
    total = sum(len(p["hechos"]) + len(p["faltan"]) for p in pasos)
    hechos = sum(len(p["hechos"]) for p in pasos)
    return {"id": o["id"], "titulo": o["titulo"], "descripcion": o["descripcion"], "estado": o["estado"],
            "resumen": plan.get("resumen", ""), "creado": o["creado"], "pasos": pasos,
            "progreso": round(hechos / total, 3) if total else 0, "temas_total": total, "temas_hechos": hechos}


def modulo_area_nombre(ref, usuario=None):
    a = areas(usuario).get(ref.rpartition(".")[0])
    return a["nombre"] if a else ""
