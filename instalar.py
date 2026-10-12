#!/usr/bin/env python3
"""Instalador de la Academia (Windows, Linux y macOS). Solo usa Python estándar.

    python3 instalar.py                  # instalación guiada (pregunta sí/no antes de escanear)
    python3 instalar.py --auto           # todo automático: escanea, aplica lo recomendado, sin preguntas
    python3 instalar.py --reconfigurar   # volver a elegir el modo de la IA

Qué hace:
 1. (Si dices que sí) escanea este PC: memoria, tarjeta gráfica, servidores de IA y modelos,
    buscador, Tailscale. Propone la configuración; el escaneo se borra solo en 24 h.
 2. Si no, pregunta el modo: IA en este PC, o datos aquí e IA en otro PC tuyo (p. ej. por Tailscale).
 3. Guarda datos/configuracion.json (cada PC tiene la suya; no va a git).
 4. Deja la Academia arrancando sola con el PC y la abre en el navegador.
 5. (Opcional) la publica en tu tailnet para usarla desde el celular.
"""
import json
import os
import platform
import shutil
import socket
import subprocess
import sys
import time
import urllib.request
import webbrowser
from pathlib import Path

for _f in (sys.stdout, sys.stderr):   # Windows: consolas y tuberías sin UTF-8 no pueden imprimir emojis
    try:
        _f.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

RAIZ = Path(__file__).resolve().parent
sys.path.insert(0, str(RAIZ / "app"))
import escaneo  # noqa: E402  (mismo escáner que el botón de Ajustes)

DATOS = RAIZ / "datos"
AUTO = "--auto" in sys.argv
CONFIG = DATOS / "configuracion.json"
SISTEMA = platform.system()          # Linux | Windows | Darwin

# Presets remotos propios de esta copia (privado/presets.json, no se publica): p. ej. el PC de la familia
try:
    REMOTOS = {k: v for k, v in json.loads((RAIZ / "privado" / "presets.json").read_text(encoding="utf-8")).items()
               if v.get("modo") == "remoto"}
except (OSError, ValueError):
    REMOTOS = {}
LOCALES = [("Ollama", "http://127.0.0.1:11434"), ("LM Studio", "http://127.0.0.1:1234"),
           ("llama.cpp / llama-server", "http://127.0.0.1:8080")]


def titulo(t):
    print("\n" + "=" * 64 + f"\n  {t}\n" + "=" * 64)


def preguntar(texto, defecto=""):
    if AUTO:
        return defecto
    r = input(f"{texto}{f' [{defecto}]' if defecto else ''}: ").strip()
    return r or defecto


def si_no(texto, defecto=True):
    if AUTO:
        return defecto
    r = input(f"{texto} [{'S/n' if defecto else 's/N'}]: ").strip().lower()
    return defecto if not r else r.startswith(("s", "y"))


def get_json(url, timeout=8):
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return json.loads(r.read())


def modelos_de(url):
    try:
        return [m.get("id") for m in get_json(url.rstrip("/").removesuffix("/v1") + "/v1/models").get("data", [])]
    except Exception:
        return None


def buscador_ok(url):
    try:
        return get_json(url.rstrip("/") + "/search?q=prueba&format=json", 12).get("results") is not None
    except Exception:
        return False


def ram_gb():
    try:
        if SISTEMA == "Linux":
            return int(open("/proc/meminfo").read().split()[1]) / 1048576
        if SISTEMA == "Darwin":
            return int(subprocess.check_output(["sysctl", "-n", "hw.memsize"])) / 2 ** 30
        if SISTEMA == "Windows":
            import ctypes

            class M(ctypes.Structure):
                _fields_ = [("l", ctypes.c_ulong), ("c", ctypes.c_ulong), ("t", ctypes.c_ulonglong),
                            ("a", ctypes.c_ulonglong), ("tp", ctypes.c_ulonglong), ("ap", ctypes.c_ulonglong),
                            ("tv", ctypes.c_ulonglong), ("av", ctypes.c_ulonglong), ("e", ctypes.c_ulonglong)]
            m = M()
            m.l = ctypes.sizeof(M)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m))
            return m.t / 2 ** 30
    except Exception:
        return None


def puerto_libre(p):
    with socket.socket() as s:
        return s.connect_ex(("127.0.0.1", p)) != 0


