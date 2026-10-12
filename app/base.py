"""Base de datos SQLite de la Academia.

Todo lo del usuario va con la columna `usuario` (su cuenta de Tailscale), así
cada persona del tailnet lleva su propio progreso. Las lecciones también son de
cada persona (se escriben con su perfil), así cada cuenta empieza en blanco.
"""
import json
import os
import sqlite3
import threading
import time
from pathlib import Path

from config import DATOS, RAIZ  # noqa: E402  (ACADEMIA_DATOS = otra carpeta, p. ej. pruebas aisladas)
RUTA_DB = DATOS / "academia.db"

ESQUEMA = """
PRAGMA journal_mode=WAL;
CREATE TABLE IF NOT EXISTS perfil (
  usuario TEXT PRIMARY KEY,
  datos TEXT NOT NULL,             -- JSON: metas, minutos/día, pesos por área, idiomas...
  creado REAL, actualizado REAL
);
CREATE TABLE IF NOT EXISTS leccion (
  usuario TEXT NOT NULL DEFAULT '', -- de quién es (se escribe con su perfil)
  tema TEXT NOT NULL,              -- id del tema del currículo (area.modulo.n)
  contenido TEXT NOT NULL,         -- markdown
  ejercicios TEXT,                 -- JSON {quiz:[...], tarjetas:[...]}
  fuentes TEXT,                    -- JSON [{titulo,url}]
  modelo TEXT, creado REAL,
  version INTEGER DEFAULT 1, completa INTEGER DEFAULT 1, plan TEXT,
  PRIMARY KEY (usuario, tema)
);
CREATE TABLE IF NOT EXISTS avance (
  usuario TEXT, tema TEXT,
  estado TEXT DEFAULT 'nuevo',     -- nuevo | visto | dominado | probado
  quiz REAL, feynman REAL,         -- mejores puntajes 0..1
  visto REAL, actualizado REAL,
  PRIMARY KEY (usuario, tema)
);
CREATE TABLE IF NOT EXISTS tarjeta (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  usuario TEXT NOT NULL, tema TEXT, area TEXT,
  frente TEXT NOT NULL, reverso TEXT NOT NULL,
  idioma TEXT,                     -- código BCP-47 para leer en voz alta (zh-CN, ja-JP...)
  origen TEXT,                     -- leccion | tutor | hermes | noticia | manual
  estabilidad REAL, dificultad REAL,
  vence REAL, ultimo REAL, repasos INTEGER DEFAULT 0, fallos INTEGER DEFAULT 0,
  suspendida INTEGER DEFAULT 0, creada REAL
);
CREATE INDEX IF NOT EXISTS tarjeta_vence ON tarjeta(usuario, suspendida, vence);
CREATE TABLE IF NOT EXISTS repaso (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  usuario TEXT, tarjeta INTEGER, nota INTEGER, fecha REAL, segundos REAL, retenibilidad REAL
);
CREATE INDEX IF NOT EXISTS repaso_fecha ON repaso(usuario, fecha);
CREATE TABLE IF NOT EXISTS actividad (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  usuario TEXT, tipo TEXT, tema TEXT, area TEXT, valor REAL, detalle TEXT, fecha REAL
);
CREATE INDEX IF NOT EXISTS actividad_fecha ON actividad(usuario, fecha);
CREATE TABLE IF NOT EXISTS chat (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  usuario TEXT, hilo TEXT, rol TEXT, texto TEXT, fecha REAL
);
CREATE INDEX IF NOT EXISTS chat_hilo ON chat(usuario, hilo, id);
CREATE TABLE IF NOT EXISTS nota (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  usuario TEXT, texto TEXT, origen TEXT, fecha REAL
);
CREATE TABLE IF NOT EXISTS noticia (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  url TEXT UNIQUE, titulo TEXT, resumen TEXT, fuente TEXT, idioma TEXT,
  tipo TEXT DEFAULT 'noticia',     -- noticia | lectura (idiomas)
  peso REAL DEFAULT 1,
  publicada REAL, vista REAL,
  areas TEXT,                      -- JSON lista (por palabras clave y fuente)
  grupo INTEGER,                   -- id de la noticia "cabeza" de su grupo (misma historia)
  cobertura INTEGER DEFAULT 1,     -- cuántas fuentes distintas cuentan la misma historia
  puntaje REAL,                    -- importancia heurística
  analisis TEXT,                   -- JSON de la IA (resumen_es, importancia, impactos...)
  importancia REAL                 -- 1..10 de la IA (o NULL)
);
CREATE INDEX IF NOT EXISTS noticia_pub ON noticia(publicada);
CREATE TABLE IF NOT EXISTS cuaderno (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  usuario TEXT, titulo TEXT, tema TEXT, area TEXT,
  imagen TEXT, trazos TEXT,        -- ruta del PNG y trazos JSON (para seguir editando)
  ancho INTEGER, alto INTEGER,
  transcripcion TEXT, evaluacion TEXT, puntaje REAL,
  creado REAL, actualizado REAL
);
CREATE TABLE IF NOT EXISTS sintesis (
  periodo TEXT, clave TEXT, texto TEXT, creada REAL, n INTEGER,
  PRIMARY KEY (periodo, clave)
);
CREATE TABLE IF NOT EXISTS kv (k TEXT PRIMARY KEY, v TEXT);
"""

