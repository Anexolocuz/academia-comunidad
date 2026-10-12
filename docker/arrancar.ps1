# Academia en Docker, guiado con preguntas sí/no (Windows, PowerShell).
# Uso: clic derecho → «Ejecutar con PowerShell», o:  powershell -ExecutionPolicy Bypass -File docker\arrancar.ps1
$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) { Write-Host "Necesitas Docker Desktop: https://docs.docker.com/desktop/setup/install/windows-install/"; Read-Host "Enter para salir"; exit 1 }

function Si($texto) { $r = Read-Host "$texto [s/n]"; return ($r -eq "" -or $r -match "^[sSyY]") }
if (-not (Test-Path .env)) { New-Item .env -ItemType File | Out-Null }
$envs = @{}; Get-Content .env | Where-Object { $_ -match "=" } | ForEach-Object { $k, $v = $_ -split "=", 2; $envs[$k] = $v }
if (-not $envs.SEARXNG_SECRET) { $envs.SEARXNG_SECRET = -join ((1..32) | ForEach-Object { "{0:x2}" -f (Get-Random -Max 256) }) }
$envs.ACADEMIA_VERSION = (Get-Content VERSION).Trim()

$perfiles = @(); $extra = @()
if (Si "¿Incluir la IA (Ollama) dentro de Docker? (no, si ya tienes Ollama/LM Studio en este PC)") {
  $perfiles += "--profile", "ollama"; $envs.IA_URL = "http://ollama:11434"
  if ((Get-Command nvidia-smi -ErrorAction SilentlyContinue) -and (Si "Detecté una tarjeta NVIDIA. ¿Usarla?")) { $extra += "-f", "docker-compose.yml", "-f", "docker/nvidia.yml" }
} else {
  $envs.IA_URL = "http://host.docker.internal:11434"
  Write-Host "  -> En Windows, Ollama de escritorio ya es accesible desde Docker. Igual puedes cambiarlo en Ajustes."
}
if (Si "¿Incluir un buscador web privado (SearXNG)?") { $perfiles += "--profile", "buscador"; $envs.BUSCADOR_URL = "http://searxng:8080" } else { $envs.BUSCADOR_URL = "" }
$envs.GetEnumerator() | ForEach-Object { "$($_.Key)=$($_.Value)" } | Set-Content .env -Encoding ascii

docker compose @extra @perfiles up -d --build
if (($perfiles -contains "ollama") -and (Si "¿Descargar ya el modelo recomendado (gemma3:4b, ~3 GB)?")) { docker compose @extra @perfiles exec ollama ollama pull gemma3:4b }
Write-Host "`nLista: abre http://127.0.0.1:8092  ->  Ajustes -> Configuración automática"
Start-Process "http://127.0.0.1:8092"
Read-Host "Enter para cerrar"
