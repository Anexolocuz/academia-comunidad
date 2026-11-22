#!/usr/bin/env python3
"""Valida el currículo (curriculo/*.json) sin IA ni red: ids únicos, prerrequisitos que existen, sin ciclos,
niveles de 1 a 5 en cada área (salvo idiomas que empiezan más arriba a propósito) y temas casi repetidos entre áreas.
Uso: python3 pruebas/validar_curriculo.py [base.sqlite para incluir las áreas propias de las personas]
Sale con código 1 si hay errores (los temas parecidos solo se avisan: a veces el mismo tema se ve desde otra área)."""
import difflib
import json
import sqlite3
import sys
import unicodedata
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent


def norm(t):
    t = unicodedata.normalize("NFKD", t.split("|")[0].lower())
    return "".join(c for c in t if not unicodedata.combining(c)).strip()


def main():
    areas = {}
    for f in sorted((RAIZ / "curriculo").glob("*.json")):
        a = json.loads(f.read_text(encoding="utf-8"))
        areas[a["id"]] = a
    extra = {}
    if len(sys.argv) > 1:
        con = sqlite3.connect(f"file:{sys.argv[1]}?mode=ro", uri=True)
        for i, d in con.execute("SELECT id, datos FROM area_extra"):
            extra[i] = json.loads(d)
    errores, avisos = [], []
    refs = {f"{a['id']}.{m['id']}" for a in areas.values() for m in a["modulos"]}
    grafo = {}
    for a in areas.values():
        ids = [m["id"] for m in a["modulos"]]
        if len(ids) != len(set(ids)):
            errores.append(f"{a['id']}: módulos con id repetido")
        niveles = sorted({m["nivel"] for m in a["modulos"]})
        if not a.get("idioma") and niveles != [1, 2, 3, 4, 5]:
            errores.append(f"{a['id']}: niveles {niveles} (deben ir de 1 a 5, de lo básico a la frontera)")
        for u in [r.get("u", "") for r in a.get("recursos", [])]:
            if not u.startswith("https://"):
                errores.append(f"{a['id']}: recurso sin https: {u}")
        for m in a["modulos"]:
            ref = f"{a['id']}.{m['id']}"
            pres = [p if "." in p else f"{a['id']}.{p}" for p in m.get("pre", [])]
            for p in pres:
                if p not in refs:
                    errores.append(f"{ref}: prerrequisito inexistente {p}")
            grafo[ref] = pres
            nivel_pre = {q: next(x["nivel"] for x in areas[q.split('.')[0]]["modulos"] if x["id"] == q.split('.')[1])
                         for q in pres if q in refs}
            for q, n in nivel_pre.items():
                if q.split(".")[0] == a["id"] and n > m["nivel"]:
                    avisos.append(f"{ref} (nivel {m['nivel']}) requiere {q} de nivel {n}")
    estado = {}
    def visitar(n, pila):
        if estado.get(n) == 1:
            errores.append("ciclo de prerrequisitos: " + " → ".join(pila + [n]))
            return
        if estado.get(n) == 2:
            return
        estado[n] = 1
        for p in grafo.get(n, []):
            visitar(p, pila + [n])
        estado[n] = 2
    for n in grafo:
        visitar(n, [])
    titulos = [(norm(t), f"{a['id']}.{m['id']}", t.split("|")[0]) for a in list(areas.values()) + list(extra.values())
               for m in a.get("modulos", []) for t in m.get("temas", []) if isinstance(t, str)]
    for i, (x, rx, tx) in enumerate(titulos):
        for y, ry, ty in titulos[i + 1:]:
            if rx.split(".")[0] != ry.split(".")[0] and len(x) > 12 and difflib.SequenceMatcher(None, x, y).ratio() > 0.9:
                avisos.append(f"tema parecido: «{tx}» ({rx}) ≈ «{ty}» ({ry})")
    for e in errores:
        print("✗", e)
    for w in avisos:
        print("⚠", w)
    print(f"{len(areas)} áreas del currículo ({len(extra)} propias revisadas); {len(errores)} errores, {len(avisos)} avisos")
    return 1 if errores else 0


if __name__ == "__main__":
    sys.exit(main())
