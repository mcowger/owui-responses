# Agents Guide

## Project Overview

`responses.py` is a single-file Open WebUI pipe function (manifold) that proxies requests
through the OpenAI Responses API. It is bundled from multiple source modules at build time.

## Deploying to Open WebUI

### One-time setup

```bash
cp .env.example .env
# Edit .env and fill in OWUI_URL and OWUI_API_KEY
```

### Upload / update

```bash
./upload.sh
```

This pushes `responses.py` to the live Open WebUI instance via
`POST /api/v1/functions/id/openai_responses_manifold/update`.
The function reloads immediately — no restart required.

### First-time create (if the function doesn't exist yet)

```bash
uv run python upload.py --create
```

## Development workflow

1. Edit `responses.py`
2. Commit your changes
3. Run `uv run upload` to deploy

## Environment variables

| Variable       | Description                          |
|----------------|--------------------------------------|
| `OWUI_URL`     | Base URL of your Open WebUI instance |
| `OWUI_API_KEY` | Admin API key (`sk-...`)             |

`.env` is gitignored. Never commit credentials.
