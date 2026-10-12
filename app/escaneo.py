"""Auto-escaneo y auto-configuración: mira qué tiene este PC que la Academia puede usar
(memoria, tarjeta gráfica, servidores de IA y sus modelos, buscador, Tailscale, Docker),
recomienda una configuración y explica cómo usar cada cosa.

Privacidad: solo se ejecuta cuando alguien lo pide (botón en Ajustes o el instalador, con
confirmación sí/no). No lee archivos personales, ni números de serie, ni IPs, ni nombres de
cuentas. El resultado se guarda en datos/escaneo.json y se BORRA SOLO a las 24 horas
(`purgar()` lo revisa cada minuto); también se puede borrar antes desde Ajustes.

Solo usa la biblioteca estándar; lo usan servidor.py (/api/escaneo) e instalar.py.
"""
import json
import os
import platform
import re
import shutil
import socket
import subprocess
import time
import urllib.request
from pathlib import Path

DURACION = 24 * 3600                       # segundos que vive un escaneo guardado
SISTEMA = platform.system()                # Linux | Windows | Darwin

# Dónde suelen escuchar los servidores de IA compatibles con OpenAI y los buscadores SearXNG
SERVIDORES_IA = [("Ollama", "http://127.0.0.1:11434"), ("LM Studio", "http://127.0.0.1:1234"),
                 ("llama.cpp (llama-server)", "http://127.0.0.1:8080"), ("vLLM", "http://127.0.0.1:8000"),
                 ("Jan", "http://127.0.0.1:1337"), ("Ollama (Docker)", "http://ollama:11434"),
                 ("Ollama del PC anfitrión (Docker)", "http://host.docker.internal:11434")]
BUSCADORES = ["http://127.0.0.1:8888", "http://127.0.0.1:8080", "http://searxng:8080",
              "http://host.docker.internal:8888"]
VISION = re.compile(r"gemma-?3|gemma-?4|llava|vl\b|-vl|vision|minicpm-v|moondream|pixtral|qwen2\.5vl|qwen3-vl|mistral-small3\.[12]", re.I)
PEQUENO = re.compile(r"(^|[^0-9a-z.])(0\.5|1|1\.5|2|3|4)b\b|tiny|e2b|e4b", re.I)


# ------------------------------------------------------------------ utilidades
def _cmd(*a, timeout=6):
    try:
        r = subprocess.run(list(a), capture_output=True, text=True, timeout=timeout)
        return r.stdout.strip() if r.returncode == 0 else None
    except (OSError, subprocess.SubprocessError):
        return None


def _json(url, timeout=3):
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return json.loads(r.read())
    except Exception:
        return None


def _resuelve(url):
    host = re.sub(r"^https?://", "", url).split(":")[0].split("/")[0]
    try:
        socket.getaddrinfo(host, None)
        return True
    except OSError:
        return False


# ------------------------------------------------------------------ hardware
def memoria_gb():
    try:
        if SISTEMA == "Linux":
            m = dict(l.split(":", 1) for l in open("/proc/meminfo"))
            return round(int(m["MemTotal"].split()[0]) / 1048576, 1), round(int(m["MemAvailable"].split()[0]) / 1048576, 1)
        if SISTEMA == "Darwin":
            return round(int(_cmd("sysctl", "-n", "hw.memsize") or 0) / 2 ** 30, 1), None
        if SISTEMA == "Windows":
            import ctypes

            class M(ctypes.Structure):
                _fields_ = [("l", ctypes.c_ulong), ("c", ctypes.c_ulong), ("t", ctypes.c_ulonglong),
                            ("a", ctypes.c_ulonglong), ("tp", ctypes.c_ulonglong), ("ap", ctypes.c_ulonglong),
                            ("tv", ctypes.c_ulonglong), ("av", ctypes.c_ulonglong), ("e", ctypes.c_ulonglong)]
            m = M()
            m.l = ctypes.sizeof(M)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m))
            return round(m.t / 2 ** 30, 1), round(m.a / 2 ** 30, 1)
    except Exception:
        pass
    return None, None


