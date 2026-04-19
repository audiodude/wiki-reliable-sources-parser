import json
import re
import time
from html import escape as html_escape
from pathlib import Path
from urllib.parse import quote

import mwclient
import requests
import typer
from dotenv import load_dotenv
from jinja2 import Environment, FileSystemLoader, select_autoescape

from parser import USER_AGENT, IncompleteParseError, get_site, parse

load_dotenv()

app = typer.Typer()

jinja = Environment(
    loader=FileSystemLoader("templates"),
    autoescape=select_autoescape(["html", "xml"]),
    block_start_string="@@",
    block_end_string="@@",
    variable_start_string="@=",
    variable_end_string="=@",
)

FORMATS = ("format1", "format2")


def create_subpage(jinja, page_format, data):
    page = {}
    page["title"] = (
        f"User:Audiodude/RSPTest/{page_format}/{data.get('qualified_name', data.get('name'))}"
    )
    template = jinja.get_template(page_format)
    page["update"] = template.render(data)
    return page


def wikitext_to_html(title, wikitext, max_retries=3, max_retry_sleep=60):
    url = "https://en.wikipedia.org/api/rest_v1/transform/wikitext/to/html/" + quote(
        title, safe=""
    )
    for attempt in range(max_retries):
        response = requests.post(
            url,
            data={"wikitext": wikitext},
            headers={"User-Agent": USER_AGENT},
            timeout=30,
        )
        if response.status_code == 429:
            raw_retry = int(response.headers.get("Retry-After", 2 ** (attempt + 1)))
            # Wikipedia sometimes returns Retry-After in the thousands of
            # seconds when an IP hits a bucket limit. Don't actually hold
            # the worker hostage for that long — cap the sleep and let the
            # final attempt surface as a failure so the operator can retry
            # later rather than having a refresh thread stuck for an hour.
            sleep_for = min(raw_retry, max_retry_sleep)
            print(
                f"REST API rate-limited ({title!r}); "
                f"Retry-After={raw_retry}s, sleeping {sleep_for}s "
                f"(attempt {attempt + 1}/{max_retries})"
            )
            time.sleep(sleep_for)
            continue
        response.raise_for_status()
        return response.text
    response.raise_for_status()
    return response.text


HEADER_STYLE = (
    "font-family: 'Linux Libertine', Georgia, Times, serif;"
    " font-size: 1.8em; font-weight: normal;"
    " border-bottom: 1px solid #a2a9b1;"
    " padding-bottom: 0.25em; margin: 0 0 0.5em 0;"
)


def inject_header_and_data(html, data):
    heading = data.get("qualified_name", data.get("name", ""))
    json_blob = json.dumps(data, ensure_ascii=False, default=str).replace(
        "</", "<\\/"
    )
    injection = (
        f'<h1 class="firstHeading" style="{HEADER_STYLE}">'
        f"{html_escape(heading)}</h1>\n"
        f"<script>var data = {json_blob};</script>\n"
    )
    body_open = re.search(r"<body\b[^>]*>", html)
    if body_open:
        idx = body_open.end()
        return html[:idx] + "\n" + injection + html[idx:]
    return injection + html


def save_with_retry(wiki_page, content, summary, max_retries=5):
    for attempt in range(max_retries):
        try:
            wiki_page.save(content, summary=summary)
            return
        except mwclient.errors.APIError as e:
            if e.code in ("ratelimited", "actionthrottled"):
                wait_seconds = 2**attempt
                print(
                    f"Rate limited. Waiting {wait_seconds} seconds before retry {attempt + 1}/{max_retries}"
                )
                time.sleep(wait_seconds)
            else:
                raise

    raise Exception(f"Max retries exceeded for rate limit on page: {wiki_page.name}")


