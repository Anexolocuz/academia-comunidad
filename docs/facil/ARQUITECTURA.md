# 🏗️ Cómo está hecha — versión fácil

> Todo el detalle (y «Cómo se construyó, para aprender»): [manual completo](../ARQUITECTURA.md)

La Academia es simple a propósito, para que cualquiera pueda leerla y aprender:

| Pieza | Qué es | Dónde |
|---|---|---|
| Servidor | Python puro, sin librerías extra | `app/servidor.py` |
| Base de datos | Un archivo SQLite | `datos/academia.db` |
| IA | Cualquier servidor tipo OpenAI (Ollama, LM Studio…) | `app/ia.py` |
| Lecciones | Las instrucciones (prompts) que recibe la IA | `app/lecciones.py` |
| Memoria | Algoritmo FSRS para repasar | `app/fsrs.py` |
| Pantallas | HTML + JavaScript sin frameworks | `web/` |
| Contenido | Un archivo por área | `curriculo/*.json` |

## Probar cambios sin dañar tus datos

```bash
ACADEMIA_DATOS=/tmp/prueba ACADEMIA_PUERTO=8099 python3 app/servidor.py
python3 pruebas/humo.py
```

¿Quieres aportar? → [CONTRIBUTING.md](../../CONTRIBUTING.md)
