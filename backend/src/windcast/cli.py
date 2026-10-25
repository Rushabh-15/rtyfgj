"""``windcast`` command line: check, precompute, report, validate, ingest."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from windcast.config import load_settings


def _check(_: argparse.Namespace) -> int:
    from windcast import contracts
    from windcast.snapshot import load_snapshot

    settings = load_settings()
    results = contracts.run_checks(load_snapshot(settings.snapshot_dir))
    for r in results:
        print(f"{'PASS' if r.passed else 'FAIL'}  {r.name}: {r.detail}")
    return 0 if all(r.passed for r in results) else 1


def _precompute(args: argparse.Namespace) -> int:
    from windcast.precompute import precompute
    from windcast.snapshot import load_snapshot

    settings = load_settings()
    out = Path(args.out) if args.out else settings.derived_dir
    written = precompute(load_snapshot(settings.snapshot_dir), out)
    print(f"wrote {len(written)} files to {out}")
    return 0


def _report(args: argparse.Namespace) -> int:
    from windcast.report import write_report

    settings = load_settings()
    out = Path(args.out)
    write_report(settings.derived_dir, out)
    print(f"wrote {out}")
    return 0


def _validate(args: argparse.Namespace) -> int:
    from windcast.validation import write_validation

    settings = load_settings()
    ok = write_validation(settings, Path(args.validation_dir), Path(args.out))
    print(f"wrote {args.out}")
    return 0 if ok or not args.strict else 1


def _ingest(args: argparse.Namespace) -> int:
    from windcast.ingest import compare_manifests, pull

    manifest = pull(Path(args.out))
    if args.compare:
        differences = compare_manifests(manifest, Path(args.compare))
        for d in differences:
            print(f"DIFFERENT  {d}")
        if differences:
            return 2
        print("identical to the committed snapshot")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="windcast", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("check", help="run data contracts on the snapshot").set_defaults(func=_check)
    p = sub.add_parser("precompute", help="rebuild the derived tables the API serves")
    p.add_argument("--out", help="output directory (default: <data>/derived)")
    p.set_defaults(func=_precompute)
    p = sub.add_parser("report", help="write the accuracy report from the derived tables")
    p.add_argument("--out", default="../docs/analysis.md")
    p.set_defaults(func=_report)
    p = sub.add_parser("validate", help="write the validation checklist")
    p.add_argument("--validation-dir", default="../validation")
    p.add_argument("--out", default="../docs/validation.md")
    p.add_argument("--strict", action="store_true", help="exit 1 if any automated check fails")
    p.set_defaults(func=_validate)
    p = sub.add_parser("ingest", help="download the snapshot window again from Elexon")
    p.add_argument("--out", required=True)
    p.add_argument("--compare", help="manifest.json to compare hashes with")
    p.set_defaults(func=_ingest)
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())
