#!/usr/bin/env python3
"""Prueba de humo: arranca la Academia en una carpeta temporal y revisa lo básico y la seguridad.
No toca tus datos ni necesita IA. Uso: python3 pruebas/humo.py   (sale con código 1 si algo falla)"""
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

for _f in (sys.stdout, sys.stderr):   # Windows: consolas y tuberías sin UTF-8 no pueden imprimir emojis
    try:
        _f.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

RAIZ = Path(__file__).resolve().parent.parent


def puerto_libre():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def pedir(url, datos=None, cabeceras=None, metodo=None):
    req = urllib.request.Request(url, data=datos, headers=cabeceras or {}, method=metodo)
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")


def main():
    fallos = []
    with tempfile.TemporaryDirectory() as tmp:
        p = puerto_libre()
        env = dict(os.environ, ACADEMIA_DATOS=tmp, ACADEMIA_PUERTO=str(p), ACADEMIA_HOST="127.0.0.1",
                   ACADEMIA_LLAMA="http://127.0.0.1:9", ACADEMIA_SEARX="")
        srv = subprocess.Popen([sys.executable, str(RAIZ / "app" / "servidor.py")], env=env,
                               stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        u = f"http://127.0.0.1:{p}"
        try:
            for _ in range(60):
                try:
                    urllib.request.urlopen(u + "/manifest.webmanifest", timeout=1)
                    break
                except Exception:
                    time.sleep(0.5)
            casos = [
                ("página principal", pedir(u + "/")[0] == 200),
                ("API /api/yo", pedir(u + "/api/yo")[0] == 200),
                ("versión", json.loads(pedir(u + "/api/version")[1]).get("version") == (RAIZ / "VERSION").read_text().strip()),
                ("temas", pedir(u + "/temas/index.json")[0] == 200),
                ("bloquea Host desconocido (DNS rebinding)", pedir(u + "/api/yo", cabeceras={"Host": "malo.example"})[0] == 421),
                ("bloquea POST que no es JSON (CSRF)", pedir(u + "/api/config", b'{"nombre":"x"}', {"Content-Type": "text/plain"})[0] == 415),
                ("bloquea otro origen (CSRF)", pedir(u + "/api/config", b'{"nombre":"x"}', {"Content-Type": "application/json", "Origin": "http://malo.example"})[0] == 403),
                ("no sale de la carpeta web", pedir(u + "/../app/config.py")[0] in (404, 400)),
                ("escaneo exige confirmación", "confirmación" in pedir(u + "/api/escaneo", b"{}", {"Content-Type": "application/json"})[1]),
                ("regiones de noticias (global siempre)", any(r["id"] == "global" for r in json.loads(pedir(u + "/api/regiones")[1])["regiones"])),
                ("fuentes solo de internet público", "público" in pedir(u + "/api/regiones/fuente/probar", b'{"u":"http://127.0.0.1/rss"}', {"Content-Type": "application/json"})[1]),
                ("cabeceras de seguridad", "nosniff" in str(urllib.request.urlopen(u + "/").headers)),
                ("horizonte (motor adaptativo)", "ritmo" in json.loads(pedir(u + "/api/horizonte")[1])),
                ("parte de lección rechaza datos inválidos", "error" in json.loads(pedir(u + "/api/parte", b'{"tema":"x","parte":1,"estado":"raro"}', {"Content-Type": "application/json"})[1])),
                ("reexplicar solo con estilos conocidos", "error" in json.loads(pedir(u + "/api/reexplicar", b'{"tema":"x","estilo":"<b>"}', {"Content-Type": "application/json"})[1])),
                ("Hermes: lo que más rinde hoy", pedir(u + "/api/hermes/siguiente")[0] == 200),
                ("programa de dominio: meta ajena o inexistente", "error" in json.loads(pedir(u + "/api/dominio?objetivo=999")[1])),
                ("lectura de paper ajena o inexistente", "error" in json.loads(pedir(u + "/api/paper?id=999")[1])),
                ("Hermes: repaso por chat", "tarjetas" in json.loads(pedir(u + "/api/hermes/repaso?n=2")[1])),
                ("acciones: lista vacía al empezar", json.loads(pedir(u + "/api/acciones")[1]).get("acciones") == []),
                ("acciones: rechaza símbolos inválidos", "inválido" in pedir(u + "/api/acciones/vigilar", b'{"simbolo":"<b>x"}', {"Content-Type": "application/json"})[1]),
                ("acciones: pronóstico solo de tu lista", "error" in json.loads(pedir(u + "/api/accion/pronostico", b'{"simbolo":"NVDA"}', {"Content-Type": "application/json"})[1])),
                ("confianza: rechaza niveles y temas inválidos", "error" in json.loads(pedir(u + "/api/confianza", b'{"tema":"no.existe","confianza":"seguro"}', {"Content-Type": "application/json"})[1])),
                ("confianza: registra y aparece en la calibración del reporte",
                 json.loads(pedir(u + "/api/confianza", b'{"tema":"biologia.celula.0","confianza":"seguro","acierto":true}', {"Content-Type": "application/json"})[1]).get("ok")
                 and json.loads(pedir(u + "/api/reporte")[1])["calibracion"]["n"] == 1),
                ("examinador: material de preguntas y evidencia validada", "error" in json.loads(pedir(u + "/api/hermes/examen?tema=no.existe")[1])
                 and "error" in json.loads(pedir(u + "/api/hermes/evidencia", b'{"tema":"biologia.celula.0","puntaje":7}', {"Content-Type": "application/json"})[1])
                 and json.loads(pedir(u + "/api/hermes/evidencia", b'{"tema":"biologia.celula.0","puntaje":0.9,"ayudas":0}', {"Content-Type": "application/json"})[1]).get("ok")),
                ("dominio: un tema sin evidencia está en el estado 0", json.loads(pedir(u + "/api/dominio/tema?tema=fisica.mediciones.0")[1])["estado"]["nivel"] == 0),
                ("dominio: sin dominar no hay prueba diferida que preparar", "error" in json.loads(pedir(u + "/api/diferida/preparar", b'{"tema":"biologia.celula.0"}', {"Content-Type": "application/json"})[1])),
                ("dominio: pruebas ajenas o inexistentes inaccesibles", "error" in json.loads(pedir(u + "/api/diferida/prueba?id=9999")[1])
                 and "error" in json.loads(pedir(u + "/api/diferida/responder", b'{"id":9999,"respuestas":[]}', {"Content-Type": "application/json"})[1])),
                ("dominio: resumen de estados", "por_nivel" in json.loads(pedir(u + "/api/dominio/estados")[1])),
                ("semanal: texto del resumen para Hermes", "Tu semana en la Academia" in pedir(u + "/api/hermes/semanal")[1]),
                ("código: apagada por defecto y sin ejercicios ajenos", json.loads(pedir(u + "/api/codigo/estado?tema=sistemas.programacion.0")[1]).get("disponible") is False
                 and "error" in json.loads(pedir(u + "/api/codigo/ejercicio?id=9999")[1])
                 and "error" in json.loads(pedir(u + "/api/codigo/ejecutar", b'{"id":9999,"codigo":"x"}', {"Content-Type": "application/json"})[1])
                 and "error" in json.loads(pedir(u + "/api/codigo/solucion", b'{"id":9999}', {"Content-Type": "application/json"})[1])),
                ("tablero: metas, dominio en el tiempo y series", all(k in json.loads(pedir(u + "/api/tablero")[1]) for k in ("metas", "dominio_tiempo", "series", "curva_edad"))),
                ("reporte: trae series, calibración y dominio", all(k in json.loads(pedir(u + "/api/reporte")[1]) for k in ("series", "calibracion", "dominio"))),
                ("acciones: no se ajusta una ajena", "error" in json.loads(pedir(u + "/api/acciones/ajustar", b'{"simbolo":"NVDA"}', {"Content-Type": "application/json"})[1])),
                ("respuestas comprimidas (gzip)", urllib.request.urlopen(urllib.request.Request(u + "/app.js", headers={"Accept-Encoding": "gzip"})).headers.get("Content-Encoding") == "gzip"),
            ]
            for nombre, ok in casos:
                print(("✅ " if ok else "❌ ") + nombre)
                if not ok:
                    fallos.append(nombre)
        finally:
            srv.terminate()
            try:
                salida = srv.communicate(timeout=5)[0]
            except subprocess.TimeoutExpired:
                srv.kill()
                salida = ""
            if fallos and salida:
                print("--- registro del servidor ---\n" + salida[-2000:])
    print(f"\n{'❌ ' + str(len(fallos)) + ' fallo(s)' if fallos else '✅ Todo bien'}")
    sys.exit(1 if fallos else 0)


if __name__ == "__main__":
    main()
