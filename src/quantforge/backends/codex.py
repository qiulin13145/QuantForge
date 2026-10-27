#!/usr/bin/env python3
"""Call Codex as a command-line proposer: one JSON request in, one JSON object out.

The request has a string `prompt` and a JSON Schema object `json_schema`.
Requires an authenticated Codex CLI; no API keys are handled here.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile


def propose(request: object, *, command: str = "codex", model: str | None = None,
            timeout: int = 180) -> dict:
    if not isinstance(request, dict) or not isinstance(request.get("prompt"), str):
        raise ValueError("request must contain a string prompt")
    if not isinstance(request.get("json_schema"), dict):
        raise ValueError("request must contain a json_schema object")
    if timeout <= 0:
        raise ValueError("timeout must be positive")

    with tempfile.TemporaryDirectory(prefix="quantforge-proposer-") as name:
        directory = Path(name)
        schema = directory / "schema.json"
        result = directory / "result.json"
        schema.write_text(json.dumps(request["json_schema"], ensure_ascii=False), encoding="utf-8")
        cmd = [command, "exec", "--ephemeral", "--skip-git-repo-check", "--sandbox", "read-only",
               "--output-schema", str(schema), "--output-last-message", str(result), "--color", "never"]
        if model:
            cmd += ["--model", model]
        cmd.append("-")
        prompt = ("Generate the requested structured JSON response directly. "
                  "Do not call any tools, read files, write files, or run commands.\n\n"
                  + request["prompt"])
        try:
            completed = subprocess.run(cmd, input=prompt, text=True, stdout=subprocess.PIPE,
                                       stderr=subprocess.PIPE, timeout=timeout, cwd=directory,
                                       check=False)
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError(f"proposer timed out after {timeout} seconds") from exc
        except FileNotFoundError as exc:
            raise RuntimeError(f"proposer executable not found: {command}") from exc
        if completed.returncode != 0:
            # The CLI output can contain user/project data, so do not echo it by default.
            raise RuntimeError(f"proposer command failed with exit status {completed.returncode}")
        if not result.is_file():
            raise RuntimeError("proposer did not write a final response")
        try:
            response = json.loads(result.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise RuntimeError("proposer did not return valid JSON") from exc
        if not isinstance(response, dict):
            raise RuntimeError("proposer response must be a JSON object")
        return response


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--command", default=os.environ.get("QUANTFORGE_CODEX_COMMAND", "codex"))
    parser.add_argument("--model", default=os.environ.get("QUANTFORGE_CODEX_MODEL"))
    parser.add_argument("--timeout", type=int, default=180)
    args = parser.parse_args()
    try:
        request = json.load(sys.stdin)
        response = propose(request, command=args.command, model=args.model, timeout=args.timeout)
    except (ValueError, RuntimeError, json.JSONDecodeError) as exc:
        print(f"codex proposer: {exc}", file=sys.stderr)
        return 1
    json.dump(response, sys.stdout, ensure_ascii=False, allow_nan=False)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
