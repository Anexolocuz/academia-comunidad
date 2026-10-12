# 🔒 Seguridad

## Versiones con soporte

Solo la última versión publicada (ver [VERSION](VERSION) y Releases). Actualiza antes de reportar.

## Reportar una vulnerabilidad

**No abras un issue público.** Usa **Security → Report a vulnerability** en este repositorio de GitHub (mensaje
privado). Incluye la versión, cómo reproducirlo y el impacto. Respondemos lo antes posible; es un proyecto
comunitario sin equipo de guardia, así que ten paciencia.

## Modelo de amenazas (resumen)

La Academia corre en el PC de cada persona y por defecto **solo acepta conexiones de ese PC**. Se consideran fallos
de seguridad, entre otros:

- entrar o administrar desde otro equipo sin Tailscale ni `clave_acceso`;
- ver o modificar datos de otro perfil;
- que una página web externa logre ejecutar acciones en la Academia (CSRF, DNS rebinding, XSS);
- que el contenido de RSS, la web o la IA ejecute código en el navegador;
- leer archivos fuera de las carpetas previstas;
- que datos personales salgan del PC sin que la documentación lo diga.

Detalle de las protecciones: [docs/SEGURIDAD_Y_DATOS.md](docs/SEGURIDAD_Y_DATOS.md).
