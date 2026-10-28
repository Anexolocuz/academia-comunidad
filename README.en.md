# 🎓 Academia — your personal school with local AI

**Academia** is a self-hosted study app: learning paths for 20 fields (~940 topics, plus your own) written in depth
by an AI that runs **on your own PC**, with web sources and real scientific papers (OpenAlex), quizzes, the Feynman
technique, exercises submitted by photo or handwriting, **spaced repetition (FSRS)**, a pen notebook, a tutor,
goal-based roadmaps, news compared across outlets, weekly check-ups and professional level per field.

> **A community project.** Only the **software** is donated — each person installs and runs it on **their own
> computer** with their own AI. No cloud, no accounts, no telemetry. The interface is currently in **Spanish**
> (translations welcome!).

## Quick start

1. Install [Ollama](https://ollama.com/download) and run `ollama pull gemma3:4b`.
2. Download this repo (Releases → zip, or `git clone`).
3. Run the installer: **Windows** `INSTALAR.bat` · **macOS** `Instalar.command` · **Linux** `./instalar.sh`
   (add `--auto` for no questions) — or **Docker**: `./docker/arrancar.sh` / `docker\arrancar.ps1`, or
   `docker compose --profile ollama --profile buscador up -d` (set `SEARXNG_SECRET` in `.env` first).
4. Open **http://127.0.0.1:8092** → ⚙️ Ajustes → 🪄 **Escanear mi PC** (auto-scan with yes/no consent; the scan is
   deleted after 24 h) → **Aplicar**.

## Highlights

- 🔒 Local-first and closed by default: only this PC can connect; phones via Tailscale or a LAN access key.
  CSRF, DNS-rebinding and header-spoofing protections; non-root read-only Docker image.
- 💹 Stock watchlist: alerts, direct and indirect news (competitors, suppliers, macro factors), scenario forecasts
  from "very likely" to "very unlikely" anchored to the stock's own base rate, scored (Brier) when they expire, plus an
  optional portfolio view with diversification risk. Educational only — not financial advice.
- 🧠 Works with any OpenAI-compatible server (Ollama, LM Studio, llama.cpp, llama-swap, vLLM, Jan).
- 🎨 Light/dark, 6 palettes (incl. high contrast), custom accent, font scaling; PWA on Android/iOS.
- 🧩 Zero dependencies: Python standard library + vanilla HTML/JS — easy to read and learn from.
- 🏷️ One version everywhere (`VERSION` → git tag → Docker image `ghcr.io/anexolocuz/academia-comunidad` → release zip).

Docs are in Spanish under [`docs/`](docs/) (easy versions in [`docs/facil/`](docs/facil/)).
License: [AGPL-3.0-or-later](LICENSE).
