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
3. Run `./upload.sh` to deploy

## Reviewing a conversation for errors

Use the Open WebUI API to fetch a chat by ID and inspect its message history,
status history, and error logs.

```bash
CHAT_ID=282df76e-c702-4768-9351-b7ae11b219be

curl -s "https://owui.home.cowger.us/api/v1/chats/$CHAT_ID" \
  -H "Authorization: Bearer $OWUI_API_KEY" | python3 -m json.tool
```

Or source the `.env` file first:

```bash
source .env
curl -s "$OWUI_URL/api/v1/chats/$CHAT_ID" \
  -H "Authorization: Bearer $OWUI_API_KEY" | python3 -m json.tool
```

Key fields to look at in the response:

| Field | What to look for |
|---|---|
| `chat.history.messages.<id>.statusHistory` | Per-message status steps and error descriptions |
| `chat.history.messages.<id>.sources` | Attached error log citations from the manifold |
| `chat.history.messages.<id>.content` | Final assistant response (empty string = failed turn) |
| `chat.history.messages.<id>.done` | `false` means the turn never completed |

Error details (stack traces, API error messages) are captured in the `sources`
array of the assistant message under `source.name = "Error Logs"`.

## Environment variables

| Variable       | Description                          |
|----------------|--------------------------------------|
| `OWUI_URL`     | Base URL of your Open WebUI instance |
| `OWUI_API_KEY` | Admin API key (`sk-...`)             |

`.env` is gitignored. Never commit credentials.
