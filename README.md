= Auto-convert RSP table to subpages

https://en.wikipedia.org/wiki/Wikipedia:Requests_for_comment/Restructuring_RSP

https://phabricator.wikimedia.org/tag/english-wikipedia-rsp-restructuring/

To generate and overwrite just the sources.jsonl data, run:

```bash
uv install
uv run python parser.py > data/sources.jsonl
```

The other "pages" should be considered historical.