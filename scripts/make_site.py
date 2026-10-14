"""Builds the GitHub Pages site for a release from the files the release publishes.

    python scripts/make_site.py <dist dir> <site dir> <tag> <repository> <commit> [<releases json>]

The site is the same at the same address whatever version of any repo reads it, and always the latest release's:
every file of it, SHA256SUMS and latest.json (the version, each file's checksum and where the release is). The
release workflow adds constraints.txt, which pins only countdown-api, for `uv sync --constraints URL` or
`UV_CONSTRAINT=URL` (the dependency stays ranged in pyproject.toml).

It is also a flat package index (https://docs.astral.sh/uv/concepts/indexes/#flat-indexes): the page links to the
wheel, with its hash, so `[[tool.uv.index]] url = "https://nvorkinn.github.io/countdown-api/" format = "flat"` lets a
project depend on countdown-api and find the latest version here. The wheel is linked at its address on the release,
not on this site, because that address stays valid after the next release replaces the site, and a lockfile records
it.

It is also a simple (PEP 503) index, under simple/, which lists every release's wheel, not just the latest: the
optional <releases json> is a list of {"name", "url", "sha256"} for the wheels of all releases (the workflow reads it
from GitHub), and the wheel built here is always added. With constraints.txt pinning one version, a project that
lists countdown-api without a version gets exactly that one, and can still ask for an older one."""

from __future__ import annotations

import hashlib
import html
import json
import sys
from pathlib import Path


def link(name: str, digest: str, repository: str, tag: str) -> str:
    """Where a file is linked from the page: a wheel at its permanent address on the release, with its hash (what a
    flat index needs); anything else beside the page."""
    if name.endswith(".whl"):
        return f"https://github.com/{repository}/releases/download/{tag}/{name}#sha256={digest}"
    return name


def simple_index(site: Path, wheels: list[dict]) -> None:
    """simple/index.html lists the project; simple/countdown-api/index.html links each wheel, at its address on its
    release, with its hash when it has one (https://peps.python.org/pep-0503/)."""
    root = site / "simple"
    project = root / "countdown-api"
    project.mkdir(parents=True, exist_ok=True)
    (root / "index.html").write_text(
        '<!doctype html>\n<html><body>\n<a href="countdown-api/">countdown-api</a>\n</body></html>\n'
    )
    links = "\n".join(
        f'<a href="{html.escape(w["url"] + ("#sha256=" + w["sha256"] if w.get("sha256") else ""))}">{html.escape(w["name"])}</a><br>'
        for w in sorted(wheels, key=lambda w: w["name"])
    )
    (project / "index.html").write_text(f"<!doctype html>\n<html><body>\n{links}\n</body></html>\n")


def main(dist: Path, site: Path, tag: str, repository: str, commit: str, releases: Path | None = None) -> None:
    site.mkdir(parents=True, exist_ok=True)
    release_url = f"https://github.com/{repository}/releases/tag/{tag}"
    files = {}
    for path in sorted(dist.iterdir()):
        if path.is_file():
            (site / path.name).write_bytes(path.read_bytes())
            files[path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
    wheels = {w["name"]: w for w in json.loads(releases.read_text())} if releases else {}
    for name, digest in files.items():
        if name.endswith(".whl"):
            wheels[name] = {"name": name, "url": link(name, digest, repository, tag).split("#")[0], "sha256": digest}
    simple_index(site, list(wheels.values()))
    latest = {"version": tag.removeprefix("v"), "tag": tag, "commit": commit, "release": release_url, "files": files}
    (site / "latest.json").write_text(json.dumps(latest, indent=2) + "\n")

    rows = "".join(
        f"<tr><th>{html.escape(name)}</th><td>{value}</td></tr>"
        for name, value in [
            ("Version", f"<strong>{html.escape(tag)}</strong>"),
            ("Release", f'<a href="{html.escape(release_url)}">{html.escape(release_url)}</a>'),
        ]
    )
    listing = "\n".join(
        f'<li><a href="{html.escape(link(name, digest, repository, tag))}">{html.escape(name)}</a> <code>{digest}</code></li>'
        for name, digest in files.items()
    )
    (site / "index.html").write_text(
        f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>countdown API</title>
<style>body{{font:16px/1.5 system-ui,sans-serif;max-width:46rem;margin:2rem auto;padding:0 1rem}}
th{{text-align:left;padding-right:1rem}}code{{word-break:break-all}}</style>
</head>
<body>
<h1>countdown API</h1>
<p>The contract between the countdown renderer and the auth-broker. Both generate their side from the file below on every build.</p>
<table>{rows}</table>
<ul>
{listing}
<li><a href="latest.json">latest.json</a></li>
<li><a href="constraints.txt">constraints.txt</a> (pins countdown-api, for <code>uv sync --constraints</code> / <code>UV_CONSTRAINT</code>)</li>
</ul>
</body>
</html>
"""
    )


if __name__ == "__main__":
    main(Path(sys.argv[1]), Path(sys.argv[2]), *sys.argv[3:6], *(Path(a) for a in sys.argv[6:7]))