def procesador():
    nombre = platform.processor() or ""
    if SISTEMA == "Linux":
        try:
            nombre = next(l.split(":", 1)[1].strip() for l in open("/proc/cpuinfo") if l.startswith("model name"))
        except (OSError, StopIteration):
            pass
    elif SISTEMA == "Darwin":
        nombre = _cmd("sysctl", "-n", "machdep.cpu.brand_string") or nombre
    return {"nombre": nombre or platform.machine(), "nucleos": os.cpu_count()}


def graficas():
    """Tarjetas gráficas y su memoria (VRAM) en GB. Apple Silicon comparte la RAM."""
    out = []
    smi = _cmd("nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader,nounits")
    for l in (smi or "").splitlines():
        n, mem = [x.strip() for x in l.rsplit(",", 1)]
        out.append({"nombre": n, "vram_gb": round(int(mem) / 1024, 1), "tipo": "nvidia"})
    if not out and shutil.which("rocm-smi"):
        info = _cmd("rocm-smi", "--showproductname", "--showmeminfo", "vram", "--json")
        try:
            for k, v in json.loads(info or "{}").items():
                total = next((int(x) for kk, x in v.items() if "Total Memory" in kk), 0)
                out.append({"nombre": v.get("Card series") or k, "vram_gb": round(total / 2 ** 30, 1), "tipo": "amd"})
        except (ValueError, AttributeError):
            pass
    if not out and SISTEMA == "Darwin" and platform.machine() == "arm64":
        out.append({"nombre": "Apple Silicon (memoria unificada)", "vram_gb": None, "tipo": "apple"})
    if not out and SISTEMA == "Linux" and shutil.which("lspci"):
        for l in (_cmd("lspci") or "").splitlines():
            if re.search(r"VGA|3D controller", l):
                out.append({"nombre": l.split(":", 2)[-1].strip(), "vram_gb": None, "tipo": "otra"})
    if not out and SISTEMA == "Windows":
        for l in (_cmd("powershell", "-NoProfile", "-Command",
                       "(Get-CimInstance Win32_VideoController).Name", timeout=12) or "").splitlines():
            if l.strip():
                out.append({"nombre": l.strip(), "vram_gb": None, "tipo": "otra"})
    return out


# ------------------------------------------------------------------ software
def servidores_ia():
    vistos, out = set(), []
    for nombre, url in SERVIDORES_IA:
        if "://ollama" in url or "host.docker" in url:
            if not _resuelve(url):
                continue
        d = _json(url + "/v1/models", 3)
        if not d:
            continue
        mods = [m.get("id") for m in d.get("data", []) if m.get("id")]
        clave = tuple(sorted(mods))
        if clave in vistos and mods:          # el mismo servidor respondiendo por dos nombres
            continue
        vistos.add(clave)
        out.append({"nombre": nombre, "url": url, "modelos": mods,
                    "con_vision": [m for m in mods if VISION.search(m)]})
    return out


def buscadores():
    out = []
    for url in BUSCADORES:
        if ("searxng" in url or "host.docker" in url) and not _resuelve(url):
            continue
        d = _json(url + "/search?q=prueba&format=json", 6)
        if d and "results" in d:
            out.append(url)
    return out


def tailscale():
    ts = shutil.which("tailscale")
    if not ts:
        return {"instalado": False}
    d = None
    try:
        d = json.loads(_cmd(ts, "status", "--json") or "null")
    except ValueError:
        pass
    activo = bool(d and d.get("BackendState") == "Running")
    return {"instalado": True, "conectado": activo,
            "nombre_dns": ((d or {}).get("Self") or {}).get("DNSName", "").rstrip(".") if activo else ""}


def docker():
    return {"instalado": bool(shutil.which("docker")), "dentro_de_docker": Path("/.dockerenv").exists()}


def disco_libre_gb(carpeta):
    try:
        return round(shutil.disk_usage(carpeta).free / 2 ** 30, 1)
    except OSError:
        return None


