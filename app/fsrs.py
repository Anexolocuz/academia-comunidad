"""Repetición espaciada con FSRS-4.5 (Free Spaced Repetition Scheduler).

Es el algoritmo que usa Anki desde la 23.10: modela para cada tarjeta su
*estabilidad* S (días hasta que la probabilidad de recordarla cae al 90 %) y su
*dificultad* D (1..10), y programa el siguiente repaso justo cuando estás por
olvidarla. Así se estudia lo mínimo para recordar lo máximo.

Notas: 1 = Otra vez (la olvidé), 2 = Difícil, 3 = Bien, 4 = Fácil.
"""
import math
import time

W = [0.4872, 1.4003, 3.7145, 13.8206, 5.1618, 1.2298, 0.8975, 0.031, 1.6474,
     0.1367, 1.0461, 2.1072, 0.0793, 0.3246, 1.587, 0.2272, 2.8755]
DECAY = -0.5
FACTOR = 19 / 81
RETENCION = 0.9          # objetivo: recordar el 90 %
MAX_DIAS = 3650
DIA = 86400


def retenibilidad(dias, S):
    if not S:
        return 0.0
    return (1 + FACTOR * max(dias, 0) / S) ** DECAY


def intervalo(S, r=RETENCION):
    d = S / FACTOR * (r ** (1 / DECAY) - 1)
    return min(max(1, round(d)), MAX_DIAS)


def _d0(g):
    return min(max(W[4] - (g - 3) * W[5], 1), 10)


def programar(tarjeta, nota, ahora=None):
    """Devuelve dict con estabilidad, dificultad, vence, ultimo, retenibilidad."""
    ahora = ahora or time.time()
    S, D, ultimo = tarjeta.get("estabilidad"), tarjeta.get("dificultad"), tarjeta.get("ultimo")
    if not S:  # primera vez
        S, D, R = W[nota - 1], _d0(nota), None
    else:
        dias = (ahora - (ultimo or ahora)) / DIA
        R = retenibilidad(dias, S)
        D2 = D - W[6] * (nota - 3)
        D = min(max(W[7] * _d0(3) + (1 - W[7]) * D2, 1), 10)
        if nota == 1:
            S = W[11] * D ** -W[12] * ((S + 1) ** W[13] - 1) * math.exp(W[14] * (1 - R))
        elif dias < 0.5:  # repaso el mismo día: crecimiento pequeño, no premiar el atracón
            S = S * (1.05 if nota >= 3 else 1.0)
        else:
            mult = W[15] if nota == 2 else (W[16] if nota == 4 else 1)
            S = S * (math.exp(W[8]) * (11 - D) * S ** -W[9]
                     * (math.exp(W[10] * (1 - R)) - 1) * mult + 1)
    S = max(S, 0.1)
    if nota == 1:
        vence = ahora + 10 * 60            # vuelve en esta misma sesión
    elif nota == 2 and not tarjeta.get("estabilidad"):
        vence = ahora + 12 * 3600          # nueva y difícil: mañana temprano
    else:
        vence = ahora + intervalo(S) * DIA
    return {"estabilidad": S, "dificultad": D, "vence": vence, "ultimo": ahora,
            "retenibilidad": R}


def vista_previa(tarjeta, ahora=None):
    """Texto de cuándo volvería cada botón (para mostrar bajo los botones)."""
    ahora = ahora or time.time()
    out = {}
    for n in (1, 2, 3, 4):
        seg = programar(tarjeta, n, ahora)["vence"] - ahora
        if seg < 3600:
            out[n] = f"{round(seg / 60)} min"
        elif seg < DIA:
            out[n] = f"{round(seg / 3600)} h"
        elif seg < 30 * DIA:
            out[n] = f"{round(seg / DIA)} d"
        elif seg < 365 * DIA:
            out[n] = f"{seg / (30 * DIA):.1f} m"
        else:
            out[n] = f"{seg / (365 * DIA):.1f} a"
    return out
