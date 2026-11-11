"""Command-line entrypoint.

Usage:
    python -m outreach run [--candidates N] [--live]

`run` executes the full pipeline with simulated sending by default.
--live enables real SMTP sending and additionally requires SMTP_HOST,
SMTP_USER, SMTP_PASS and SMTP_FROM in the environment; it is never the
default and is not used for the demo run.
"""

import argparse
import sys

from .pipeline import run_pipeline


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="outreach",
                                     description="Automated Micro-Influencer Outreach System")
    sub = parser.add_subparsers(dest="command", required=True)

    run_p = sub.add_parser("run", help="Run the full pipeline end-to-end")
    run_p.add_argument("--candidates", type=int, default=160,
                       help="Target number of candidate channels to discover (default 160)")
    run_p.add_argument("--live", action="store_true",
                       help="Enable live SMTP sending (default: simulated, nothing is sent)")

    args = parser.parse_args(argv)
    if args.command == "run":
        run_pipeline(target_candidates=args.candidates, live=args.live)
    return 0


if __name__ == "__main__":
    sys.exit(main())