def elegir_modelo(modelos, sugerido):
    print("   Modelos disponibles:")
    for i, m in enumerate(modelos, 1):
        print(f"     {i}. {m}")
    r = preguntar("   Número o nombre del modelo principal", sugerido or (modelos[0] if modelos else ""))
    return modelos[int(r) - 1] if r.isdigit() and 0 < int(r) <= len(modelos) else r


def configurar_con_escaneo(previa):
    """Escanea el PC (con permiso) y propone la configuración. Devuelve dict o None si no se quiere."""
    titulo("1/4 · Configuración automática")
    print("""   Puedo revisar este PC para configurarla solo: sistema, memoria, tarjeta gráfica,
   servidores de IA y sus modelos, buscador SearXNG, Tailscale y Docker.
   No leo tus archivos ni envío nada a internet. El resultado se guarda en datos/escaneo.json
   y se BORRA SOLO en 24 horas.""")
    if not si_no("   ¿Escanear este PC ahora?", True):
        return None
    e = escaneo.escanear(DATOS)
    rec = escaneo.recomendar(e, previa)
    escaneo.guardar(DATOS, e, rec)
    vram = ", ".join(f"{g['nombre']}" + (f" ({g['vram_gb']} GB)" if g["vram_gb"] else "") for g in e["graficas"]) or "ninguna detectada"
    print(f"\n   {e['sistema']} · {e['procesador']['nombre']} · {e['ram_gb']} GB RAM · gráfica: {vram}")
    print("\n   Qué puedes usar:")
    for x in rec["capacidades"]:
        print("     " + x)
    if rec["pasos"]:
        print("\n   Cómo completarlo:")
        for n, x in enumerate(rec["pasos"], 1):
            print(f"     {n}. {x.replace('`', '')}")
    print("\n   Configuración recomendada:")
    for k, v in rec["config"].items():
        print(f"     {k:30} {v if v != '' else '—'}")
    if not si_no("\n   ¿Aplicar esta configuración?", True):
        return None
    return rec["config"]


def configurar():
    titulo("1/4 · ¿Dónde corre la IA?")
    print("""   1) Todo en este PC: tus datos y la IA aquí. Necesitas un servidor de IA local
      (Ollama, LM Studio o llama.cpp) y un PC con buena RAM (16 GB o más recomendado).
   2) Datos en este PC, IA en otro PC tuyo (en tu casa o por Tailscale): ese otro PC
      tiene que tener un servidor de IA compatible con OpenAI y estar prendido.""")
    for n, (k, v) in enumerate(REMOTOS.items(), 3):
        print(f"   {n}) {v.get('nombre_preset', k)}")
    op = preguntar("   Elige", "1")
    c = {}
    if op.isdigit() and int(op) >= 3 and int(op) - 3 < len(REMOTOS):
        p = dict(list(REMOTOS.values())[int(op) - 3])
        p.pop("nombre_preset", None)
        c.update(p)
        mods = modelos_de(c["ia_url"])
        print("   " + (f"✅ IA disponible ({len(mods)} modelos)." if mods is not None else
                      "⚠️  No respondió ahora (revisa Tailscale y que ese PC esté prendido). Funcionará cuando haya conexión."))
        return c
    if op == "2":
        c["modo"] = "remoto"
        c["ia_url"] = preguntar("   URL del servidor de IA del otro PC (p. ej. http://192.168.1.20:11434 o https://pc.tu-tailnet.ts.net:10443)", "")
        mods = modelos_de(c["ia_url"]) if c["ia_url"] else None
        if mods:
            print(f"   ✅ Responde con {len(mods)} modelo(s).")
            c["modelo"] = elegir_modelo(mods, next((m for m in mods if "gemma" in m), ""))
        else:
            print("   ⚠️  No respondió: revisa la URL y que ese PC acepte conexiones. Puedes cambiarla luego en Ajustes.")
            c["modelo"] = preguntar("   Modelo principal", "gemma3:12b")
        c["modelo_ligero"] = ""
        c["searx_url"] = preguntar("   URL de su buscador SearXNG (Enter = ninguno)", "")
        c["aigate_url"] = ""
        c["permitir_interrumpir"] = False
        return c
    c["modo"] = "local"
    encontrados = [(n, u, modelos_de(u)) for n, u in LOCALES]
    encontrados = [(n, u, m) for n, u, m in encontrados if m is not None]
    ram = ram_gb()
    sugerido = ("gemma3:27b" if ram and ram >= 48 else "gemma3:12b" if ram and ram >= 20 else "gemma3:4b")
    if encontrados:
        n, u, mods = encontrados[0]
        print(f"\n   ✅ Encontré {n} en {u} con {len(mods)} modelo(s).")
        c["ia_url"] = preguntar("   URL del servidor de IA", u)
        mods = modelos_de(c["ia_url"]) or mods
        c["modelo"] = elegir_modelo(mods, next((m for m in mods if "gemma" in m), ""))
    else:
        print(f"""
   No encontré ningún servidor de IA en este PC. La forma más fácil:
     1. Instala Ollama: https://ollama.com/download
     2. Descarga un modelo (con visión, para leer tus apuntes). Para tu RAM ({f'{ram:.0f} GB' if ram else '?'}):
          ollama pull {sugerido}
        (más RAM → modelo más grande y mejor: gemma3:4b < gemma3:12b < gemma3:27b)
     3. Vuelve a correr el instalador con --reconfigurar (o usa 🪄 Configuración automática en Ajustes).
   Puedes seguir ahora y configurarlo después en Ajustes.""")
        c["ia_url"] = preguntar("   URL del servidor de IA", "http://127.0.0.1:11434")
        c["modelo"] = preguntar("   Modelo principal", sugerido)
    c["modelo_ligero"] = preguntar("   Modelo ligero (opcional, Enter para ninguno)", "")
    c["permitir_interrumpir"] = False   # por defecto: esperar en la cola, nunca cortar otra app
    print("\n   Búsqueda web (para lecciones con fuentes actuales): necesita SearXNG.")
    c["searx_url"] = preguntar("   URL de tu SearXNG, o Enter para ninguna", "")
    c["aigate_url"] = ""
    return c


