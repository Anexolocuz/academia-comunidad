"""Lectura medida de verdad (2026-10-11): cuánto del texto se leyó, a qué velocidad y si se terminó.

La interfaz (web/app.js, «LECT») parte cada lección/noticia en bloques (párrafos, filas, fórmulas), los clasifica
(«es», el idioma estudiado «de»/«en»/«ja»…, o «formulas») y, mientras hay actividad real, reparte el tiempo
entre los bloques que están en pantalla. Un bloque cuenta como leído cuando estuvo en pantalla al menos lo que
tardarías en leerlo a 3× tu velocidad. Cada sesión de lectura llega aquí (se actualiza cada minuto).
"""
import json
import statistics
import time

from base import db, ejecutar, fila, filas

DIA = 86400
WPM_INICIAL = 180      # hasta tener datos propios (lectura de estudio en español)
SEG_FORMULA_INICIAL = 20
NOMBRE_CAT = {"es": "Español", "en": "Inglés", "de": "Alemán", "fr": "Francés", "it": "Italiano", "pt": "Portugués",
              "ja": "Japonés", "zh": "Chino", "ko": "Coreano", "ru": "Ruso", "formulas": "Fórmulas"}
NOMBRE_METODO = {"leccion": "📖 Lecciones", "noticias": "🌍 Noticias", "lectura": "📚 Lecturas", "tutor": "💬 Tutor"}


def iniciar():
    db().executescript("""CREATE TABLE IF NOT EXISTS lectura (
        id TEXT PRIMARY KEY, usuario TEXT, tema TEXT, area TEXT, metodo TEXT, idioma TEXT,
        inicio REAL, fin REAL, segundos REAL, avance REAL, palabras INTEGER, formulas INTEGER,
        cats TEXT, acciones INTEGER, audio INTEGER);
        CREATE INDEX IF NOT EXISTS lectura_usuario ON lectura(usuario, fin);""")
    db().commit()


