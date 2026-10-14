"""Builds the GitHub Pages site for a release from the files the release publishes.

    python scripts/make_site.py <dist dir> <site dir> <tag> <repository> <commit>

The site is the same at the same address whatever version of any repo reads it: every file of the release (the
contract and the code built from it), SHA256SUMS and latest.json (the version, each file's checksum and where the
release is) are always the latest release's."""

import hashlib
import html
import json
import sys
from pathlib import Path


def main(dist: Path, site: Path, tag: str, repository: str, commit: str) -> None:
    site.mkdir(parents=True, exist_ok=True)
    release_url = f"https://github.com/{repository}/releases/tag/{tag}"
    files = {}
    for path in sorted(dist.iterdir()):
        if path.is_file():
            (site / path.name).write_bytes(path.read_bytes())
            files[path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
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
        f'<li><a href="{html.escape(name)}">{html.escape(name)}</a> <code>{digest}</code></li>'
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
</ul>
</body>
</html>
"""
    )


if __name__ == "__main__":
    main(Path(sys.argv[1]), Path(sys.argv[2]), *sys.argv[3:6])
