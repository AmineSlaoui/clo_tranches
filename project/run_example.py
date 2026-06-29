# (c) 2027, Michael Robbins
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the Chapter 4.1 CLO tail-risk example.")
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--live-root", default=None)
    parser.add_argument(
        "--require-live-root",
        action="store_true",
        help="Fail if --live-root is omitted instead of copying the cached public SEC case-study output.",
    )
    args, passthrough = parser.parse_known_args(argv)

    cmd = [
        sys.executable,
        str(ROOT / "python" / "CLO.py"),
        "--output-dir",
        args.output_dir,
    ]

    if args.live_root:
        cmd.extend(["--mode", "live", "--live-root", args.live_root])
    else:
        if args.require_live_root:
            print("Live mode requires --live-root or BOOK2_CLO_LIVE_ROOT.", file=sys.stderr)
            return 2
        cmd.extend(["--mode", "public"])
    cmd.extend(passthrough)
    return subprocess.run(cmd, cwd=ROOT).returncode


if __name__ == "__main__":
    raise SystemExit(main())
