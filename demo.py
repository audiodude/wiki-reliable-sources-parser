import os
import threading
from datetime import datetime, timedelta
from pathlib import Path

from flask import (
    Flask,
    abort,
    redirect,
    render_template_string,
    send_from_directory,
    url_for,
)

from main import run

DATA_DIR = Path(os.environ.get("DATA_DIR", str(Path(__file__).parent))).resolve()
DATA_DIR.mkdir(parents=True, exist_ok=True)

HTML_ROOT = (DATA_DIR / "html").resolve()
WIKITEXT_ROOT = (DATA_DIR / "wikitext").resolve()
HTML_ROOT.mkdir(parents=True, exist_ok=True)
WIKITEXT_ROOT.mkdir(parents=True, exist_ok=True)

# Deliberately outside DATA_DIR so it lives on ephemeral container storage
# and resets on every deploy.
LAST_REFRESH_FILE = Path(__file__).parent / ".last_refresh"
REFRESH_INTERVAL = timedelta(minutes=20)
GITHUB_URL = "https://github.com/audiodude/rspdemo"

_refresh_lock = threading.Lock()
_refresh_running = False


def _read_last_refresh():
    if not LAST_REFRESH_FILE.exists():
        return None
    try:
        return datetime.fromisoformat(LAST_REFRESH_FILE.read_text().strip())
    except ValueError:
        return None


def _write_last_refresh():
    LAST_REFRESH_FILE.write_text(datetime.now().isoformat())


def _background_refresh():
    global _refresh_running
    try:
        run(
            dry_run=False,
            wikitext_output_dir=WIKITEXT_ROOT,
            html_dir=HTML_ROOT,
        )
    except Exception as e:
        print(f"Background refresh failed: {e}")
    finally:
        with _refresh_lock:
            _refresh_running = False


