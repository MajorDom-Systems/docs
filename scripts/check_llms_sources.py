#!/usr/bin/env python3
"""Weekly change-check for the integration llms endpoints.

Compares each source repo's current HEAD (GitHub API) against the SHA recorded in the *live*
site's ``/llms/manifest.json`` (published by the last deploy). If any repo has advanced — or the
manifest is missing — it triggers a docs redeploy via ``publish.yml``, which re-packs and
republishes. Nothing is cloned or committed here.

Needs the ``gh`` CLI with ``GH_TOKEN`` in the environment (both provided in GitHub Actions).
"""

from __future__ import annotations

import json
import subprocess
import urllib.request
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
SITE_MANIFEST_URL = "https://docs.majordom.io/llms/manifest.json"


def _head_sha(owner_repo: str, branch: str) -> str | None:
    result = subprocess.run(
        ["gh", "api", f"repos/{owner_repo}/commits/{branch}", "--jq", ".sha"],
        capture_output=True, text=True,
    )
    return result.stdout.strip() if result.returncode == 0 and result.stdout.strip() else None


def _live_manifest() -> dict:
    try:
        with urllib.request.urlopen(SITE_MANIFEST_URL, timeout=20) as response:
            return json.load(response)
    except Exception:
        return {}  # missing/unreachable -> treat everything as changed (forces a rebuild)


def main() -> None:
    sources = yaml.safe_load((ROOT / "llms_sources.yml").read_text()).get("integrations", [])
    manifest = _live_manifest()

    changed = []
    for entry in sources:
        name, url = entry["name"], entry["repo"]
        branch = entry.get("branch", "master")
        owner_repo = url.rstrip("/").removeprefix("https://github.com/")
        latest = _head_sha(owner_repo, branch)
        built = (manifest.get(name) or {}).get("commit")
        if latest and latest != built:
            changed.append(f"  {name}: {built or '(none)'} -> {latest}")

    if not changed:
        print("No source repos changed since the last deploy — nothing to do.")
        return

    print("Changed source repos:\n" + "\n".join(changed))
    # the released docs: without --ref it runs on the default branch, develop
    subprocess.run(["gh", "workflow", "run", "publish.yml", "--ref", "master"], check=True)
    print("Triggered publish.yml — the docs will be re-packed and redeployed.")


if __name__ == "__main__":
    main()
