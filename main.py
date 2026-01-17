import os
import time
from parser import IncompleteParseError, parse

import mwclient
import typer
from dotenv import load_dotenv
from jinja2 import Environment, FileSystemLoader, select_autoescape

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

USER_AGENT = "ReliableSourcesUpdaterBot/1.0 (User:Audiodude)"
FORMATS = ("format1", "format2")


def create_subpage(jinja, page_format, data):
    page = {}
    page["title"] = (
        f"User:Audiodude/RSPTest/{page_format}/{data.get('qualified_name', data.get('name'))}"
    )
    template = jinja.get_template(page_format)
    page["update"] = template.render(data)
    return page


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


@app.command()
def main(
    limit: int = typer.Option(None, help="Maximum number of sources to process"),
    use_cache: bool = typer.Option(
        False, help="Use cached Wikipedia pages if available"
    ),
    dry_run: bool = typer.Option(
        False, help="Print updates without saving to Wikipedia"
    ),
    skip_to: str = typer.Option(None, help="Skip sources until this name is found"),
):
    options = {
        "Authorization": f"Bearer {os.environ['WIKIPEDIA_ACCESS_TOKEN']}",
        "User-Agent": USER_AGENT,
    }
    site = mwclient.Site(
        "en.wikipedia.org",
        connection_options={"headers": options},
    )
    format_to_sources = {fmt: [] for fmt in FORMATS}
    try:
        for data in parse(site, use_cache=use_cache):
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

                # Only print title and skip saving page to wiki if dry-run is enabled
                if dry_run:
                    print(f"--- {page['title']} ---")
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


if __name__ == "__main__":
    app()