def run(
    limit=None,
    use_cache=True,
    dry_run=True,
    skip_to=None,
    wikitext_output_dir=None,
    html_dir=None,
):
    format_to_sources = {fmt: [] for fmt in FORMATS}
    site = get_site() if not dry_run else None
    try:
        for data in parse(use_cache=use_cache):
            if skip_to and data["sort_name"] < skip_to:
                continue

            for page_format in FORMATS:
                page = create_subpage(jinja, page_format, data)
                summary = f"Test page for RSPS with {page_format}"
                format_to_sources[page_format].append(
                    {
                        "link": page["title"],
                        "name": data.get("qualified_name", data.get("name")),
                    }
                )

                safe_id = data["id"].replace("/", "_")
                wikitext_file = None
                if wikitext_output_dir is not None:
                    out_dir = wikitext_output_dir / page_format
                    out_dir.mkdir(parents=True, exist_ok=True)
                    wikitext_file = out_dir / f"{safe_id}.mediawikitext"
                    # Only rewrite if content changed, so mtime stays stable
                    # for downstream dependency tracking.
                    existing = (
                        wikitext_file.read_text(encoding="utf-8")
                        if wikitext_file.exists()
                        else None
                    )
                    if existing != page["update"]:
                        wikitext_file.write_text(page["update"], encoding="utf-8")

                if html_dir is not None:
                    out_dir = html_dir / page_format
                    out_dir.mkdir(parents=True, exist_ok=True)
                    html_file = out_dir / f"{safe_id}.html"
                    up_to_date = (
                        wikitext_file is not None
                        and wikitext_file.exists()
                        and html_file.exists()
                        and html_file.stat().st_mtime
                        >= wikitext_file.stat().st_mtime
                    )
                    if not up_to_date:
                        html = wikitext_to_html(page["title"], page["update"])
                        html = inject_header_and_data(html, data)
                        html_file.write_text(html, encoding="utf-8")

                # Only print title and skip saving page to wiki if dry-run is enabled
                if dry_run:
                    print(f"--- {page['title']} --- {page_format}")
                    continue

                wiki_page = site.pages[page["title"]]
                print(
                    f"Updating https://en.wikipedia.org/wiki/{page['title'].replace(' ', '_')}"
                )
                try:
                    save_with_retry(wiki_page, page["update"], summary)
                    # Be polite to Wikipedia's servers
                    time.sleep(1)
                except mwclient.errors.APIError as e:
                    if (
                        e.code == "abusefilter-warning"
                        or e.code == "abusefilter-blocked-domains-attempted"
                    ):
                        pass
                    else:
                        print(page["title"])
                        print(page["update"])
                        raise

            if limit is not None:
                limit -= 1
                if limit == 0:
                    return

        # Create index pages
        for page_format, sources in format_to_sources.items():
            template = jinja.get_template("index1")
            index_page = template.render(sites=sources)
            wiki_page = site.pages[f"User:Audiodude/RSPTest/{page_format}/Index"]
            save_with_retry(
                wiki_page,
                index_page,
                summary=f"Update index page for {page_format} pages",
            )
    except IncompleteParseError as e:
        print(f"Error during parsing:\n{e}\nPartial row follows:\n{e.alltext}")


@app.command()
def main(
    limit: int = typer.Option(None, help="Maximum number of sources to process"),
    use_cache: bool = typer.Option(
        True, help="Use cached Wikipedia pages if available"
    ),
    dry_run: bool = typer.Option(
        True, help="Print updates without saving to Wikipedia"
    ),
    skip_to: str = typer.Option(None, help="Skip sources until this name is found"),
    wikitext_output_dir: Path = typer.Option(
        None,
        help="If set, write each formatted row to <dir>/<format>/<id>.mediawikitext",
    ),
    html_dir: Path = typer.Option(
        None,
        help="If set, render each row to HTML via the Wikipedia REST API and write to <dir>/<format>/<id>.html",
    ),
):
    run(
        limit=limit,
        use_cache=use_cache,
        dry_run=dry_run,
        skip_to=skip_to,
        wikitext_output_dir=wikitext_output_dir,
        html_dir=html_dir,
    )


if __name__ == "__main__":
    app()
