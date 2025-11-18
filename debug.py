import os
from parser import parse
from pprint import pprint

import mwclient
from jinja2 import Environment, FileSystemLoader, select_autoescape

from main import USER_AGENT

jinja = Environment(
    loader=FileSystemLoader("templates"),
    autoescape=select_autoescape(["html", "xml"]),
    block_start_string="@@",
    block_end_string="@@",
    variable_start_string="@=",
    variable_end_string="=@",
)


def main(page_format="format1", filter_fn=lambda: True):
    options = {
        "Authorization": f"Bearer {os.environ['WIKIPEDIA_ACCESS_TOKEN']}",
        "User-Agent": USER_AGENT,
    }
    site = mwclient.Site(
        "en.wikipedia.org",
        connection_options={"headers": options},
    )

    for data in parse(site, use_cache=True):
        if not filter_fn(data):
            continue
        pprint(data)
        template = jinja.get_template(page_format)
        print(template.render(data))


if __name__ == "__main__":
    main(filter_fn=lambda row: row.get("id") == "Bellingcat")
