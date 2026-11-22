#!/usr/bin/env python3
"""Importador opcional del paquete de contenidos preparados para la Academia.

No toca tus datos existentes salvo que pases `--sobrescribir`.
Uso:
  python3 contenidos/importar.py --listar
  python3 contenidos/importar.py
  python3 contenidos/importar.py --area ciberseguridad sistemas
"""
from __future__ import annotations

import argparse
import gzip
import json
import os
import sqlite3
import sys
import time
from pathlib import Path

CONTENIDOS = Path(__file__).resolve().parent
RAIZ = CONTENIDOS.parent


def _resolver_usuario(db: sqlite3.Connection, expl: str | None, datos_dir: Path) -> str:
    if expl:
        return expl
    cfg_path = datos_dir / "configuracion.json"
    if cfg_path.exists():
        try:
            cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
            if cfg.get("usuario_local"):
                return str(cfg["usuario_local"])
            perm = cfg.get("usuarios_permitidos") or []
            if perm:
                return str(perm[0])
        except (OSError, ValueError):
            pass
    fila = db.execute("SELECT usuario FROM perfil ORDER BY creado LIMIT 1").fetchone()
    if fila and fila[0]:
        return str(fila[0])
    return "local"


def listar() -> int:
    idx_path = CONTENIDOS / "indice.json"
    if not idx_path.exists():
        print("No se encontró contenidos/indice.json")
        return 1
    idx = json.loads(idx_path.read_text(encoding="utf-8"))
    print(f"Áreas propias incluidas: {len(idx.get('areas_propias', []))}")
    for a in idx.get("areas_propias", []):
        print(f"  • {a['id']}: {a.get('nombre')} ({a.get('grupo')})")
    print(f"\nRutas vivas enriquecidas: {len(idx.get('rutas_vivas', []))}")
    print("  " + ", ".join(idx.get("rutas_vivas", [])))
    print(f"\nLecciones preparadas ({idx.get('total_lecciones', 0)} en total):")
    for a in idx.get("areas_con_lecciones", []):
        print(f"  • {a['area']:<24} {a['total']:>3} lecciones")
    return 0


