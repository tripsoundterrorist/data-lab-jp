from __future__ import annotations

import argparse
import hashlib
import os
import re
import shutil
import sys
import tempfile
import uuid
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent
ALLOWLIST = (
    "_headers",
    "404.html",
    "about.html",
    "analytics-consent.css",
    "analytics-consent.js",
    "index.html",
    "column-price.html",
    "column-trend.html",
    "column-score.html",
    "contact.html",
    "disclosure.html",
    "legal.css",
    "privacy.html",
    "robots.txt",
    "sitemap.xml",
    "terms.html",
    "items/index.html",
    "items/item.html",
    "items/items.css",
    "items/discovery.js",
    "items/items.js",
)
FORBIDDEN_FILENAMES = frozenset(
    {
        ".env",
        ".gitignore",
        "agents.md",
        "readme.md",
        "schema.sql",
    }
)
FORBIDDEN_EXTENSIONS = frozenset(
    {".db", ".sqlite", ".sqlite3", ".py", ".ps1", ".sql"}
)
FORBIDDEN_PATH_PARTS = frozenset(
    {
        ".git",
        "backup",
        "backups",
        "credentials",
        "db",
        "logs",
        "preview",
        "public-data",
        "scripts",
    }
)
FORBIDDEN_CONTENT_PATTERNS = {
    "SECRET_ASSIGNMENT": re.compile(
        r"(?i)(?:api[_-]?id|affiliate[_-]?id|access[_-]?token|credentials?"
        r"|password|secret)\s*[:=]"
    ),
    "QUERY_CONTEXT": re.compile(r"(?i)query_context"),
    "RAW_API_RESPONSE": re.compile(r"(?i)raw[_ -]?api[_ -]?response"),
}


class SourceError(Exception):
    pass


class UnsafeOutputError(Exception):
    pass


class ValidationError(Exception):
    pass


class BuildInternalError(Exception):
    pass


class SafeArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        self.print_usage(sys.stderr)
        print("static site build failed: INVALID_ARGUMENT", file=sys.stderr)
        raise SystemExit(2)


def resolve_repo_root(value: Path) -> Path:
    try:
        root = value.resolve(strict=True)
    except OSError as error:
        raise SourceError("REPOSITORY_ROOT_UNAVAILABLE") from error
    if not root.is_dir():
        raise SourceError("REPOSITORY_ROOT_NOT_DIRECTORY")
    return root


def resolve_output(repo_root: Path, value: Path | None) -> Path:
    lexical_dist_root = repo_root / "dist"
    if lexical_dist_root.is_symlink():
        raise UnsafeOutputError("DIST_SYMLINK_FORBIDDEN")
    requested = value if value is not None else lexical_dist_root
    if not requested.is_absolute():
        requested = repo_root / requested
    output = requested.resolve()
    dist_root = (repo_root / "dist").resolve()
    if output != dist_root and dist_root not in output.parents:
        raise UnsafeOutputError("OUTPUT_OUTSIDE_DIST")
    if output.parent == output:
        raise UnsafeOutputError("OUTPUT_IS_FILESYSTEM_ROOT")
    return output


def validate_relative_name(name: str) -> None:
    relative = Path(name)
    if (
        relative.is_absolute()
        or not relative.parts
        or "." in relative.parts
        or ".." in relative.parts
    ):
        raise ValidationError("ALLOWLIST_PATH_UNSAFE")
    lowered = relative.name.casefold()
    if lowered in FORBIDDEN_FILENAMES or lowered.startswith(".env."):
        raise ValidationError("FORBIDDEN_FILENAME")
    if relative.suffix.casefold() in FORBIDDEN_EXTENSIONS:
        raise ValidationError("FORBIDDEN_EXTENSION")
    if any(part.casefold() in FORBIDDEN_PATH_PARTS for part in relative.parts):
        raise ValidationError("FORBIDDEN_PATH")


