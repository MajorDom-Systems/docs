"""MkDocs hook: fold the example-integration full-source dumps into the LLM index.

``mkdocs-llmstxt`` builds ``llms.txt`` (index of doc pages) and ``llms-full.txt`` from the docs.
This hook runs after that and, for each source in ``llms_sources.yml`` that has a generated
``docs/llms/<name>.txt`` (produced by ``scripts/build_llms.py`` and copied to ``site/llms/`` by
MkDocs), it:

- appends an "Example Integrations (full source)" section to ``llms.txt`` linking the unindexed
  ``/llms/<name>.txt`` endpoints, and
- appends each full dump to ``llms-full.txt``.

It also links the Hub OpenAPI spec (``hub/hub-openapi-v1.json``, synced from the Hub by a workflow) from
``llms.txt`` and appends it to ``llms-full.txt`` rendered as markdown.

The dumps are served as raw ``.txt`` (not in the nav, not HTML), so they stay out of the site's
search index and are reachable only via ``llms.txt``.
"""

from __future__ import annotations

import json
from pathlib import Path

import yaml

from majordom_docs.openapi_md import render

SITE_URL = "https://docs.majordom.io"
HUB_OPENAPI = "hub/hub-openapi-v1.json"


def on_post_build(config, **kwargs) -> None:
    site_dir = Path(config["site_dir"])
    _append_hub_openapi(site_dir)
    sources_file = Path(config["config_file_path"]).parent / "llms_sources.yml"
    if not sources_file.exists():
        return

    sources = yaml.safe_load(sources_file.read_text()).get("integrations", [])

    links: list[str] = []
    packs: list[Path] = []
    for entry in sources:
        name = entry["name"]
        title = entry.get("title", name)
        pack = site_dir / "llms" / f"{name}.txt"
        if not pack.exists():  # not generated yet (e.g. local build without scripts/build_llms.py)
            continue
        links.append(f"- [{title} — full source]({SITE_URL}/llms/{name}.txt)")
        packs.append(pack)

    if not links:
        return

    llms = site_dir / "llms.txt"
    if llms.exists():
        with llms.open("a", encoding="utf-8") as f:
            f.write("\n## Example Integrations (full source)\n\n")
            f.write("Complete source of each example integration — load one to write your own:\n\n")
            f.write("\n".join(links) + "\n")

    llms_full = site_dir / "llms-full.txt"
    if llms_full.exists():
        with llms_full.open("a", encoding="utf-8") as f:
            for pack in packs:
                f.write("\n\n")
                f.write(pack.read_text(encoding="utf-8"))


def _append_hub_openapi(site_dir: Path) -> None:
    spec_file = site_dir / HUB_OPENAPI
    if not spec_file.exists():
        return

    llms = site_dir / "llms.txt"
    if llms.exists():
        with llms.open("a", encoding="utf-8") as f:
            f.write("\n## Hub API (OpenAPI)\n\n")
            f.write(f"- [Hub REST API OpenAPI spec (JSON)]({SITE_URL}/{HUB_OPENAPI})\n")

    llms_full = site_dir / "llms-full.txt"
    if llms_full.exists():
        with llms_full.open("a", encoding="utf-8") as f:
            f.write("\n\n")
            f.write(render(json.loads(spec_file.read_text(encoding="utf-8")), "Hub REST API (OpenAPI)"))
