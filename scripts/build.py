"""Builds the code generated from the contract by running openapi-codegen on openapi.yaml.

    uv run --frozen python scripts/build.py [openapi.yaml] [output dir]

Each archive holds a `countdown_api/` package for one side of the API:

    countdown_api-client.tar.gz   the Pydantic models and the `requests` client   (the renderer's side)
    countdown_api-server.tar.gz   the Pydantic models and the Flask views         (the broker's side)

Every part is also checked (openapi-codegen --check) and imported. The archives are byte-for-byte reproducible
(sorted, no timestamps or owners), so a checksum only changes when the code does."""

import gzip
import io
import subprocess
import sys
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
# archive name -> openapi-codegen's --only
SIDES = {"client": "clients", "server": "blueprints"}
PACKAGE = "countdown_api"


def generate(spec: Path, package: Path, only: str) -> None:
    command = [sys.executable, "-m", "openapi_codegen", str(spec), "--out", str(package), "--only", only]
    subprocess.run(command, check=True)
    subprocess.run([*command, "--check"], check=True)


def archive(package: Path, destination: Path) -> None:
    """A deterministic .tar.gz of the package directory, as countdown_api/..."""
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w", format=tarfile.PAX_FORMAT) as tar:
        for path in sorted([package, *package.rglob("*")]):
            if "__pycache__" in path.parts:
                continue
            info = tar.gettarinfo(str(path), arcname=f"{PACKAGE}/{path.relative_to(package)}".rstrip("/."))
            info.mtime, info.uid, info.gid, info.uname, info.gname = 0, 0, 0, "", ""
            info.mode = 0o755 if path.is_dir() else 0o644
            if path.is_file():
                with path.open("rb") as file:
                    tar.addfile(info, file)
            else:
                tar.addfile(info)
    with destination.open("wb") as file, gzip.GzipFile(filename="", mode="wb", fileobj=file, mtime=0) as zipped:
        zipped.write(buffer.getvalue())


def main(spec: Path, out: Path) -> None:
    for side, only in SIDES.items():
        package = out / "generated" / side / PACKAGE
        generate(spec, package, only)
        archive(package, out / f"{PACKAGE}-{side}.tar.gz")
        print(f"built {PACKAGE}-{side}.tar.gz ({only})")


if __name__ == "__main__":
    arguments = sys.argv[1:]
    main(Path(arguments[0] if arguments else ROOT / "openapi.yaml"), Path(arguments[1] if arguments[1:] else ROOT / "build"))