def importar(args: argparse.Namespace) -> int:
    datos_dir = Path(args.datos or os.environ.get("ACADEMIA_DATOS") or (RAIZ / "datos"))
    datos_dir.mkdir(parents=True, exist_ok=True)
    os.environ["ACADEMIA_DATOS"] = str(datos_dir)
    sys.path.insert(0, str(RAIZ / "app"))
    import base  # esquema oficial de academia.db

    db = sqlite3.connect(str(datos_dir / "academia.db"))
    db.executescript(base.ESQUEMA)
    db.executescript("""
        CREATE TABLE IF NOT EXISTS area_extra (id TEXT, usuario TEXT, datos TEXT, creado REAL, PRIMARY KEY (id, usuario));
        CREATE TABLE IF NOT EXISTS ruta_extra (usuario TEXT, area TEXT, datos TEXT, actualizado REAL, PRIMARY KEY (usuario, area));
    """)
    usuario = _resolver_usuario(db, args.usuario, datos_dir)
    ahora = time.time()
    filtro_areas = set(args.area or [])

    rutas_imp, extras_imp, lecc_imp, lecc_omit = 0, 0, 0, 0

    if not args.sin_rutas:
        ap_path = CONTENIDOS / "rutas" / "areas_propias.json"
        if ap_path.exists():
            for a in json.loads(ap_path.read_text(encoding="utf-8")):
                if filtro_areas and a["id"] not in filtro_areas:
                    continue
                existe = db.execute("SELECT 1 FROM area_extra WHERE usuario=? AND id=?", (usuario, a["id"])).fetchone()
                if existe and not args.sobrescribir:
                    continue
                reg = dict(a, usuario=usuario)
                db.execute(
                    "INSERT INTO area_extra(id, usuario, datos, creado) VALUES(?,?,?,?) "
                    "ON CONFLICT(id, usuario) DO UPDATE SET datos=excluded.datos",
                    (a["id"], usuario, json.dumps(reg, ensure_ascii=False), ahora),
                )
                rutas_imp += 1

        rv_path = CONTENIDOS / "rutas" / "rutas_vivas.json"
        if rv_path.exists():
            for r in json.loads(rv_path.read_text(encoding="utf-8")):
                if filtro_areas and r["area"] not in filtro_areas:
                    continue
                existe = db.execute("SELECT 1 FROM ruta_extra WHERE usuario=? AND area=?", (usuario, r["area"])).fetchone()
                if existe and not args.sobrescribir:
                    continue
                db.execute(
                    "INSERT INTO ruta_extra(usuario, area, datos, actualizado) VALUES(?,?,?,?) "
                    "ON CONFLICT(usuario, area) DO UPDATE SET datos=excluded.datos, actualizado=excluded.actualizado",
                    (usuario, r["area"], json.dumps(r["datos"], ensure_ascii=False), ahora),
                )
                extras_imp += 1

    if not args.sin_lecciones:
        lecc_dir = CONTENIDOS / "lecciones"
        for p in sorted(lecc_dir.glob("*.json.gz")):
            area = p.name[:-8]
            if filtro_areas and area not in filtro_areas:
                continue
            with gzip.open(p, "rt", encoding="utf-8") as f:
                pack = json.load(f)
            for l in pack.get("lecciones", []):
                existe = db.execute("SELECT 1 FROM leccion WHERE usuario=? AND tema=?", (usuario, l["tema"])).fetchone()
                if existe and not args.sobrescribir:
                    lecc_omit += 1
                    continue
                db.execute(
                    """INSERT INTO leccion(usuario,tema,contenido,ejercicios,fuentes,modelo,creado,version,completa,plan)
                       VALUES(?,?,?,?,?,?,?,?,?,NULL)
                       ON CONFLICT(usuario,tema) DO UPDATE SET contenido=excluded.contenido,
                       ejercicios=excluded.ejercicios, fuentes=excluded.fuentes, modelo=excluded.modelo,
                       creado=excluded.creado, version=excluded.version, completa=excluded.completa, plan=NULL""",
                    (
                        usuario, l["tema"], l["contenido"],
                        json.dumps(l["ejercicios"], ensure_ascii=False) if l.get("ejercicios") is not None else None,
                        json.dumps(l.get("fuentes") or [], ensure_ascii=False),
                        l.get("modelo") or "comunidad", ahora, int(l.get("version") or 3), int(l.get("completa") or 1),
                    ),
                )
                lecc_imp += 1

    db.commit()
    db.close()
    print(f"✓ Importado para usuario «{usuario}»: {rutas_imp} áreas propias, {extras_imp} rutas vivas, {lecc_imp} lecciones nuevas ({lecc_omit} ya existían).")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Importa rutas y lecciones ya preparadas a la Academia.")
    ap.add_argument("--listar", action="store_true", help="Muestra las rutas y lecciones incluidas sin tocar la base")
    ap.add_argument("--usuario", help="Cuenta/perfil destino en academia.db (por defecto se detecta solo)")
    ap.add_argument("--datos", help="Carpeta datos/ destino (por defecto ACADEMIA_DATOS o ./datos)")
    ap.add_argument("--area", nargs="+", help="Importar solo una o varias áreas concretas")
    ap.add_argument("--sin-rutas", action="store_true", help="Omitir rutas propias y rutas vivas")
    ap.add_argument("--sin-lecciones", action="store_true", help="Omitir lecciones")
    ap.add_argument("--sobrescribir", action="store_true", help="Reemplazar rutas/lecciones si ya existían")
    args = ap.parse_args()
    return listar() if args.listar else importar(args)


if __name__ == "__main__":
    raise SystemExit(main())
