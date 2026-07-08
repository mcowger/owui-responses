# Agents Guide

## Deploying to Open WebUI


### Upload / update

```bash
mise exec -- uv run python upload.py            # dist/responses.py (default)
mise exec -- uv run python upload.py gemini     # dist/gemini.py
mise exec -- uv run python upload.py anthropic  # dist/anthropic_function.py
mise exec -- uv run python upload.py context    # dist/context.py
```

The target may be a bare name (`gemini`), a filename (`gemini.py`), or a
path; bare names get `.py` appended. Known targets upload the generated
single-file artifacts from `dist/`. This pushes the file to the live Open WebUI instance via
`POST /api/v1/functions/id/<function_id>/update`. The function reloads
immediately — no restart required.

### First-time create (if the function doesn't exist yet)

```bash
mise exec -- uv run python upload.py anthropic --create
```

## Development workflow

1. Edit source under `src/owui_manifolds/`
2. Run `uv run python scripts/build_functions.py`
3. Commit both source changes and generated `dist/*.py`
4. Run `mise exec -- uv run python upload.py <target>` to deploy

Use `uv run python scripts/build_functions.py --check` in tests/CI to ensure
committed `dist/` artifacts match the modular source.

## Environment and live-system safety

Use `mise exec -- <command>` for any command that needs Open WebUI credentials
or live instance configuration. Do not rely on `source .env`,
`python-dotenv`, or `dotenv_values()` in verification scripts; this repo's
working environment is provided by mise, and `.env` may be absent, incomplete,
or intentionally different from the active shell environment.

Examples:

```bash
mise exec -- uv run python upload.py responses
mise exec -- bash -lc 'BASE="${OWUI_URL%/}"; curl -s "$BASE/api/models?refresh=true" -H "Authorization: Bearer $OWUI_API_KEY"'
```

Do not run live chat completions, mutate existing chats, upload functions, or
trigger provider requests unless the user has explicitly asked for that live
operation in the current task. Read-only inspection of a user-provided chat ID
is acceptable when debugging an error, but new completions and uploads affect
the live system and should be called out before running.

When a live verification is approved, prefer creating a new chat unless the
user specifically asks to test in an existing chat. If you must use an existing
chat, state the chat ID and what will be posted before sending the request.

## Reviewing a conversation for errors

Use the Open WebUI API to fetch a chat by ID and inspect its message history,
status history, and error logs. You'll need to execute using
`mise exec -- <command>` to get the appropriate environment variables.

Always retrieve chats in two separate steps — download to a file first, then
analyze that file. Never pipe the response directly into `python`/`json.tool`;
it's inefficient and discards the raw data.

```bash
export CHAT_ID=282df76e-c702-4768-9351-b7ae11b219be

# 1. Download to a file
mise exec -- bash -lc 'BASE="${OWUI_URL%/}"; curl -s "$BASE/api/v1/chats/$CHAT_ID" -H "Authorization: Bearer $OWUI_API_KEY" -o "/tmp/chat_$CHAT_ID.json"'

# 2. Analyze the file
python3 -m json.tool /tmp/chat_$CHAT_ID.json
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

## Verifying a pipe end-to-end in Open WebUI

Do not stop at local syntax/import checks when changing a pipe. For Open WebUI
manifolds, verify the live behavior through the Open WebUI API after the user
approves live verification.

Recommended workflow:

1. **Upload the updated function**
   ```bash
   mise exec -- uv run python upload.py gemini --id google_gemini_manifold
   ```

2. **Confirm the manifold models are registered**
   ```bash
   mise exec -- bash -lc 'BASE="${OWUI_URL%/}"; curl -s "$BASE/api/models?refresh=true" -H "Authorization: Bearer $OWUI_API_KEY"' | python3 -m json.tool
   ```

   Check that the expected model IDs appear in `data[]`, e.g.
   `google_gemini_manifold.gemini-3.5-flash`.

3. **Run a real chat completion through Open WebUI**
   Prefer calling `/api/chat/completions` (or `/api/v1/chat/completions`) with a
   real `chat_id`, `user_message`, and assistant `id` so Open WebUI persists the
   turn exactly as the UI would.

   Minimal pattern:
   ```bash
   mise exec -- uv run python - <<'PY'
   import os
   import time
   import uuid

   import requests

   base = os.environ['OWUI_URL'].rstrip('/')
   key = os.environ['OWUI_API_KEY']
   headers = {'Authorization': f'Bearer {key}', 'Content-Type': 'application/json'}

   model = 'google_gemini_manifold.gemini-3.5-flash'
   chat_id = str(uuid.uuid4())
   user_id = str(uuid.uuid4())
   assistant_id = str(uuid.uuid4())
   now = int(time.time())
   prompt = 'Reply with exactly: OK'

   payload = {
       'model': model,
       'stream': False,
       'messages': [{'role': 'user', 'content': prompt}],
       'parent_id': None,
       'chat_id': chat_id,
       'id': assistant_id,
       'user_message': {
           'id': user_id,
           'role': 'user',
           'content': prompt,
           'parentId': None,
           'childrenIds': [assistant_id],
           'timestamp': now,
           'models': [model],
       },
   }

   print(requests.post(f'{base}/api/chat/completions', headers=headers, json=payload, timeout=120).text)
   PY
   ```

   Synthetic requests must match the real UI/Open WebUI request shape closely
   enough to exercise the bug being tested. Include the same `model`, `stream`
   mode, `chat_id`, `id`, `user_message`, `parent_id`, `messages`, tools, and
   provider-specific options that were present in the failing request. If the
   failure came from a proxy log or stored chat, save that raw request/response
   as a fixture and write the regression test against it. Do not treat a
   smaller hand-written payload as proof unless it preserves the failing shape.

4. **Read back the stored chat message**
   Fetch the chat via `/api/v1/chats/<chat_id>` and inspect the persisted
   assistant message, not just the HTTP response body.

   Verify all of the following:
   - the assistant `content` is clean and user-visible
   - no internal markers/tags leaked into `content`
   - any hidden persistence data lives in non-visible message fields
   - `statusHistory` shows a clean successful flow

5. **If a model shows in admin but not in chat dropdowns**
   Query `/api/models?refresh=true`. If the manifold's submodels are absent
   there, the function module likely failed to load or its `pipes()` method
   failed at runtime.

What this caught for `gemini.py`:
- module-load failures can prevent manifold models from appearing in `/api/models`
- Developer API rejects some SDK fields even when the type exists in docs
- Open WebUI may render/store anything appended to assistant `content`, so
  persistence state must not be hidden in visible content strings
  (Markdown refs and HTML comments both leaked into chat output)
  — store hidden IDs in per-message metadata instead

## Environment variables

| Variable       | Description                          |
|----------------|--------------------------------------|
| `OWUI_URL`     | Base URL of your Open WebUI instance |
| `OWUI_API_KEY` | Admin API key (`sk-...`)             |

`.env` is gitignored. Never commit credentials.
