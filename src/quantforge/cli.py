"""Command-line interface for QuantForge workspaces."""

import argparse
import json
from pathlib import Path
import sys

from .controls import ContractError
from .engine import abort_round, initialize, recover, retry_failed, run_round
from .storage import load


def main():
    parser = argparse.ArgumentParser(prog="quantforge")
    commands = parser.add_subparsers(dest="command", required=True)
    init = commands.add_parser("init", help="initialize a search workspace")
    init.add_argument("workspace", type=Path)
    init.add_argument("--config", required=True, type=Path)
    for name in ("step", "status", "recover", "abort"):
        cmd = commands.add_parser(name)
        cmd.add_argument("workspace", type=Path)
    retry = commands.add_parser("retry")
    retry.add_argument("workspace", type=Path)
    retry.add_argument("key")
    args = parser.parse_args()
    try:
        if args.command == "init":
            result = {"state": str(initialize(args.workspace, args.config))}
        elif args.command == "step":
            result = run_round(args.workspace)
        elif args.command == "recover":
            recover(args.workspace)
            result = {"recovered": True}
        elif args.command == "abort":
            abort_round(args.workspace)
            result = {"abandoned": True}
        elif args.command == "retry":
            retry_failed(args.workspace, args.key)
            result = {"retry": args.key}
        else:
            state = load(args.workspace / "state.json")
            result = {"round": state["round"], "spent": state["spent"], "budget": state["config"]["budget"], "open_residuals": [r for r in state["residuals"] if r["status"] == "OPEN"], "pending": state["pending"] and {k: v for k, v in state["pending"].items() if k not in ("packet", "calls")}, "in_flight": state["in_flight"]}
        print(json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False))
    except (ContractError, OSError, ValueError, RuntimeError, KeyError) as exc:
        print(f"quantforge: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
