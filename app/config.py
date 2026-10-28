"""Configuración de esta instalación de la Academia.

Vive en datos/configuracion.json (fuera de git: cada PC tiene la suya). La
escribe el instalador (instalar.py) y se puede cambiar en Ajustes → IA.
Las variables de entorno ACADEMIA_* tienen prioridad (útil para pruebas).

Modos:
  "local"  → la IA corre en este mismo PC (llama.cpp/llama-swap, Ollama o LM Studio:
             cualquier servidor compatible con la API de OpenAI).
  "remoto" → los datos se guardan en este PC, pero la IA y el buscador son los de
             otro PC de tu red (p. ej. por Tailscale).

Presets propios de una instalación (p. ej. el PC de la familia) van en
privado/presets.json, que no se publica.
"""
import json
import os
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
DATOS = Path(os.environ.get("ACADEMIA_DATOS") or RAIZ / "datos")
DATOS.mkdir(parents=True, exist_ok=True, mode=0o700)
ARCHIVO = DATOS / "configuracion.json"

DEFECTO = {
    "modo": "local",
    "host": "127.0.0.1",
    "puerto": 8092,
    "ia_url": "http://127.0.0.1:11434",          # servidor compatible con OpenAI (/v1/chat/completions)
    "modelo": "gemma3:12b",                       # el escaneo automático propone el que mejor cabe en tu PC
    "modelo_ligero": "",                          # opcional: modelo pequeño para cuando el grande está ocupado
    "modelos_compatibles": [],                    # otros modelos que pueden estar cargados A LA VEZ sin conflicto
                                                  # (p. ej. el de Hermes si el servidor los deja convivir)
    "searx_url": "http://127.0.0.1:8888",         # SearXNG (búsqueda web); vacío = sin búsqueda
    "aigate_url": "",                             # opcional: http://<pc>:9137/state (no molestar si se juega)
    "trabajos_paralelos": 1,                      # tareas a la vez en el servidor de IA (= llama-server --parallel N)
    "noticias_a_fondo_por_persona": 8,            # noticias diarias a máxima profundidad (las que verá cada persona)
    "regiones_por_defecto": {"global": 2},        # regiones de noticias (prioridad 0-3) de quien aún no eligió las suyas
    "lecciones_adelantadas": 2,                   # lecciones listas sin leer que se preparan por adelantado por persona
    "mercado_cada_dias": 30,                      # cada cuántos días se renueva el nivel profesional vs. mercado de cada ruta
    "revision_rutas_cada_dias": 7,                # cada cuántos días se revisa cada ruta (temas que faltan o cambiaron)
    "acciones_pronostico_diario": True,           # 💹 cada día, pronóstico a 30 días de cada acción vigilada (False = solo
                                                  # noticias y alertas; el pronóstico se pide a mano)
    "verificar_lecciones": False,                 # True = cada lección nueva se contrasta sola con fuentes verificadas
    "modelos_cedibles": [],                       # modelos de otras apps que ceden el turno a lo que PIDES tú cuando llevan
                                                  # 20 s sin procesar (p. ej. el de un servicio de memoria); [] = siempre esperar
    "supermemory_estado_url": "",                 # opcional: URL de otra app que devuelva JSON {"en_curso": true|false}
                                                  # (p. ej. un servicio de memoria): no se le corta un trabajo a medias
    "permitir_interrumpir": False,                # False (por defecto) = si otra app usa la IA, tu tarea espera en la cola;
                                                  # True = te pregunta si quieres interrumpirla (su tarea en curso fallaría)
    "usuarios_permitidos": None,                  # cuentas de Tailscale; None = las del portal (si existe), [] = cualquiera del tailnet
    "usuario_local": "",                          # nombre del perfil cuando se entra desde este mismo PC
    "administradores": None,                      # cuentas que pueden cambiar la IA desde el celular; None = la 1.ª permitida
    "nombre": "Academia",
    # --- seguridad (ver docs/SEGURIDAD_Y_DATOS.md) ---
    "redes_locales": ["127.0.0.0/8", "::1/128"],  # quién cuenta como «este PC» (admin sin clave). En Docker se añade
                                                  # la red interna del contenedor (el puerto solo se publica en 127.0.0.1)
    "clave_acceso": "",                           # si no está vacía, cualquier equipo que NO sea este PC (ni Tailscale)
                                                  # puede entrar con esta clave; vacía = solo este PC y Tailscale
    "hosts_permitidos": [],                       # nombres extra con los que se abre (p. ej. "academia.lan");
                                                  # localhost, 127.0.0.1 y *.ts.net ya están permitidos
}

