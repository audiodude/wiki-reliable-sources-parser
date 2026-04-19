# wiki-reliable-sources-parser

Parses the [Wikipedia Reliable Sources / Perennial Sources](https://en.wikipedia.org/wiki/Wikipedia:Reliable_sources/Perennial_sources) tables into structured data, re-renders each source as a standalone wikitext page via Jinja templates, and optionally previews the result as rendered HTML.

Context:
- https://en.wikipedia.org/wiki/Wikipedia:Requests_for_comment/Restructuring_RSP
- https://phabricator.wikimedia.org/tag/english-wikipedia-rsp-restructuring/

## Live demo

A hosted preview of the output lives at **https://rspdemo.vibes.travisbriggs.com**.

## CLI usage

```bash
uv sync

# Render each source to a wikitext file and fetch its HTML preview:
uv run python main.py \
  --dry-run \
  --wikitext-output-dir wikitext \
  --html-dir html
```

Key flags:

| Flag | Description |
| --- | --- |
| `--dry-run / --no-dry-run` | If true (default), skip posting to Wikipedia. |
| `--use-cache / --no-use-cache` | Use on-disk cache of raw RSP pages (default: true). |
| `--wikitext-output-dir DIR` | Write each rendered row to `DIR/<format>/<id>.mediawikitext`. |
| `--html-dir DIR` | Call the Wikipedia REST API to render wikitext → HTML, write to `DIR/<format>/<id>.html`. |
| `--skip-to NAME` | Skip sources until `NAME` (by sort key). |
| `--limit N` | Process only the first N sources. |

HTML generation is Make-style dependent on the wikitext file: if `<id>.mediawikitext` hasn't changed since the last run, the HTML file is left alone (no REST API call).

Each generated HTML has a styled `<h1>` with the source's qualified name and a `<script>var data = {...};</script>` block containing the full row dict.

## Web demo (`demo.py`)

A small Flask app for browsing the generated HTML:

```bash
uv run python demo.py   # http://localhost:5000
```

- `/` — Apache-style directory listing of the `html/` tree, with a **Refresh data** button.
- Clicking a source opens a wrapper page with the HTML in an iframe (max-width 1200px, 200px top margin), plus a **view wikitext** link to the raw `.mediawikitext`.
- The **Refresh data** button is fire-and-forget: it spawns the CLI's `run()` in a daemon thread and rate-limits to one refresh per 20 minutes. A persistent status banner at the top of every page shows the last refresh timestamp.

### Environment variables

| Var | Purpose |
| --- | --- |
| `DATA_DIR` | Root directory for `html/`, `wikitext/`, and `cache/`. Defaults to the repo directory locally. |
| `WIKIPEDIA_ACCESS_TOKEN` | OAuth token for authenticated Wikipedia API calls. Only needed for non-dry-run posts; safe to leave empty for read-only previewing. |

## Deployment (Railway)

- Project name: **rspdemo**
- Host: **rspdemo.vibes.travisbriggs.com**
- Deploy flow: merge `main` → `release`, push. Railway auto-deploys from the `release` branch.
- Start command: `gunicorn demo:app -b 0.0.0.0:$PORT --workers 2 --timeout 120` (see `Procfile`).
- Persistence: a Railway volume is mounted at `/data`, and `DATA_DIR=/data` is set on the service. `html/`, `wikitext/`, and `cache/` live inside the volume so they survive deploys. `.last_refresh` deliberately lives outside the volume on ephemeral container storage so the refresh rate limit resets on every deploy.
- `WIKIPEDIA_ACCESS_TOKEN` is intentionally left **unset** on the hosted service — the Refresh button will not successfully post to Wikipedia from production.

Custom domain setup uses two Cloudflare DNS records (Railway's certificate issuance requires both):
1. `CNAME rspdemo.vibes` → the Railway-provided target (e.g. `xxxx.up.railway.app`).
2. `TXT _railway-verify.rspdemo.vibes` → the verification token from Railway.
