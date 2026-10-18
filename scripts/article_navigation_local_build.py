"""New OS-temp output only. Default OFF; never used by the public build.

Generated opt-in artifacts contain live-capable consent code. Do not serve or open
them without separate publication/transmission approval. Tests use mocks only.
"""
import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.books_device_local_build import check_output, collect_rehearsal, load_builder

from scripts.article_navigation_release_bundle import (
    PAGES, ASSETS, TAG, CONSENT_NEW,
    build_navigation_bundle as build_local_bundle, collect_assets)


def collect_local_bundle(*, enabled=False):
    baseline = collect_rehearsal('release')
    assets = collect_assets(ROOT) if enabled else {}
    files = build_local_bundle(baseline, assets, enabled=enabled)
    builder = load_builder()
    secrets = builder.read_known_secret_values(ROOT)
    ordinary = {name: data for name, data in files.items() if name not in ASSETS}
    builder.validate_files(ordinary, secrets, coupon_public=True, books_device=True)
    for data in assets.values():
        substitute = dict(ordinary)
        substitute['404.html'] = data
        builder.validate_files(substitute, secrets, coupon_public=True, books_device=True)
    return files


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--with-article-navigation', dest='enabled', action='store_true')
    mode.add_argument('--without-article-navigation', dest='enabled', action='store_false')
    parser.set_defaults(enabled=False)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args(argv)
    try:
        output = check_output(args.output)
        files = collect_local_bundle(enabled=args.enabled)
        if not args.dry_run:
            output.mkdir(parents=True, exist_ok=False)
            for name, data in files.items():
                path = output / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(data)
            if {p.relative_to(output).as_posix() for p in output.rglob('*') if p.is_file()} != set(files):
                raise ValueError('LOCAL_OUTPUT_SET_MISMATCH')
            if any((output / name).read_bytes() != data for name, data in files.items()):
                raise ValueError('LOCAL_OUTPUT_CONTENT_MISMATCH')
    except (ValueError, OSError, UnicodeError):
        print('LOCAL_NAVIGATION_BUILD_FAILED', file=sys.stderr)
        return 1
    print(f'LOCAL_ONLY navigation={args.enabled} files={len(files)} dry_run={args.dry_run}')
    print('Not served or executed. Live-capable opt-in artifacts require separate approval.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
