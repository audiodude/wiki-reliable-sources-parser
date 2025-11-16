import os

import mwclient
import requests
from dotenv import load_dotenv
from jinja2 import Environment, FileSystemLoader, select_autoescape

from parser import parse

load_dotenv()

jinja = Environment(
    loader=FileSystemLoader("templates"), autoescape=select_autoescape(["html", "xml"])
)

USER_AGENT = "ReliableSourcesUpdaterBot/1.0 (User:Audiodude)"


def create_subpage(jinja, format, data):
    page = {}
    page["title"] = f"User:Audiodude/RSPTest/{format}/{data['name']}"
    template = jinja.get_template(format)
    page["update"] = template.render(data)
    return page


def main(limit, use_cache, dry_run):
    options = {
        "Authorization": f"Bearer {os.environ['WIKIPEDIA_ACCESS_TOKEN']}",
        "User-Agent": "Audiodude RSP Migration [1.0] (User:Audiodude) via mwclient",
    }
    site = mwclient.Site(
        "en.wikipedia.org",  # Or the specific wiki you are targeting
        connection_options={"headers": options},
    )
    for data in parse(site, use_cache=use_cache):
        for page_format in ("format1", "format2"):
            page = create_subpage(jinja, page_format, data)

            if dry_run:
                print(f"--- {page['title']} ---")
                print(page["update"])
                print()
                continue
            wiki_page = site.pages[page["title"]]
            print(f"Updating {page['title']}")
            wiki_page.save(
                page["update"], summary=f"Test page for RSPS with {page_format}"
            )
        limit -= 1
        if limit == 0:
            return


if __name__ == "__main__":
    main(limit=1, use_cache=True, dry_run=True)
