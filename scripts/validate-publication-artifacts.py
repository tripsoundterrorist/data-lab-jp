"""Read-only CLI for validating an artifact directory under the OS temp root."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import tempfile

from publication_artifact_validator import validate_artifacts


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("directory", type=Path)
    args = parser.parse_args(argv)
    try:
        root = args.directory.resolve(strict=True)
        temp_root = Path(tempfile.gettempdir()).resolve(strict=True)
        root.relative_to(temp_root)
        if not root.is_dir() or root.is_symlink():
            raise ValueError
        files = {
            path.relative_to(root).as_posix(): path.read_bytes()
            for path in root.rglob("*.json")
            if path.is_file() and not path.is_symlink()
        }
        result = validate_artifacts(files)
    except Exception:
        result = validate_artifacts(None)
    print(json.dumps(result.to_dict(), sort_keys=True))
    return 0 if result.artifact_validation == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
