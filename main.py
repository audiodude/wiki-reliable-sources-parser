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
        "User-Agent": "Audiodude RSP Migration [1.0] (User:Audiodude) via mwclient",
    }
    site = mwclient.Site(
        "en.wikipedia.org",  # Or the specific wiki you are targeting
        connection_options={"headers": options},
    )
    links = []
    try:
        for data in parse(site, use_cache=use_cache):
            for page_format in ("format1", "format2"):
                page = create_subpage(jinja, page_format, data)
                links.append(page["title"])

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

        template = jinja.get_template("index1")
        index_page = template.render(links=links)
        wiki_page = site.pages[f"User:Audiodude/RSPTest/{page_format}/Index"]
        wiki_page.save(index_page, summary=f"Update index page for {page_format} pages")
    except IncompleteParseError as e:
        print(f"Error during parsing:\n{e}\nPartial row follows:\n{e.alltext}")


if __name__ == "__main__":
    app()