_local = threading.local()
_bloqueo = threading.Lock()


def db():
    c = getattr(_local, "c", None)
    if c is None:
        c = sqlite3.connect(RUTA_DB, timeout=30, check_same_thread=False)
        c.row_factory = sqlite3.Row
        c.execute("PRAGMA busy_timeout=30000")
        c.execute("PRAGMA foreign_keys=ON")
        _local.c = c
    return c


MIGRACIONES = [
    ("repaso", "dias", "ALTER TABLE repaso ADD COLUMN dias REAL"),        # días desde el repaso anterior
    ("repaso", "origen", "ALTER TABLE repaso ADD COLUMN origen TEXT"),    # repaso | chequeo
    ("entrega", "tarea", "ALTER TABLE entrega ADD COLUMN tarea INTEGER"),  # entrega de una tarea de práctica
    ("tarea", "tipo", "ALTER TABLE tarea ADD COLUMN tipo TEXT DEFAULT 'desarrollo'"),  # desarrollo | quiz
    ("tarea", "intentos", "ALTER TABLE tarea ADD COLUMN intentos TEXT"),   # quiz: [{fecha, bien, total}]
    ("leccion", "version", "ALTER TABLE leccion ADD COLUMN version INTEGER DEFAULT 1"),  # 1 = corta, 2 = a fondo por partes
    ("leccion", "completa", "ALTER TABLE leccion ADD COLUMN completa INTEGER DEFAULT 1"),  # 0 = aún escribiendo partes
    ("leccion", "plan", "ALTER TABLE leccion ADD COLUMN plan TEXT"),       # JSON: partes de la lección a fondo
    ("noticia", "profundo", "ALTER TABLE noticia ADD COLUMN profundo TEXT"),  # JSON: explicación a fondo {texto, fuentes, tarjetas}
    ("leccion_anterior", "usuario", "ALTER TABLE leccion_anterior ADD COLUMN usuario TEXT"),
]


def _lecciones_por_usuario():
    """Antes las lecciones eran compartidas (clave = tema). Ahora son de cada persona:
    las que ya había se copian a cada cuenta con perfil (quien las estudió las conserva)."""
    if "usuario" in {r[1] for r in db().execute("PRAGMA table_info(leccion)")}:
        return
    duenos = [r[0] for r in db().execute("SELECT usuario FROM perfil ORDER BY creado")] or [""]
    c = db()
    c.execute("""CREATE TABLE leccion_nueva (
        usuario TEXT NOT NULL DEFAULT '', tema TEXT NOT NULL, contenido TEXT NOT NULL, ejercicios TEXT,
        fuentes TEXT, modelo TEXT, creado REAL, version INTEGER DEFAULT 1, completa INTEGER DEFAULT 1, plan TEXT,
        PRIMARY KEY (usuario, tema))""")
    for i, u in enumerate(duenos):
        c.execute("""INSERT INTO leccion_nueva SELECT ?, tema, contenido, ejercicios, fuentes, modelo, creado,
                     version, completa, plan FROM leccion""", (u,))
        if i:
            c.execute("""INSERT INTO leccion_anterior(tema,contenido,ejercicios,fuentes,version,creado,reemplazada,usuario)
                         SELECT tema,contenido,ejercicios,fuentes,version,creado,reemplazada,? FROM leccion_anterior
                         WHERE usuario IS NULL""", (u,))
    c.execute("UPDATE leccion_anterior SET usuario=? WHERE usuario IS NULL", (duenos[0],))
    c.execute("DROP TABLE leccion")
    c.execute("ALTER TABLE leccion_nueva RENAME TO leccion")


