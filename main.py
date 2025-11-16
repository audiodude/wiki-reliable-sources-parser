import mwclient
from jinja2 import Environment, PackageLoader, select_autoescape

from parser import parse

jinja = Environment(
    loader=PackageLoader("templates"), autoescape=select_autoescape(["html", "xml"])
)

USER_AGENT = "ReliableSourcesUpdaterBot/1.0 (User:Audiodude)"


def create_subpage(jinja, format, data):
    page = {}
    page["title"] = f"User:Audiodude/RSPTest/{format}/{data['name']}"
    template = jinja.get_template(format)
    page["update"] = template.render(data)
    return page


def main(limit, use_cache, dry_run):
    site = mwclient.Site("en.wikipedia.org", clients_useragent=USER_AGENT)
    for page_format in ("format1", "format2"):
        for data in parse(site, use_cache=use_cache):
            page = create_subpage(jinja, page_format, data)
            limit -= 1
            if limit == 0:
                break
            if dry_run:
                print(f"--- {page['title']} ---")
                print(page["update"])
                print()
                continue
            site.save_page(
                page["title"], page["update"], f"Test page for RSPS with {format}'"
            )


if __name__ == "__main__":
    main(limit=10, use_cache=True, dry_run=True)
