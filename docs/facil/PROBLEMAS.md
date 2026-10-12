# 🩺 Si algo falla — versión fácil

> Todo el detalle: [manual completo](../SOLUCION_DE_PROBLEMAS.md)

Prueba en este orden:

1. **¿Abre `http://127.0.0.1:8092`?** Si no → reinicia el PC (o `systemctl --user restart academia` en Linux).
2. **¿La IA responde?** → Ajustes → 🪄 **Escanear mi PC**. Te dice qué falta y cómo arreglarlo.
3. **¿Ollama está abierto?** Ábrelo (en Windows/Mac es una app; en Linux `ollama serve`).

| Veo esto | Haz esto |
|---|---|
| «solo acepta conexiones desde su propio PC» | Entra desde el PC, o usa Tailscale / clave ([CELULAR](CELULAR.md)) |
| «En cola…» mucho rato | Normal: la IA está ocupada; sigue sola |
| Lecciones muy lentas | Usa un modelo más pequeño (el escaneo te dice cuál) |
| No lee mis apuntes | Usa un modelo con visión (`gemma3`) |
| El celular no abre | Tailscale encendido en el PC y en el celular |

¿Nada de esto? Abre un *issue* en GitHub con lo que ves (sin datos personales).
