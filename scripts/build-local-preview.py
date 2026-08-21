from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import re
import sqlite3
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from types import ModuleType
from typing import Any


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DATABASE_PATH = ROOT / "data" / "data-lab.db"
DEFAULT_OUTPUT_PATH = Path(tempfile.gettempdir()) / "data-lab-local-preview-v0.1"
PREVIEW_SOURCE = ROOT / "preview"
PREVIEW_FILES = ("index.html", "item.html", "preview.css", "preview.js")
EXPECTED_PUBLIC_SCHEMA_VERSION = "0.1"
EXPECTED_PUBLIC_POLICY_VERSION = "0.1"
EXPECTED_PUBLICATION_STATUS = "local_validation_only"


class PreviewBuildError(Exception):
    pass


class SafeArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        self.print_usage(sys.stderr)
        print("local preview build failed: INVALID_ARGUMENT", file=sys.stderr)
        raise SystemExit(2)


def load_public_builder() -> ModuleType:
    path = ROOT / "scripts" / "build-public-data.py"
    specification = importlib.util.spec_from_file_location("data_lab_public", path)
    if specification is None or specification.loader is None:
        raise PreviewBuildError("PUBLIC_BUILDER_LOAD_FAILED")
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


def timestamp_argument(name: str):
    def parser(value: str) -> datetime:
        normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
        try:
            result = datetime.fromisoformat(normalized)
        except ValueError as error:
            raise argparse.ArgumentTypeError(f"{name} must be ISO8601") from error
        if result.tzinfo is None:
            raise argparse.ArgumentTypeError(f"{name} must include a UTC offset")
        return result.astimezone(timezone.utc)

    return parser


def preview_source_files() -> dict[str, bytes]:
    files: dict[str, bytes] = {}
    for filename in PREVIEW_FILES:
        path = PREVIEW_SOURCE / filename
        if not path.is_file():
            raise PreviewBuildError("PREVIEW_SOURCE_MISSING")
        files[filename] = path.read_bytes()
    return files


def validate_preview_source(files: dict[str, bytes]) -> None:
    if set(files) != set(PREVIEW_FILES):
        raise PreviewBuildError("PREVIEW_SOURCE_SET_MISMATCH")
    combined = b"\n".join(files.values()).decode("utf-8")
    forbidden_patterns = {
        "SCRIPT_INJECTION_API": r"\b(?:eval|Function)\s*\(",
        "UNSAFE_HTML_ASSIGNMENT": r"\.innerHTML\s*=",
        "EXTERNAL_SCRIPT": r"<script[^>]+src=[\"']https?://",
        "EXTERNAL_STYLESHEET": r"<link[^>]+href=[\"']https?://",
        "SECRET_PARAMETER": r"(?:api|affiliate)[_-]?id\s*=",
        "ENV_REFERENCE": r"\.env\b",
        "AFFILIATE_FIELD": r"affiliateURL",
        "SQLITE_PATH": r"[a-z]:[\\/][^\r\n\"']*\.(?:db|sqlite3?)",
    }
    for code, pattern in forbidden_patterns.items():
        if re.search(pattern, combined, re.IGNORECASE):
            raise PreviewBuildError(f"PREVIEW_SOURCE_{code}")
    if "loading = \"lazy\"" not in combined:
        raise PreviewBuildError("PREVIEW_LAZY_IMAGE_MISSING")
    if "noopener noreferrer" not in combined:
        raise PreviewBuildError("PREVIEW_EXTERNAL_LINK_REL_MISSING")