def read_known_secret_values(repo_root: Path) -> tuple[bytes, ...]:
    values: set[bytes] = set()
    env_path = repo_root / ".env"
    if env_path.is_symlink():
        raise ValidationError("SECRET_SOURCE_SYMLINK_FORBIDDEN")
    if env_path.is_file():
        try:
            lines = env_path.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeError) as error:
            raise ValidationError("SECRET_SOURCE_READ_FAILED") from error
        for line in lines:
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            _, raw_value = stripped.split("=", 1)
            value = raw_value.strip().strip("\"'")
            if len(value) >= 6:
                values.add(value.encode("utf-8"))
    secret_name = re.compile(
        r"(?i)(?:api[_-]?id|affiliate[_-]?id|credential|token|password|secret)"
    )
    for name, value in os.environ.items():
        if secret_name.search(name) and len(value) >= 6:
            values.add(value.encode("utf-8"))
    return tuple(sorted(values))


def collect_sources(repo_root: Path) -> dict[str, bytes]:
    if not ALLOWLIST or len(ALLOWLIST) != len(set(ALLOWLIST)):
        raise ValidationError("ALLOWLIST_INVALID")
    files: dict[str, bytes] = {}
    for name in ALLOWLIST:
        validate_relative_name(name)
        source = repo_root / name
        source_parts = [
            repo_root.joinpath(*Path(name).parts[:index])
            for index in range(1, len(Path(name).parts) + 1)
        ]
        if any(part.is_symlink() for part in source_parts):
            raise SourceError("SOURCE_SYMLINK_FORBIDDEN")
        try:
            resolved = source.resolve(strict=True)
        except OSError as error:
            raise SourceError("ALLOWLIST_SOURCE_MISSING") from error
        if repo_root not in resolved.parents or not resolved.is_file():
            raise SourceError("ALLOWLIST_SOURCE_OUTSIDE_ROOT")
        try:
            files[name] = resolved.read_bytes()
        except OSError as error:
            raise SourceError("ALLOWLIST_SOURCE_READ_FAILED") from error
    return files


def validate_files(files: dict[str, bytes], secrets: tuple[bytes, ...], *, coupon_review: bool = False, coupon_public: bool = False, books_device: bool = False) -> None:
    expected = set(ALLOWLIST) | ({"coupon-help.html"} if coupon_review or coupon_public else set()) | ({"books-device-check.html"} if books_device else set())
    if set(files) != expected:
        raise ValidationError("OUTPUT_SET_MISMATCH")
    for name, content in files.items():
        validate_relative_name(name)
        try:
            text = content.decode("utf-8")
        except UnicodeError as error:
            raise ValidationError("OUTPUT_NOT_UTF8") from error
        for pattern in FORBIDDEN_CONTENT_PATTERNS.values():
            if pattern.search(text):
                raise ValidationError("FORBIDDEN_CONTENT_PATTERN")
        if any(secret in content for secret in secrets):
            raise ValidationError("KNOWN_SECRET_VALUE_FOUND")


def validate_staging(staging: Path, files: dict[str, bytes], *, coupon_review: bool = False, coupon_public: bool = False, books_device: bool = False) -> None:
    found: dict[str, Path] = {}
    try:
        entries = list(staging.rglob("*"))
    except OSError as error:
        raise ValidationError("STAGING_READ_FAILED") from error
    for entry in entries:
        if entry.is_symlink():
            raise ValidationError("STAGING_SYMLINK_FORBIDDEN")
        relative = entry.relative_to(staging).as_posix()
        if entry.is_dir():
            if relative != "items":
                raise ValidationError("STAGING_UNEXPECTED_DIRECTORY")
            continue
        if not entry.is_file():
            raise ValidationError("STAGING_NON_FILE_FOUND")
        validate_relative_name(relative)
        found[relative] = entry
    expected = set(ALLOWLIST) | ({"coupon-help.html"} if coupon_review or coupon_public else set()) | ({"books-device-check.html"} if books_device else set())
    if set(found) != expected:
        raise ValidationError("STAGING_SET_MISMATCH")
    for name, expected in files.items():
        try:
            actual = found[name].read_bytes()
        except OSError as error:
            raise ValidationError("STAGING_FILE_READ_FAILED") from error
        if actual != expected:
            raise ValidationError("STAGING_CONTENT_MISMATCH")


