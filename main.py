import os
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
    page["title"] = f"User:Audiodude/RSPTest/{page_format}/{data['name']}"
    template = jinja.get_template(page_format)
    page["update"] = template.render(data)
    return page


@app.command()
def main(
    limit: int = typer.Option(None, help="Maximum number of sources to process"),
    use_cache: bool = typer.Option(
        False, help="Use cached Wikipedia pages if available"
    ),
    dry_run: bool = typer.Option(
        False, help="Print updates without saving to Wikipedia"
    ),
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
            for page_format in FORMATS:
                page = create_subpage(jinja, page_format, data)
                format_to_sources[page_format].append(
                    {
                        "link": page["title"],
                        "name": data["name"],
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
                    wiki_page.save(
                        page["update"], summary=f"Test page for RSPS with {page_format}"
                    )
                except mwclient.errors.APIError as e:
                    if e.code == "spamblacklist":
                        data["url"] = data["domain"]
                        page = create_subpage(jinja, page_format, data)
                        wiki_page.save(
                            page["update"],
                            summary=f"Test page for RSPS with {page_format}",
                        )
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
            wiki_page.save(
                index_page, summary=f"Update index page for {page_format} pages"
            )
    except IncompleteParseError as e:
        print(f"Error during parsing:\n{e}\nPartial row follows:\n{e.alltext}")


if __name__ == "__main__":
    app()