# Valores de las variables de entorno que se respetan (pruebas / unidades systemd viejas)
ENTORNO = {"ACADEMIA_HOST": "host", "ACADEMIA_PUERTO": "puerto", "ACADEMIA_LLAMA": "ia_url",
           "ACADEMIA_MODELO": "modelo", "ACADEMIA_MODELO_LIGERO": "modelo_ligero",
           "ACADEMIA_SEARX": "searx_url", "ACADEMIA_AIGATE": "aigate_url",
           "ACADEMIA_CLAVE": "clave_acceso", "ACADEMIA_REDES_LOCALES": "redes_locales",
           "ACADEMIA_HOSTS": "hosts_permitidos", "ACADEMIA_USUARIO": "usuario_local"}
LISTAS = {"redes_locales", "hosts_permitidos"}   # en el entorno van separadas por comas

VERSION = (RAIZ / "VERSION").read_text(encoding="utf-8").strip() if (RAIZ / "VERSION").exists() else "0.0.0"


def leer():
    c = dict(DEFECTO)
    # ACADEMIA_INICIAL_<CLAVE>: valor de partida (p. ej. en Docker) que SÍ se puede cambiar luego en Ajustes
    for env, v in os.environ.items():
        if env.startswith("ACADEMIA_INICIAL_") and env[17:].lower() in DEFECTO:
            clave = env[17:].lower()
            c[clave] = int(v) if isinstance(DEFECTO[clave], int) and not isinstance(DEFECTO[clave], bool) and v.isdigit() else v
    viejo = RAIZ / "config" / "academia.json"          # compatibilidad con la primera versión
    for f in (viejo, ARCHIVO):
        try:
            c.update(json.loads(f.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            pass
    for env, clave in ENTORNO.items():
        if os.environ.get(env):
            v = os.environ[env]
            c[clave] = int(v) if clave == "puerto" else [x.strip() for x in v.split(",") if x.strip()] if clave in LISTAS else v
    return c


def guardar(cambios):
    actual = {}
    try:
        actual = json.loads(ARCHIVO.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        pass
    actual.update(cambios)
    ARCHIVO.write_text(json.dumps(actual, ensure_ascii=False, indent=2), encoding="utf-8")
    privado(ARCHIVO)
    return leer()


def privado(ruta):
    """Solo tu usuario puede leerlo (puede guardar la clave de acceso). En Windows no aplica."""
    try:
        os.chmod(ruta, 0o600)
    except OSError:
        pass


# Valores listos para elegir con un clic (Ajustes → IA y el instalador)
PRESETS = {
    "local_ollama": {"modo": "local", "nombre_preset": "IA en este PC con Ollama",
                     "ia_url": "http://127.0.0.1:11434", "modelo": "gemma3:12b", "modelo_ligero": "",
                     "searx_url": "", "aigate_url": "", "permitir_interrumpir": False},
    "local_lmstudio": {"modo": "local", "nombre_preset": "IA en este PC con LM Studio",
                       "ia_url": "http://127.0.0.1:1234", "modelo": "", "modelo_ligero": "",
                       "searx_url": "", "aigate_url": "", "permitir_interrumpir": False},
    "local_llamacpp": {"modo": "local", "nombre_preset": "IA en este PC con llama.cpp (llama-server)",
                       "ia_url": "http://127.0.0.1:8080", "modelo": "", "modelo_ligero": "",
                       "searx_url": "", "aigate_url": "", "permitir_interrumpir": False},
    "local_llamaswap": {"modo": "local", "nombre_preset": "IA en este PC con llama-swap + SearXNG",
                        "ia_url": "http://127.0.0.1:11434", "modelo": "", "modelo_ligero": "",
                        "searx_url": "http://127.0.0.1:8888", "aigate_url": "", "permitir_interrumpir": False},
    "docker": {"modo": "local", "nombre_preset": "Docker: Ollama y SearXNG del docker compose",
               "ia_url": "http://ollama:11434", "modelo": "gemma3:4b", "modelo_ligero": "",
               "searx_url": "http://searxng:8080", "aigate_url": "", "permitir_interrumpir": False},
}
try:   # presets propios de esta instalación (no se publican)
    PRESETS.update(json.loads((RAIZ / "privado" / "presets.json").read_text(encoding="utf-8")))
except (OSError, ValueError):
    pass
SERVIDORES_LOCALES = [("llama-swap / Ollama", "http://127.0.0.1:11434"), ("LM Studio", "http://127.0.0.1:1234"),
                      ("llama.cpp (llama-server)", "http://127.0.0.1:8080")]

C = leer()