def autoarranque(puerto):
    py = sys.executable
    servidor = RAIZ / "app" / "servidor.py"
    if SISTEMA == "Linux" and shutil.which("systemctl"):
        unidad = Path.home() / ".config/systemd/user/academia.service"
        unidad.parent.mkdir(parents=True, exist_ok=True)
        unidad.write_text(f"""[Unit]
Description=Academia personal (127.0.0.1:{puerto})
After=network-online.target

[Service]
Type=simple
WorkingDirectory={servidor.parent}
ExecStart={py} {servidor}
Environment=PYTHONUNBUFFERED=1
Restart=always
RestartSec=3
Nice=10

[Install]
WantedBy=default.target
""", encoding="utf-8")
        subprocess.run(["systemctl", "--user", "daemon-reload"])
        subprocess.run(["systemctl", "--user", "enable", "--now", "academia.service"])
        subprocess.run(["systemctl", "--user", "restart", "academia.service"])
        print("   ✅ Servicio de usuario 'academia' activo (arranca solo al iniciar sesión).")
        print("      Para que arranque aunque no inicies sesión: sudo loginctl enable-linger $USER")
        return True
    if SISTEMA == "Windows":
        pyw = Path(py).with_name("pythonw.exe")
        pyw = pyw if pyw.exists() else Path(py)
        inicio = Path(os.environ["APPDATA"]) / r"Microsoft\Windows\Start Menu\Programs\Startup"
        vbs = inicio / "Academia.vbs"
        vbs.write_text(f'CreateObject("WScript.Shell").Run """{pyw}"" ""{servidor}""", 0, False\n', encoding="utf-8")
        subprocess.Popen([str(pyw), str(servidor)], cwd=str(servidor.parent),
                         creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        print(f"   ✅ Arranca sola al iniciar Windows ({vbs.name} en la carpeta Inicio) y ya está corriendo.")
        return True
    if SISTEMA == "Darwin":
        plist = Path.home() / "Library/LaunchAgents/com.academia.servidor.plist"
        plist.parent.mkdir(parents=True, exist_ok=True)
        plist.write_text(f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
 <key>Label</key><string>com.academia.servidor</string>
 <key>ProgramArguments</key><array><string>{py}</string><string>{servidor}</string></array>
 <key>WorkingDirectory</key><string>{servidor.parent}</string>
 <key>RunAtLoad</key><true/><key>KeepAlive</key><true/>
 <key>StandardOutPath</key><string>{DATOS / 'academia.log'}</string>
 <key>StandardErrorPath</key><string>{DATOS / 'academia.log'}</string>
</dict></plist>
""", encoding="utf-8")
        subprocess.run(["launchctl", "unload", str(plist)], capture_output=True)
        subprocess.run(["launchctl", "load", str(plist)])
        print("   ✅ Agente de inicio de macOS instalado y corriendo.")
        return True
    print(f"   ⚠️  No sé dejarla automática en este sistema. Iníciala con: {py} {servidor}")
    return False


def escaneo_version():
    try:
        return "v" + (RAIZ / "VERSION").read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def main():
    if sys.version_info < (3, 10):
        sys.exit("Necesitas Python 3.10 o más nuevo: https://www.python.org/downloads/")
    DATOS.mkdir(exist_ok=True, mode=0o700)
    titulo("Instalador de la Academia " + escaneo_version())
    print(f"   Sistema: {SISTEMA} · Python {platform.python_version()} · carpeta: {RAIZ}")
    previa = {}
    if CONFIG.exists():
        previa = json.loads(CONFIG.read_text(encoding="utf-8"))
        if "--reconfigurar" not in sys.argv and not si_no("   Ya hay una configuración. ¿Volver a configurar la IA?", AUTO):
            c = previa
        else:
            c = previa | (configurar_con_escaneo(previa) or configurar())
    else:
        c = configurar_con_escaneo({}) or configurar()

    titulo("2/4 · Tu perfil y el acceso")
    c["nombre"] = preguntar("   Nombre de esta Academia", previa.get("nombre", "Mi Academia"))
    c["usuario_local"] = preguntar("   Tu nombre de perfil en este PC (sin espacios)", previa.get("usuario_local") or
                                   (os.environ.get("USERNAME") or os.environ.get("USER") or "yo").lower())
    print("   Para entrar desde el celular por Tailscale: escribe tu cuenta de Tailscale (correo).")
    print("   Solo esas cuentas podrán abrirla. Enter = cualquier cuenta de tu tailnet.")
    cuentas = preguntar("   Cuentas permitidas (separadas por coma)", ",".join(previa.get("usuarios_permitidos") or []))
    c["usuarios_permitidos"] = [x.strip() for x in cuentas.split(",") if x.strip()]
    puerto = int(previa.get("puerto", 8092))
    if not previa and not puerto_libre(puerto):
        puerto = next(p for p in range(8092, 8200) if puerto_libre(p))
    c["puerto"] = puerto
    c.setdefault("host", "127.0.0.1")
    CONFIG.write_text(json.dumps(c, ensure_ascii=False, indent=2), encoding="utf-8")
    try:
        os.chmod(CONFIG, 0o600)        # puede guardar la clave de acceso
    except OSError:
        pass
    print(f"   ✅ Configuración guardada en {CONFIG}")

    titulo("3/4 · Arranque automático")
    autoarranque(puerto)

    titulo("4/4 · Celular y tablet (opcional)")
    ts = shutil.which("tailscale")
    if ts and si_no("   ¿Publicarla en tu tailnet (HTTPS, solo tus equipos) para abrirla desde el celular?", not AUTO):
        cmd = [ts, "serve", "--bg", "--https=15443", f"http://127.0.0.1:{puerto}"]
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode == 0:
            print("   ✅ Publicada. Dirección: " + next((l for l in r.stdout.split() if l.startswith("https://")),
                                                   "mira «tailscale serve status»"))
        else:
            print("   ⚠️  No se pudo (puede requerir administrador). Corre tú: " + " ".join(cmd))
            print("      " + (r.stderr or "").strip()[:300])
    elif not ts:
        print("   Tailscale no está instalado: https://tailscale.com/download (luego: tailscale serve --bg "
              f"--https=15443 http://127.0.0.1:{puerto})")

    url = f"http://127.0.0.1:{puerto}/"
    for _ in range(20):
        try:
            urllib.request.urlopen(url + "api/ia", timeout=2)
            break
        except Exception:
            time.sleep(0.5)
    titulo("¡Listo!")
    print(f"""   Abre: {url}
   Primer paso dentro de la app: ⚙️ Ajustes → tu perfil y la prioridad de las áreas que quieras
   (todas empiezan en 0), o crea tus propias áreas y metas en 🎯.
   Celular o tablet: mira docs/facil/CELULAR.md (Tailscale o clave de acceso en tu red de casa).
   Manuales: docs/facil/ (versión fácil) y docs/ (versión completa).""")
    try:
        webbrowser.open(url)
    except Exception:
        pass


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nCancelado.")
