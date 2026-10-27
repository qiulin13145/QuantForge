"""Run a candidate function under Python's line tracer in a child process."""

import json
import sys


def main():
    request = json.load(sys.stdin)
    source, scope = request["source"], request["scope"]
    filename = "<quantforge-candidate>"
    namespace = {"__name__": "quantforge_candidate"}
    exec(compile(source, filename, "exec"), namespace)
    fn = namespace.get(scope)
    if not callable(fn):
        raise ValueError("probe scope must be a top-level callable")
    lines = set()

    def trace(frame, event, arg):
        if event == "line" and frame.f_code.co_filename == filename:
            lines.add(frame.f_lineno)
        return trace

    sys.settrace(trace)
    try:
        probe_input = request["probe_input"]
        if isinstance(probe_input, dict) and "args" in probe_input:
            result = fn(*probe_input["args"], **probe_input.get("kwargs", {}))
        else:
            result = fn(probe_input)
    finally:
        sys.settrace(None)
    print(json.dumps({"lines": sorted(lines), "output": result}, allow_nan=False))


if __name__ == "__main__":
    main()
