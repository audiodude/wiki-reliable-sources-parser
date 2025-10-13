import json
import re
from pathlib import Path

import mwclient
import mwparserfromhell


class IncompleteParseError(Exception):
    pass


RE_ID = re.compile(r'id="([^"]+)"')
RE_PARENTHESIZED = re.compile(r"(\([^)]+?\))")


def get_cached_page(site, title):
    cache_dir = Path("cache")
    cache_dir.mkdir(exist_ok=True)
    cache_file = cache_dir / f"{title.replace('/', '_')}.txt"
    if cache_file.exists():
        with open(cache_file, "r", encoding="utf-8") as f:
            return mwparserfromhell.parse(f.read())
    page = site.pages[title]
    with open(cache_file, "w", encoding="utf-8") as f:
        f.write(page.text())
    return mwparserfromhell.parse(page.text())


USER_AGENT = "ReliableSourcesUpdaterBot/1.0 (User:Audiodude)"
page_numbers = list(range(1, 9))

data_dir = Path("data")
data_dir.mkdir(exist_ok=True)

sources = []

site = mwclient.Site("en.wikipedia.org", clients_useragent=USER_AGENT)
for page_num in page_numbers:
    url = f"Wikipedia:Reliable_sources/Perennial_sources/{page_num}"
    wikicode = get_cached_page(site, url)
    table = wikicode.filter_tags(matches=lambda node: node.tag == "table")[0]

    onlyinclude = table.contents.filter_tags(
        recursive=True, matches=lambda node: node.tag == "onlyinclude"
    )[0]
    items = onlyinclude.contents.split("\n")
    data = {}
    cell_index = 0
    in_summary = False
    for item in items:
        if not item:
            continue
        if "|-" in item:
            if data:
                # Store the previous source
                sources.append(data)

            data = {}
            cell_index = 0
            in_summary = False

            md = RE_ID.search(item)
            if not md:
                raise IncompleteParseError(f"Could not find id in row: {item}")
            data["id"] = md.group(1)
            continue

        if item.startswith("|"):
            cell_index += 1
            in_summary = False
        item_wikicode = mwparserfromhell.parse(item)

        if in_summary:
            data["summary"] += " " + item_wikicode.strip()

        if cell_index == 1:
            smalls = item_wikicode.filter_tags(matches=lambda node: node.tag == "small")
            for small in smalls:
                if "name qualifier" in data:
                    data["name_qualifier"] += " " + small.contents.strip_code().strip()
                else:
                    data["name_qualifier"] = small.contents.strip_code().strip()
                # Remove the small text, name qualifier like (Media Matters for America), so we
                # can get parenthesized content qualifiers.
                item_wikicode.remove(small)

            links = item_wikicode.filter_wikilinks()
            if not links:
                text = item_wikicode.filter_text()
                if not text:
                    raise IncompleteParseError(
                        f"Could not find name in row: {item_wikicode}"
                    )
                if text:
                    data["name"] = text[0].split("| ")[1]
            else:
                # store a plain-text name (strip wikitext)
                data["name"] = links[0].title.strip_code().strip()
            # A qualifier, like "FooSite (movie reviews)".
            content_qualifier = " ".join(
                RE_PARENTHESIZED.findall(item_wikicode.strip_code())
            ).strip()
            if content_qualifier:
                data["content_qualifier"] = content_qualifier
        elif cell_index == 3:
            # store discussion as plain-text titles from wikilinks
            data["discussion"] = " ".join(
                str(l) for l in item_wikicode.filter_wikilinks()
            )
        elif cell_index == 5:
            # store plaintext summary (remove leading '| ' and strip wikitext)
            data["summary"] = item_wikicode.lstrip("| ").strip()
            in_summary = True

        templates = item_wikicode.filter_templates()
        if templates:
            for template in templates:
                if template.name == "WP:RSPSTATUS":
                    data["status"] = str(template.params[0])
                elif template.name == "WP:RSPLAST":
                    data["rsp_last"] = str(template.params[0])
                elif template.name == "WP:RSPSHORTCUT":
                    data["shortcut"] = str(template.params[0])
                elif template.name == "WP:RSPUSES":
                    data["domain"] = str(template.params[0])
                elif template.name == "rsnl":
                    entry = {}
                    entry["notice_id"] = str(template.params[0])
                    entry["notice_title"] = str(template.params[1])
                    entry["notice_year"] = str(template.params[2])
                    entry["rfc"] = template.has("rfc") and template.get(
                        "rfc"
                    ).value.lower().startswith("y")
                    data.setdefault("rsnl", []).append(entry)

    # Store the last source
    sources.append(data)

    with open(data_dir / f"page_{page_num}.json", "w", encoding="utf-8") as f:
        json.dump(sources, f, indent=2, ensure_ascii=False)