def _refresh_status():
    last = _read_last_refresh()
    now = datetime.now()
    wait_minutes = 0
    if last is not None and now - last < REFRESH_INTERVAL:
        remaining = REFRESH_INTERVAL - (now - last)
        wait_minutes = max(1, int(remaining.total_seconds() // 60) + 1)
    return {
        "last_refresh": last.strftime("%Y-%m-%d %H:%M:%S") if last else None,
        "wait_minutes": wait_minutes,
        "refresh_running": _refresh_running,
        "refresh_disabled": (_refresh_running or wait_minutes > 0),
    }

app = Flask(__name__)

STATUS_BANNER = """
<div class="status-banner" style="position: fixed; top: 0; left: 0; right: 0; background: #eef; border-bottom: 1px solid #99c; padding: 6px 12px; font: 12px sans-serif; color: #333; z-index: 1000;">
  {% if refresh_running %}<b>Refresh in progress...</b>{% endif %}
  Last refreshed: <b>{% if last_refresh %}{{ last_refresh }}{% else %}never{% endif %}</b>.
  {% if wait_minutes %}Next refresh available in {{ wait_minutes }} min.{% else %}Refresh available now.{% endif %}
</div>
"""

WRAPPER_HTML = (
    """<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>{{ name }}</title>
<style>
  body { margin: 0; background: #f5f5f5; font-family: sans-serif; }
  .wrap { max-width: 1200px; margin: 200px auto 0 auto; }
  iframe {
    width: 100%;
    height: calc(100vh - 240px);
    border: 1px solid #ccc;
    background: white;
  }
  .back { margin-bottom: 8px; font-size: 13px; }
  .toolbar { margin-bottom: 8px; font-size: 13px; display: flex; gap: 1em; }
</style>
</head>
<body>
"""
    + STATUS_BANNER
    + """
<div class="wrap">
  <div class="toolbar">
    <a href="{{ parent_url }}">&larr; up</a>
    {% if wikitext_url %}<a href="{{ wikitext_url }}">view wikitext</a>{% endif %}
  </div>
  <iframe src="{{ raw_url }}"></iframe>
</div>
</body>
</html>"""
)

ROOT_INTRO = """
{% if show_refresh %}
<section class="intro">
  <h2>wiki-reliable-sources-parser demo</h2>
  <p>
    Parses the
    <a href="https://en.wikipedia.org/wiki/Wikipedia:Reliable_sources/Perennial_sources">Wikipedia Reliable Sources / Perennial Sources</a>
    tables into structured data, re-renders each source as a standalone wikitext
    page via Jinja templates, and previews the result as rendered HTML via the
    Wikipedia REST API.
  </p>
  <p>
    Source code:
    <a href="{{ github_url }}">{{ github_url }}</a>
  </p>
  <h3>How to use</h3>
  <ul>
    <li>Browse into <code>format1/</code> or <code>format2/</code> below to see candidate layouts.</li>
    <li>Clicking a source opens it in an iframe wrapper. Use <b>view wikitext</b> at the top to see the raw mediawikitext the HTML was rendered from.</li>
    <li>Each generated HTML injects a <code>&lt;script&gt;var data = {...};&lt;/script&gt;</code> block with the full row dict — open devtools and poke <code>data</code> in the console.</li>
    <li>Click <b>Refresh data</b> to re-run the parse pipeline against live Wikipedia. It is fire-and-forget and rate-limited to once per 20 minutes; the status banner at the top of every page shows the last refresh time.</li>
    <li>On the hosted deployment the Wikipedia access token is intentionally unset, so the refresh will not successfully post anything back to Wikipedia.</li>
  </ul>
</section>
{% endif %}
"""

LISTING_HTML = (
    """<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>Index of /{{ rel }}</title>
<style>
  body { font-family: monospace; margin: 2em; padding-top: 2em; max-width: 900px; }
  a { text-decoration: none; }
  li { padding: 2px 0; }
  form.refresh { margin: 1em 0; }
  form.refresh button { font-family: inherit; padding: 0.4em 0.8em; cursor: pointer; }
  section.intro { font-family: sans-serif; color: #222; line-height: 1.5; }
  section.intro h2 { margin-top: 1em; }
  section.intro code { background: #f0f0f0; padding: 1px 4px; border-radius: 3px; }
</style>
</head>
<body>
"""
    + STATUS_BANNER
    + ROOT_INTRO
    + """
<h1>Index of /{{ rel }}</h1>
{% if show_refresh %}
<form class="refresh" method="post" action="{{ refresh_url }}">
  <button type="submit"{% if refresh_disabled %} disabled{% endif %}>
    {% if refresh_running %}Refresh in progress...{% else %}Refresh data{% endif %}
  </button>
</form>
{% endif %}
<ul>
{% if parent_url %}<li><a href="{{ parent_url }}">../</a></li>{% endif %}
{% for entry in entries %}
  <li><a href="{{ entry.url }}">{{ entry.name }}{% if entry.is_dir %}/{% endif %}</a></li>
{% endfor %}
</ul>
</body>
</html>"""
)


def _safe_target(subpath: str) -> Path:
    target = (HTML_ROOT / subpath).resolve()
    if target != HTML_ROOT and HTML_ROOT not in target.parents:
        abort(404)
    if not target.exists():
        abort(404)
    return target


def _parent_url(subpath: str) -> str:
    if not subpath:
        return url_for("browse")
    parent = Path(subpath).parent
    if str(parent) in (".", ""):
        return url_for("browse")
    return url_for("browse", subpath=parent.as_posix())


@app.route("/")
@app.route("/<path:subpath>")
def browse(subpath: str = ""):
    target = _safe_target(subpath)

    if target.is_dir():
        index = target / "index.html"
        if index.exists():
            index_rel = (
                (Path(subpath) / "index.html").as_posix() if subpath else "index.html"
            )
            return redirect(url_for("browse", subpath=index_rel))

        entries = []
        for p in sorted(
            target.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower())
        ):
            rel = (Path(subpath) / p.name).as_posix() if subpath else p.name
            entries.append(
                {
                    "name": p.name,
                    "url": url_for("browse", subpath=rel),
                    "is_dir": p.is_dir(),
                }
            )
        return render_template_string(
            LISTING_HTML,
            rel=subpath,
            entries=entries,
            parent_url=_parent_url(subpath) if subpath else None,
            show_refresh=(subpath == ""),
            refresh_url=url_for("refresh"),
            github_url=GITHUB_URL,
            **_refresh_status(),
        )

    if target.name == "index.html":
        return send_from_directory(str(target.parent), "index.html")

    wikitext_subpath = subpath
    if wikitext_subpath.endswith(".html"):
        wikitext_subpath = wikitext_subpath[: -len(".html")] + ".mediawikitext"
    wikitext_file = (WIKITEXT_ROOT / wikitext_subpath).resolve()
    wikitext_url = None
    if (
        wikitext_file.is_file()
        and (wikitext_file == WIKITEXT_ROOT or WIKITEXT_ROOT in wikitext_file.parents)
    ):
        wikitext_url = url_for("wikitext", subpath=wikitext_subpath)

    return render_template_string(
        WRAPPER_HTML,
        name=target.name,
        raw_url=url_for("raw", subpath=subpath),
        parent_url=_parent_url(subpath),
        wikitext_url=wikitext_url,
        **_refresh_status(),
    )


@app.route("/refresh", methods=["POST"])
def refresh():
    global _refresh_running
    last = _read_last_refresh()
    now = datetime.now()
    if last is not None and now - last < REFRESH_INTERVAL:
        return redirect(url_for("browse"))
    with _refresh_lock:
        if _refresh_running:
            return redirect(url_for("browse"))
        _refresh_running = True
        _write_last_refresh()
    threading.Thread(target=_background_refresh, daemon=True).start()
    return redirect(url_for("browse"))


@app.route("/wikitext/<path:subpath>")
def wikitext(subpath: str):
    target = (WIKITEXT_ROOT / subpath).resolve()
    if target != WIKITEXT_ROOT and WIKITEXT_ROOT not in target.parents:
        abort(404)
    if not target.is_file():
        abort(404)
    return send_from_directory(str(WIKITEXT_ROOT), subpath, mimetype="text/plain")


@app.route("/raw/<path:subpath>")
def raw(subpath: str):
    target = _safe_target(subpath)
    if not target.is_file():
        abort(404)
    return send_from_directory(str(HTML_ROOT), subpath)


if __name__ == "__main__":
    app.run(debug=True, port=5000)
