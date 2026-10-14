"""Imports the named parts of a generated countdown_api package that sits in the given directory.

    python -I scripts/check_imports.py <dir> models,clients

-I ignores the current directory, so the package is put on the path here."""

import importlib
import sys

directory, parts = sys.argv[1], sys.argv[2].split(",")
sys.path.insert(0, directory)
for part in parts:
    importlib.import_module(f"countdown_api.{part}")
    print(f"imported countdown_api.{part}")
