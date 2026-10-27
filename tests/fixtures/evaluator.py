import json
import sys

request = json.load(sys.stdin)
namespace = {}
exec(compile(request["source"], "<candidate>", "exec"), namespace)
output = namespace["run"](1)
parent = {}
exec(compile(request["parent_source"], "<parent>", "exec"), parent)
parent_output = parent["run"](1)
result = {"success": True, "safe": True, "score": 3 - output,
          "outcome": "gain" if output > parent_output else "loss", "signature": output > parent_output}
if request["phase"] == "probe":
    candidate = {}
    exec(compile(request["condition"]["candidate_source"], "<candidate>", "exec"), candidate)
    result["response_valid"] = output > candidate["run"](1)
json.dump(result, sys.stdout, allow_nan=False)
