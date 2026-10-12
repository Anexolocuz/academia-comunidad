# Academia — imagen mínima: Python estándar, sin dependencias. La IA va en otro contenedor (Ollama) o en tu PC.
FROM python:3.14-slim
ARG VERSION=dev
LABEL org.opencontainers.image.title="Academia" \
      org.opencontainers.image.description="Escuela personal con IA local" \
      org.opencontainers.image.licenses="AGPL-3.0-or-later" \
      org.opencontainers.image.version="${VERSION}"
# usuario sin privilegios; los datos van en el volumen /datos
RUN useradd --create-home --uid 1000 academia && mkdir /datos && chown academia /datos
WORKDIR /app
COPY --chown=root:root VERSION ./
COPY --chown=root:root app ./app
COPY --chown=root:root web ./web
COPY --chown=root:root curriculo ./curriculo
COPY --chown=root:root config ./config
USER academia
ENV ACADEMIA_DATOS=/datos \
    ACADEMIA_HOST=0.0.0.0 \
    ACADEMIA_PUERTO=8092 \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1
EXPOSE 8092
VOLUME ["/datos"]
HEALTHCHECK --interval=60s --timeout=5s --start-period=30s \
  CMD python -c "import urllib.request;urllib.request.urlopen('http://127.0.0.1:8092/manifest.webmanifest',timeout=4)"
CMD ["python", "app/servidor.py"]