def atomic_publish(output: Path, files: dict[str, bytes], *, coupon_review: bool = False, coupon_public: bool = False, books_device: bool = False) -> None:
    if output.is_symlink() or (output.exists() and not output.is_dir()):
        raise UnsafeOutputError("OUTPUT_NOT_SAFE_DIRECTORY")
    parent = output.parent
    try:
        parent.mkdir(parents=True, exist_ok=True)
        staging = Path(tempfile.mkdtemp(prefix=f".{output.name}.tmp-", dir=parent))
    except OSError as error:
        raise BuildInternalError("STAGING_CREATE_FAILED") from error
    previous: Path | None = None
    try:
        for name, content in files.items():
            destination = staging / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(content)
        validate_staging(staging, files, coupon_review=coupon_review, coupon_public=coupon_public, books_device=books_device)
        if output.exists():
            previous = output.with_name(f".{output.name}.previous-{uuid.uuid4().hex}")
            os.replace(output, previous)
        os.replace(staging, output)
        if previous is not None:
            shutil.rmtree(previous, ignore_errors=True)
    except Exception:
        if staging.exists():
            shutil.rmtree(staging, ignore_errors=True)
        if previous is not None and previous.exists() and not output.exists():
            try:
                os.replace(previous, output)
            except OSError as restore_error:
                raise BuildInternalError("OUTPUT_RESTORE_FAILED") from restore_error
        raise


def build_summary(
    repo_root: Path, output: Path, files: dict[str, bytes], dry_run: bool
) -> dict[str, Any]:
    return {
        "mode": "dry-run" if dry_run else "generated",
        "source": str(repo_root),
        "output": str(output),
        "files": list(files),
        "file_count": len(files),
        "sha256": {
            name: hashlib.sha256(content).hexdigest() for name, content in files.items()
        },
        "validation": "passed",
        "status": "ok",
    }


