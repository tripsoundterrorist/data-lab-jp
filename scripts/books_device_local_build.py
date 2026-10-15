"""Generate release/rollback rehearsals only in a NEW isolated OS-temp directory.

Not a deploy command. The ordinary deployment build remains unchanged.
"""
import argparse
import importlib.util
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.books_device_release_bundle import build_release_bundle, ARTICLE
from scripts.coupon_help_candidate_bundle import REQUIRED_INPUTS
from scripts.coupon_help_public_release import build_public_release


def load_builder():
    spec = importlib.util.spec_from_file_location('device_baseline_builder', ROOT / 'scripts/build-static-site.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def check_output(path: Path) -> Path:
    if not path.is_absolute():
        raise ValueError('ABSOLUTE_TEMP_OUTPUT_REQUIRED')
    if path.is_symlink() or any(p.is_symlink() for p in path.parents):
        raise ValueError('SYMLINK_OUTPUT_FORBIDDEN')
    resolved = path.resolve()
    temp_root = Path(tempfile.gettempdir()).resolve(strict=True)
    if (resolved == temp_root or temp_root not in resolved.parents or resolved.exists()
            or resolved == ROOT or ROOT in resolved.parents):
        raise ValueError('NEW_ISOLATED_TEMP_OUTPUT_REQUIRED')
    return resolved


def collect_rehearsal(mode: str) -> dict[str, bytes]:
    if mode not in {'release', 'rollback'}:
        raise ValueError('UNKNOWN_REHEARSAL_MODE')
    builder = load_builder()
    baseline = builder.collect_sources(ROOT)
    secrets = builder.read_known_secret_values(ROOT)
    builder.validate_files(baseline, secrets)
    sources = {name: baseline[name] for name in REQUIRED_INPUTS if name in baseline}
    for name in ('coupon-help.html', 'books-device-review.html'):
        path = ROOT / 'preview' / name
        if path.is_symlink() or path.parent.is_symlink():
            raise ValueError('DRAFT_SYMLINK_FORBIDDEN')
        if name == 'coupon-help.html':
            sources['preview/coupon-help.html'] = path.read_bytes()
    baseline.update(build_public_release(sources))
    builder.validate_files(baseline, secrets, coupon_public=True)
    result = build_release_bundle(baseline,
        (ROOT / 'preview/books-device-review.html').read_bytes(), enabled=mode == 'release')
    # Apply the existing UTF-8/content/known-secret validators to every output.
    ordinary = {name: data for name, data in result.items() if name != ARTICLE}
    builder.validate_files(ordinary, secrets, coupon_public=True)
    if ARTICLE in result:
        check_article = dict(ordinary)
        check_article['404.html'] = result[ARTICLE]
        builder.validate_files(check_article, secrets, coupon_public=True)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mode', choices=('release', 'rollback'), required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args(argv)
    try:
        output = check_output(args.output)
        files = collect_rehearsal(args.mode)
        if not args.dry_run:
            # Exclusive creation; never replace a previous directory or touch dist.
            output.mkdir(parents=True, exist_ok=False)
            for name, data in files.items():
                destination = output / name
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(data)
            if {p.relative_to(output).as_posix() for p in output.rglob('*') if p.is_file()} != set(files):
                raise ValueError('LOCAL_OUTPUT_SET_MISMATCH')
            if any((output / name).read_bytes() != data for name, data in files.items()):
                raise ValueError('LOCAL_OUTPUT_CONTENT_MISMATCH')
    except (ValueError, OSError, UnicodeError):
        print('LOCAL_REHEARSAL_FAILED', file=sys.stderr)
        return 1
    print(f'LOCAL_ONLY mode={args.mode} files={len(files)} dry_run={args.dry_run}')
    print('No deployment, network or analytics execution performed.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