def escanear(carpeta_datos="."):
    total, libre = memoria_gb()
    return {"fecha": int(time.time()), "sistema": f"{SISTEMA} {platform.release()}", "arquitectura": platform.machine(),
            "python": platform.python_version(), "procesador": procesador(), "ram_gb": total, "ram_libre_gb": libre,
            "graficas": graficas(), "disco_libre_gb": disco_libre_gb(carpeta_datos),
            "servidores_ia": servidores_ia(), "buscadores": buscadores(), "tailscale": tailscale(), "docker": docker()}


# ------------------------------------------------------------------ recomendación
def _modelo_sugerido(presupuesto_gb):
    """Modelo de Ollama con visión (lee tus apuntes) que cabe en la memoria disponible."""
    if presupuesto_gb >= 20:
        return "gemma3:27b"
    if presupuesto_gb >= 9:
        return "gemma3:12b"
    if presupuesto_gb >= 4:
        return "gemma3:4b"
    return "gemma3:1b"


def recomendar(e, actual=None):
    """Configuración recomendada + qué se puede usar + pasos para lo que falta."""
    actual = actual or {}
    vram = max([g["vram_gb"] or 0 for g in e["graficas"]] or [0])
    apple = any(g["tipo"] == "apple" for g in e["graficas"])
    ram = e["ram_gb"] or 0
    presupuesto = vram if vram else (ram * 0.6 if apple else ram * 0.4)
    gpu_buena = vram >= 12 or (apple and ram >= 24)
    gpu = vram >= 6 or apple
    c, capacidades, pasos = {}, [], []

    srv = next((s for s in e["servidores_ia"] if s["modelos"]), None) or (e["servidores_ia"] or [None])[0]
    if srv:
        mods = srv["modelos"]
        prefer = [m for m in mods if m == actual.get("modelo")] or srv["con_vision"] or \
                 [m for m in mods if re.search(r"gemma|qwen|llama|mistral", m, re.I)] or mods
        grandes = [m for m in prefer if not PEQUENO.search(m)] or prefer
        c.update({"modo": "local", "ia_url": srv["url"], "modelo": grandes[0] if grandes else _modelo_sugerido(presupuesto)})
        ligero = next((m for m in mods if PEQUENO.search(m) and m != c["modelo"]), "")
        c["modelo_ligero"] = ligero
        capacidades.append(f"✅ IA local: {srv['nombre']} con {len(mods)} modelo(s); usaría «{c['modelo']}».")
        if not mods:
            pasos.append(f"Tu servidor {srv['nombre']} no tiene modelos. Descarga uno: `ollama pull {_modelo_sugerido(presupuesto)}`.")
        if srv["con_vision"]:
            capacidades.append("✅ Visión: el cuaderno y las fotos de tus ejercicios se pueden corregir.")
        else:
            pasos.append(f"Para que la IA lea tus apuntes a mano necesitas un modelo con visión (p. ej. `ollama pull {_modelo_sugerido(presupuesto)}`).")
    else:
        sug = _modelo_sugerido(presupuesto)
        c.update({"modo": "local", "ia_url": "http://ollama:11434" if e["docker"]["dentro_de_docker"] else "http://127.0.0.1:11434",
                  "modelo": sug, "modelo_ligero": ""})
        capacidades.append("❌ No encontré ningún servidor de IA en este PC.")
        pasos += ["Instala Ollama (lo más fácil): https://ollama.com/download — o usa `docker compose --profile ollama up -d`.",
                  f"Descarga el modelo recomendado para tu PC: `ollama pull {sug}`.",
                  "Vuelve a escanear: la Academia lo encontrará sola."]

    if e["buscadores"]:
        c["searx_url"] = e["buscadores"][0]
        capacidades.append("✅ Búsqueda web (SearXNG): lecciones con fuentes actuales.")
    else:
        c["searx_url"] = ""
        capacidades.append("➖ Sin búsqueda web: las lecciones salen solo del conocimiento del modelo (+ documentos de OpenAlex).")
        pasos.append("Opcional: búsqueda web con `docker compose --profile buscador up -d` (SearXNG privado en tu PC).")

    # ritmo de la IA según la potencia: que nunca deje el PC inutilizable
    c["trabajos_paralelos"] = 1
    c["lecciones_adelantadas"] = 2 if gpu_buena else 1 if gpu else 0
    c["noticias_a_fondo_por_persona"] = 8 if gpu_buena else 4 if gpu else 2
    c["permitir_interrumpir"] = False
    if e["docker"]["dentro_de_docker"] and not e["graficas"]:
        capacidades.append("🔎 Dentro de Docker no veo la tarjeta gráfica del PC: dejé un ritmo prudente; súbelo en Avanzado si tu IA va rápida.")
    elif gpu_buena:
        capacidades.append(f"✅ Tarjeta gráfica potente ({vram or 'memoria unificada'} GB): lecciones a fondo y noticias en segundo plano.")
    elif gpu:
        capacidades.append(f"🟡 Tarjeta gráfica modesta ({vram} GB): modelos medianos; prepararé menos cosas por adelantado.")
    else:
        capacidades.append("🟡 Sin tarjeta gráfica útil: la IA irá en el procesador (lenta). Usa un modelo pequeño o la IA de otro PC tuyo.")
    if ram and ram < 8:
        pasos.append(f"Tienes {ram} GB de RAM: usa modelos de 1-4B (p. ej. `gemma3:1b`) o la IA de otro PC tuyo.")

    ts = e["tailscale"]
    if e["docker"]["dentro_de_docker"]:
        pasos.append("Celular: instala Tailscale en el PC (no en Docker) y corre `tailscale serve --bg --https=15443 http://127.0.0.1:8092`.")
    elif ts.get("conectado"):
        capacidades.append("✅ Tailscale conectado: puedes usarla desde tu celular sin abrirla a internet.")
        pasos.append("Celular: `tailscale serve --bg --https=15443 http://127.0.0.1:8092` y abre "
                     f"https://{ts.get('nombre_dns') or '<tu-pc>.<tailnet>.ts.net'}:15443 en el celular.")
    elif ts.get("instalado"):
        capacidades.append("➖ Tailscale instalado pero desconectado.")
    elif not e["docker"]["dentro_de_docker"]:
        capacidades.append("➖ Sin Tailscale: solo desde este PC (o define una clave de acceso para tu red de casa).")
    if (e.get("disco_libre_gb") or 99) < 10:
        pasos.append(f"Poco disco libre ({e['disco_libre_gb']} GB): los modelos ocupan de 1 a 20 GB.")
    return {"config": c, "capacidades": capacidades, "pasos": pasos}


