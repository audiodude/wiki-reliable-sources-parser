import re
from pathlib import Path

import mwparserfromhell


class IncompleteParseError(Exception):
    def __init__(self, message, alltext=""):
        super().__init__(message)
        self.alltext = alltext


RE_ID = re.compile(r'id="([^"]+)"')
RE_SORT_VALUE = re.compile(r'data-sort-value="([^"]+)"')
RE_PARENTHESIZED = re.compile(r"(\([^)]+?\))")


def get_page(site, title, use_cache=False):
    if use_cache:
        cache_dir = Path("cache")
        cache_dir.mkdir(exist_ok=True)
        cache_file = cache_dir / f"{title.replace('/', '_')}.txt"
        if cache_file.exists():
            with open(cache_file, "r", encoding="utf-8") as f:
                return mwparserfromhell.parse(f.read())

    page = site.pages[title]

    if use_cache:
        with open(cache_file, "w", encoding="utf-8") as f:
            f.write(page.text())
    return mwparserfromhell.parse(page.text())


def parse(site, use_cache=False):
    page_numbers = list(range(1, 10))

    data_dir = Path("data")
    data_dir.mkdir(exist_ok=True)

    for page_num in page_numbers:
        url = f"Wikipedia:Reliable_sources/Perennial_sources/{page_num}"
        wikicode = get_page(site, url, use_cache=use_cache)
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
                    # Yield the previous source
                    yield data

                data = {"alltext": item}
                cell_index = 0
                in_summary = False

                md = RE_ID.search(item)
                if not md:
                    raise IncompleteParseError(
                        f"Could not find id in row: {item}", alltext=data["alltext"]
                    )
                data["id"] = md.group(1)

                continue

            if item.startswith("|"):
                cell_index += 1
                data["alltext"] += "\n" + item
                in_summary = False
            item_wikicode = mwparserfromhell.parse(item)

            if in_summary:
                data["summary"] += " " + item_wikicode.strip()

            if cell_index == 1:
                smalls = item_wikicode.filter_tags(
                    matches=lambda node: node.tag == "small"
                )
                for small in smalls:
                    if "name qualifier" in data:
                        data["name_qualifier"] += (
                            " " + small.contents.strip_code().strip()
                        )
                    else:
                        data["name_qualifier"] = small.contents.strip_code().strip()
                    # Remove the small text, name qualifier like (Media Matters for America), so we
                    # can get parenthesized content qualifiers.
                    item_wikicode.remove(small)

                for tag in item_wikicode.filter_tags(
                    matches=lambda node: node.tag == "span"
                ):
                    # Remove "plainlink" span tags.
                    item_wikicode.remove(tag)

                links = item_wikicode.filter_wikilinks()
                if not links:
                    text = item_wikicode.filter_text()
                    if text:
                        while text:
                            name = text[0]
                            if RE_SORT_VALUE.search(str(name)):
                                text.pop(0)
                                continue
                            name = name.replace("| ", "").strip()
                            if name:
                                data["name"] = name
                                break
                            text.pop(0)
                else:
                    # Store a plain-text name (strip wikitext).
                    data["name"] = links[0].title.strip_code().strip()

                if not data.get("name"):
                    raise IncompleteParseError(
                        f"Could not find name in row: {item_wikicode}",
                        alltext=data["alltext"],
                    )
                # A qualifier, like "FooSite (movie reviews)".
                content_qualifier = " ".join(
                    RE_PARENTHESIZED.findall(item_wikicode.strip_code())
                ).strip()
                if content_qualifier:
                    data["content_qualifier"] = content_qualifier
                    data["qualified_name"] = f"{data['name']} {content_qualifier}"

                md = RE_SORT_VALUE.search(item)
                if md:
                    data["sort_name"] = md.group(1)
                else:
                    # If no explicit sort value, use the name.
                    data["sort_name"] = data["name"]
            elif cell_index == 3:
                # Store discussion as plain-text titles from wikilinks.
                rsn = [
                    str(l.title)
                    for l in item_wikicode.filter_wikilinks()
                    if l.text.isdigit()
                ]
                other = [
                    str(l.title)
                    for l in item_wikicode.filter_wikilinks()
                    if not l.text.isdigit()
                ]
                data["discussion"] = {"rsn": rsn}
                if other:
                    data["discussion"]["other"] = other
            elif cell_index == 5:
                # Store plaintext summary (remove leading '| ' and strip wikitext).
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

        # Yield the last source
        yield data


if __name__ == "__main__":
    for data in parse(None, use_cache=True):
        print(data)