def validate_staging(files: dict[str, bytes], public_module: ModuleType) -> dict[str, Any]:
    required = {"index.html", "item.html", "preview.css", "preview.js", "public-data/manifest.json", "public-data/index.json"}
    if not required <= set(files):
        raise PreviewBuildError("STAGING_REQUIRED_FILE_MISSING")
    try:
        manifest = json.loads(files["public-data/manifest.json"])
        index = json.loads(files["public-data/index.json"])
    except json.JSONDecodeError as error:
        raise PreviewBuildError("STAGING_JSON_INVALID") from error
    if manifest.get("public_schema_version") != EXPECTED_PUBLIC_SCHEMA_VERSION:
        raise PreviewBuildError("STAGING_SCHEMA_VERSION_MISMATCH")
    if manifest.get("public_policy_version") != EXPECTED_PUBLIC_POLICY_VERSION:
        raise PreviewBuildError("STAGING_POLICY_VERSION_MISMATCH")
    if manifest.get("publication_status") != EXPECTED_PUBLICATION_STATUS:
        raise PreviewBuildError("STAGING_PUBLICATION_STATUS_INVALID")
    items = index.get("items")
    if not isinstance(items, list) or len(items) != manifest.get("item_count"):
        raise PreviewBuildError("STAGING_ITEM_COUNT_MISMATCH")
    identifiers = [item.get("public_id") for item in items]
    if len(identifiers) != len(set(identifiers)):
        raise PreviewBuildError("STAGING_DUPLICATE_PUBLIC_ID")
    expected_details = {f"public-data/{public_module.detail_relative_path(identifier)}" for identifier in identifiers}
    actual_details = {path for path in files if path.startswith("public-data/items/")}
    if expected_details != actual_details:
        raise PreviewBuildError("STAGING_DETAIL_SET_MISMATCH")
    for path in actual_details:
        try:
            detail = json.loads(files[path])
        except json.JSONDecodeError as error:
            raise PreviewBuildError("STAGING_DETAIL_JSON_INVALID") from error
        if detail.get("item", {}).get("public_id") not in set(identifiers):
            raise PreviewBuildError("STAGING_ORPHAN_DETAIL")
    public_module.safety_scan(
        {path.removeprefix("public-data/"): content for path, content in files.items() if path.startswith("public-data/")}
    )
    return {
        "item_count": len(items),
        "json_file_count": len(actual_details) + 2,
        "duplicate_public_id_count": 0,
        "missing_detail_count": 0,
        "orphan_detail_count": 0,
        "public_schema_version": manifest["public_schema_version"],
        "public_policy_version": manifest["public_policy_version"],
        "publication_status": manifest["publication_status"],
        "rights_review_required": manifest["rights_review_required"],
    }


def build_preview(database_path: Path, as_of: datetime, generated_at: datetime) -> tuple[dict[str, bytes], dict[str, Any]]:
    public_module = load_public_builder()
    try:
        public_files, public_summary = public_module.build_documents(
            database_path, as_of, generated_at
        )
    except public_module.PublicDataError as error:
        raise PreviewBuildError(str(error)) from error
    sources = preview_source_files()
    validate_preview_source(sources)
    files = dict(sources)
    files.update({f"public-data/{path}": content for path, content in public_files.items()})
    staging = validate_staging(files, public_module)
    staging.update(
        {
            "validation_failures": 0,
            "secret_scan_failures": 0,
            "preview_source_files": len(sources),
            "staging_file_count": len(files),
            "total_bytes": sum(len(content) for content in files.values()),
            "public_data_bytes": public_summary["sizes"]["total_bytes"],
            "staging_digest": hashlib.sha256(
                b"".join(path.encode("utf-8") + b"\0" + files[path] for path in sorted(files))
            ).hexdigest(),
        }
    )
    return files, staging


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = SafeArgumentParser(description="Build a local-only DATA LAB UI preview staging directory.")
    parser.add_argument("--db", type=Path, default=DEFAULT_DATABASE_PATH)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH)
    parser.add_argument("--as-of", type=timestamp_argument("--as-of"))
    parser.add_argument("--generated-at", type=timestamp_argument("--generated-at"))
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--json", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    args = parse_args(argv)
    now = datetime.now(timezone.utc)
    try:
        files, summary = build_preview(args.db, args.as_of or now, args.generated_at or now)
        public_module = load_public_builder()
        if not args.dry_run:
            try:
                public_module.atomic_write(args.output, files)
            except public_module.PublicDataError as error:
                raise PreviewBuildError(str(error)) from error
    except PreviewBuildError as error:
        if args.json:
            print(json.dumps({"preview_version": "0.1", "error": str(error)}, ensure_ascii=False))
        else:
            print(f"local preview build failed: {error}", file=sys.stderr)
        return 2
    except (OSError, sqlite3.Error):
        if args.json:
            print(json.dumps({"preview_version": "0.1", "error": "LOCAL_IO_OR_DATABASE_ERROR"}))
        else:
            print("local preview build failed: LOCAL_IO_OR_DATABASE_ERROR", file=sys.stderr)
        return 2
    except Exception:
        if args.json:
            print(json.dumps({"preview_version": "0.1", "error": "UNEXPECTED_ERROR"}))
        else:
            print("local preview build failed: UNEXPECTED_ERROR", file=sys.stderr)
        return 3
    summary["mode"] = "dry-run" if args.dry_run else "generated"
    summary["output_written"] = not args.dry_run
    if args.json:
        print(json.dumps(summary, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
    else:
        print("LOCAL WEB UI PREVIEW v0.1")
        print(f"Mode: {summary['mode']}")
        print(f"Items: {summary['item_count']}")
        print(f"Files: {summary['staging_file_count']}")
        if not args.dry_run:
            output = args.output.resolve()
            print(f"Staging: {output}")
            print(f'Run: python -m http.server 8000 --bind 127.0.0.1 --directory "{output}"')
            print("Open: http://127.0.0.1:8000/index.html")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