def guardar(usuario, d):
    """Crea o actualiza una sesión de lectura (la interfaz la reenvía cada minuto con los totales)."""
    sid = str(d.get("id") or "")[:40]
    if not sid:
        return
    previa = fila("SELECT usuario FROM lectura WHERE id=?", (sid,))
    if previa and previa["usuario"] != usuario:   # cada perfil solo toca lo suyo
        return
    cats = {}
    for k, v in (d.get("cats") or {}).items():
        cats[str(k)[:12]] = {"seg": max(0.0, float(v.get("seg", 0))), "palabras": max(0, int(v.get("palabras", 0))),
                             "formulas": max(0, int(v.get("formulas", 0)))}
    ahora = time.time()
    vals = (usuario, d.get("tema"), d.get("area"), d.get("metodo"), d.get("idioma"),
            float(d.get("inicio") or ahora), ahora, max(0.0, float(d.get("segundos", 0))),
            min(1.0, max(0.0, float(d.get("avance", 0)))), int(d.get("palabras", 0)), int(d.get("formulas", 0)),
            json.dumps(cats), int(d.get("acciones", 0)), int(d.get("audio", 0)))
    if previa:
        ejecutar("""UPDATE lectura SET usuario=?, tema=?, area=?, metodo=?, idioma=?, inicio=?, fin=?, segundos=?,
                    avance=?, palabras=?, formulas=?, cats=?, acciones=?, audio=? WHERE id=?""", vals + (sid,))
    else:
        ejecutar("""INSERT INTO lectura(usuario,tema,area,metodo,idioma,inicio,fin,segundos,avance,palabras,formulas,
                    cats,acciones,audio,id) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", vals + (sid,))


def _sesiones(usuario, desde):
    out = []
    for r in filas("SELECT * FROM lectura WHERE usuario=? AND fin>? AND segundos>=20", (usuario, desde)):
        r = dict(r)
        r["cats"] = json.loads(r["cats"] or "{}")
        out.append(r)
    return out


def velocidades(usuario, dias=60):
    """Palabras por minuto por idioma y segundos por fórmula (ponderado por tiempo; necesita ≥1 min por categoría)."""
    acum = {}
    for s in _sesiones(usuario, time.time() - dias * DIA):
        for k, v in s["cats"].items():
            a = acum.setdefault(k, {"seg": 0.0, "palabras": 0, "formulas": 0})
            for x in a:
                a[x] += v.get(x, 0)
    out = {}
    for k, a in acum.items():
        if a["seg"] < 60:
            continue
        if k == "formulas":
            out[k] = {"seg_formula": round(a["seg"] / a["formulas"]) if a["formulas"] else None,
                      "min": round(a["seg"] / 60), "formulas": a["formulas"]}
        else:
            out[k] = {"wpm": round(a["palabras"] / a["seg"] * 60) if a["palabras"] else None,
                      "min": round(a["seg"] / 60), "palabras": a["palabras"]}
    return out


def wpm_base(usuario):
    """Velocidad propia en español (para el umbral de inactividad y para corregir el historial)."""
    es = velocidades(usuario).get("es", {})
    if not es.get("wpm") or es.get("min", 0) < 5:   # con menos de 5 min leídos la medida aún no es fiable
        return WPM_INICIAL
    return max(80, min(600, es["wpm"]))


def resumen(usuario, dias=30):
    ses = _sesiones(usuario, time.time() - dias * DIA)
    vel = velocidades(usuario)
    base = wpm_base(usuario)
    filas_vel = []
    for k, v in sorted(vel.items(), key=lambda kv: -kv[1]["min"]):
        nombre = NOMBRE_CAT.get(k, k)
        if k == "formulas":
            filas_vel.append({"cat": k, "nombre": "🧮 " + nombre, "valor": v["seg_formula"], "unidad": "s por fórmula",
                              "min": v["min"], "n": v["formulas"]})
        else:
            filas_vel.append({"cat": k, "nombre": "🔤 Texto en " + nombre.lower(), "valor": v["wpm"], "unidad": "palabras/min",
                              "min": v["min"], "n": v["palabras"]})
    por_metodo = {}
    completas = 0
    for s in ses:
        # completa = llegó al final Y no fue un vistazo (no más rápido que 2,5× su velocidad)
        leidas = sum(v.get("palabras", 0) for k, v in s["cats"].items() if k != "formulas")
        rapido = s["segundos"] and leidas / s["segundos"] * 60 > base * 2.5
        s["completa"] = s["avance"] >= 0.9 and not rapido
        completas += s["completa"]
        m = por_metodo.setdefault(s["metodo"] or "leccion", {"sesiones": 0, "completas": 0, "min": 0.0, "avance": 0.0})
        m["sesiones"] += 1
        m["completas"] += s["completa"]
        m["min"] += s["segundos"] / 60
        m["avance"] += s["avance"]
    metodos = [{"metodo": k, "nombre": NOMBRE_METODO.get(k, k), "sesiones": m["sesiones"], "completas": m["completas"],
                "min": round(m["min"]),
                # velocidad de avance: % del texto recorrido por cada 10 min de lectura activa
                "avance_10min": round(m["avance"] / m["min"] * 10 * 100) if m["min"] >= 1 else None}
               for k, m in por_metodo.items()]
    recientes = sorted(ses, key=lambda s: -s["fin"])[:8]
    return {"velocidades": filas_vel, "metodos": metodos, "sesiones": len(ses), "completas": completas,
            "wpm_base": base, "propia": vel.get("es", {}).get("min", 0) >= 5,
            "recientes": [{"tema": s["tema"], "metodo": s["metodo"], "fin": s["fin"], "min": round(s["segundos"] / 60, 1),
                           "avance": round(s["avance"] * 100), "completa": s["completa"]} for s in recientes]}
