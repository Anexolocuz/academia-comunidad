# 📚 Contenidos ya preparados (apartado independiente)

Este directorio es **opcional e independiente** de la aplicación base (`app/`, `web/`, `curriculo/`).  
Sirve si quieres empezar a estudiar de inmediato con **rutas ampliadas y cientos de lecciones a fondo ya escritas** (con ejercicios, quizzes, tarjetas de repaso y fuentes verificadas), sin esperar a que tu IA local las genere desde cero.

> Al instalar o actualizar la Academia de forma normal (`instalar.sh`, `INSTALAR.bat`, Docker), tus `datos/` **no** cargan este paquete automáticamente. Solo se importa si ejecutas `importar.py`.

## Qué incluye

- [`indice.json`](indice.json): inventario completo de rutas y lecciones disponibles.
- [`rutas/areas_propias.json`](rutas/areas_propias.json): áreas adicionales completas (Estadística para Ingeniería y Finanzas, Ingeniería Eléctrica, Ingeniería Robótica, IA y Automatización, Depuración Android con ADB y Neurociencia).
- [`rutas/rutas_vivas.json`](rutas/rutas_vivas.json): módulos de ampliación generados contra mercado laboral e investigación reciente.
- `lecciones/*.json.gz`: lecciones ya generadas por área (comprimidas con gzip; sin datos personales, sin progreso de estudio y sin notas privadas).

## Cómo importarlo

Desde la raíz del proyecto:

```bash
# Ver qué trae sin modificar nada
python3 contenidos/importar.py --listar

# Importar todas las rutas y lecciones que aún no tengas (no sobrescribe las tuyas)
python3 contenidos/importar.py

# Importar solo una o varias áreas concretas
python3 contenidos/importar.py --area ciberseguridad sistemas matematicas
```

### Opciones útiles

- `--usuario <cuenta>`: si tienes varios perfiles en tu instalación, indica a cuál importarlo (por defecto toma tu perfil local).
- `--datos <carpeta>`: indica otra carpeta `datos/` distinta.
- `--sin-rutas` / `--sin-lecciones`: importa solo una de las dos cosas.
- `--sobrescribir`: reemplaza lecciones o rutas si ya existían en tu base.

Si corres la Academia en Docker con el volumen montado en `./datos`, basta con ejecutar `python3 contenidos/importar.py` desde la máquina anfitriona (o dentro del contenedor tras copiar `contenidos/`).