def print_summary(summary: dict[str, Any]) -> None:
    print("STATIC SITE STAGING v0.1")
    print(f"Mode: {summary['mode']}")
    if summary.get("local_review_only"):
        print("Local review only: noindex retained; publication not authorized.")
    print(f"Source: {summary['source']}")
    print(f"Output: {summary['output']}")
    print(f"Files: {summary['file_count']}")
    for name in summary["files"]:
        print(f"  {name}")
    print(f"Validation: {summary['validation']}")
    print(f"Status: {summary['status']}")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = SafeArgumentParser(
        description="Build an allowlisted static DATA LAB deployment directory."
    )
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    coupon_mode = parser.add_mutually_exclusive_group()
    coupon_mode.add_argument("--without-coupon-help", action="store_true",
                            help="Rollback article, price link and sitemap entry together.")
    coupon_mode.add_argument("--coupon-review-candidate", action="store_true",
                        help="Local noindex review only; requires a new output outside repo under OS temp.")
    books_mode = parser.add_mutually_exclusive_group()
    books_mode.add_argument("--with-books-device", dest="books_device_enabled", action="store_true",
                           help="Explicitly generate device article, internal link and sitemap entry; publication requires separate approval.")
    books_mode.add_argument("--without-books-device", dest="books_device_enabled", action="store_false",
                           help="Rebuild without device article, internal link and sitemap entry (default).")
    parser.set_defaults(books_device_enabled=False)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        repo_root = resolve_repo_root(args.repo_root)
        if args.books_device_enabled and args.coupon_review_candidate:
            raise ValidationError("DEVICE_PUBLIC_AND_COUPON_REVIEW_INCOMPATIBLE")
        if args.coupon_review_candidate:
            if args.output is None or not args.output.is_absolute():
                raise UnsafeOutputError("REVIEW_REQUIRES_ABSOLUTE_TEMP_OUTPUT")
            temp_root = Path(tempfile.gettempdir()).resolve(strict=True)
            output = args.output.resolve()
            if (output == temp_root or temp_root not in output.parents
                    or output == repo_root or repo_root in output.parents
                    or output.exists() or args.output.is_symlink()
                    or any(parent.is_symlink() for parent in args.output.parents)):
                raise UnsafeOutputError("REVIEW_OUTPUT_NOT_NEW_ISOLATED_TEMP")
        else:
            output = resolve_output(repo_root, args.output)
        files = collect_sources(repo_root)
        secrets = read_known_secret_values(repo_root)
        validate_files(files, secrets)
        coupon_public = not args.coupon_review_candidate and not args.without_coupon_help
        if args.coupon_review_candidate or coupon_public:
            sys.path.insert(0, str(ROOT))
            from scripts.coupon_help_candidate_bundle import build_candidate_bundle, REQUIRED_INPUTS
            draft_path = repo_root / "preview" / "coupon-help.html"
            if draft_path.is_symlink() or draft_path.parent.is_symlink():
                raise SourceError("REVIEW_SOURCE_SYMLINK_FORBIDDEN")
            if not draft_path.is_file():
                raise SourceError("REVIEW_DRAFT_MISSING")
            sources = {name: files[name] for name in REQUIRED_INPUTS if name in files}
            sources['preview/coupon-help.html'] = draft_path.read_bytes()
            try:
                if coupon_public:
                    from scripts.coupon_help_public_release import build_public_release
                    bundle = build_public_release(sources)
                else:
                    bundle = build_candidate_bundle(sources)
            except ValueError as error:
                raise ValidationError("REVIEW_TEMPLATE_INVALID") from error
            # Preserve every existing security header and add noindex everywhere.
            if args.coupon_review_candidate:
                bundle['_headers'] = files['_headers'] + b'\n/*\n  X-Robots-Tag: noindex, nofollow\n'
            files.update(bundle)
            validate_files(files, secrets, coupon_review=args.coupon_review_candidate, coupon_public=coupon_public)
        if args.books_device_enabled:
            sys.path.insert(0, str(ROOT))
            from scripts.books_device_release_bundle import build_release_bundle
            device_draft = repo_root / 'preview' / 'books-device-review.html'
            if device_draft.is_symlink() or device_draft.parent.is_symlink():
                raise SourceError('DEVICE_SOURCE_SYMLINK_FORBIDDEN')
            if not device_draft.is_file():
                raise SourceError('DEVICE_DRAFT_MISSING')
            try:
                files = build_release_bundle(files, device_draft.read_bytes(), enabled=True)
            except ValueError as error:
                raise ValidationError('DEVICE_TEMPLATE_INVALID') from error
        validate_files(files, secrets, coupon_review=args.coupon_review_candidate,
                       coupon_public=coupon_public, books_device=args.books_device_enabled)
        if not args.dry_run:
            atomic_publish(output, files, coupon_review=args.coupon_review_candidate, coupon_public=coupon_public, books_device=args.books_device_enabled)
        summary = build_summary(repo_root, output, files, args.dry_run)
        if args.coupon_review_candidate:
            summary["mode"] = "coupon-review-dry-run" if args.dry_run else "coupon-review-generated"
            summary["local_review_only"] = True
    except SourceError as error:
        print(f"static site build failed: {error}", file=sys.stderr)
        return 2
    except UnsafeOutputError as error:
        print(f"static site build failed: {error}", file=sys.stderr)
        return 3
    except ValidationError as error:
        print(f"static site build failed: {error}", file=sys.stderr)
        return 4
    except (BuildInternalError, OSError):
        print("static site build failed: INTERNAL_ERROR", file=sys.stderr)
        return 1
    except Exception:
        print("static site build failed: INTERNAL_ERROR", file=sys.stderr)
        return 1
    print_summary(summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