def _reubicar_imagenes():
    """Las imágenes se guardan con ruta completa; si la carpeta de datos se movió (otro PC, Docker),
    las vuelve a apuntar a DATOS/cuaderno|entregas/… cuando el archivo está allí."""
    for tabla in ("cuaderno", "entrega"):
        for r in db().execute(f"SELECT id, imagen FROM {tabla} WHERE imagen IS NOT NULL AND imagen != ''").fetchall():
            viejo = Path(r[1])
            if viejo.exists():
                continue
            partes = viejo.parts
            i = next((k for k, x in enumerate(partes) if x in ("cuaderno", "entregas")), None)
            if i is not None and DATOS.joinpath(*partes[i:]).exists():
                db().execute(f"UPDATE {tabla} SET imagen=? WHERE id=?", (str(DATOS.joinpath(*partes[i:])), r[0]))


def iniciar():
    with _bloqueo:
        db().executescript(ESQUEMA)
        db().executescript("""CREATE TABLE IF NOT EXISTS tarea (
            id INTEGER PRIMARY KEY AUTOINCREMENT, usuario TEXT, tema TEXT, area TEXT, titulo TEXT,
            dificultad TEXT, enfoque TEXT, ejercicios TEXT, creado REAL)""")
        db().executescript("""CREATE TABLE IF NOT EXISTS entrega (
            id INTEGER PRIMARY KEY AUTOINCREMENT, usuario TEXT, tema TEXT, area TEXT,
            ejercicio TEXT, version INTEGER, tipo TEXT,      -- texto | imagen | cuaderno
            texto TEXT, imagen TEXT, cuaderno INTEGER,
            evaluacion TEXT, puntaje REAL, creado REAL, corregido REAL)""")
        db().executescript("""CREATE TABLE IF NOT EXISTS leccion_anterior (
            id INTEGER PRIMARY KEY AUTOINCREMENT, tema TEXT, contenido TEXT, ejercicios TEXT,
            fuentes TEXT, version INTEGER, creado REAL, reemplazada REAL, usuario TEXT)""")
        db().executescript("""CREATE TABLE IF NOT EXISTS chequeo (
            id INTEGER PRIMARY KEY AUTOINCREMENT, usuario TEXT, semana TEXT,
            temas TEXT, preguntas TEXT, tarjetas TEXT, resultado TEXT, informe TEXT,
            creado REAL, completado REAL)""")
        for tabla, col, sql in MIGRACIONES:
            if col not in {r[1] for r in db().execute(f"PRAGMA table_info({tabla})")}:
                db().execute(sql)
        _lecciones_por_usuario()
        _reubicar_imagenes()
        db().commit()


def ejecutar(sql, args=()):
    c = db()
    cur = c.execute(sql, args)
    c.commit()
    return cur


def filas(sql, args=()):
    return [dict(r) for r in db().execute(sql, args).fetchall()]


def fila(sql, args=()):
    r = db().execute(sql, args).fetchone()
    return dict(r) if r else None


def kv_get(k, defecto=None):
    r = fila("SELECT v FROM kv WHERE k=?", (k,))
    return json.loads(r["v"]) if r else defecto


def kv_set(k, v):
    ejecutar("INSERT INTO kv(k,v) VALUES(?,?) ON CONFLICT(k) DO UPDATE SET v=excluded.v",
             (k, json.dumps(v, ensure_ascii=False)))


def registrar(usuario, tipo, tema=None, area=None, valor=None, detalle=None):
    ejecutar("INSERT INTO actividad(usuario,tipo,tema,area,valor,detalle,fecha) VALUES(?,?,?,?,?,?,?)",
             (usuario, tipo, tema, area, valor,
              json.dumps(detalle, ensure_ascii=False) if detalle is not None else None, time.time()))