# ------------------------------------------------------------------ guardar 24 h
def _archivo(datos):
    return Path(datos) / "escaneo.json"


def guardar(datos, e, rec):
    f = _archivo(datos)
    f.write_text(json.dumps({"creado": int(time.time()), "expira": int(time.time()) + DURACION,
                             "escaneo": e, "recomendacion": rec}, ensure_ascii=False), encoding="utf-8")
    try:
        os.chmod(f, 0o600)
    except OSError:
        pass


def leer(datos):
    purgar(datos)
    try:
        return json.loads(_archivo(datos).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def purgar(datos, forzar=False):
    """Borra el escaneo guardado si ya pasó un día (o si se pide)."""
    f = _archivo(datos)
    try:
        if forzar or json.loads(f.read_text(encoding="utf-8")).get("expira", 0) <= time.time():
            f.unlink()
            return True
    except (OSError, ValueError):
        if f.exists() and (forzar or time.time() - f.stat().st_mtime > DURACION):
            f.unlink(missing_ok=True)
            return True
    return False


if __name__ == "__main__":       # python3 app/escaneo.py → ver el escaneo sin guardar nada
    import sys
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    r = escanear()
    print(json.dumps({"escaneo": r, "recomendacion": recomendar(r)}, ensure_ascii=False, indent=2))
