#!/usr/bin/env python3
"""A real numerical Block32 evaluator for QuantForge integration examples.

The calling framework runs this program as an independent subprocess.  The
candidate code executes with the evaluator's OS permissions; a subprocess is
not a security sandbox.  Use only trusted candidates or add external isolation.
"""
from __future__ import annotations

import contextlib
import io
import json
import math
import random
import sys
from typing import Any

LEVELS = (0.0, 0.5, 1.0, 1.5, 2.0, 3.0, 4.0, 6.0)


def reference(values: list[float]) -> list[float]:
    """E2M1 nearest decoding, with E8M0 power-of-two shared scaling."""
    largest = max(abs(v) for v in values)
    exponent = max(-127, min(127, math.floor(math.log2(largest)) - 2)) if largest else -127
    scale = math.ldexp(1.0, exponent)
    return [math.copysign(min(LEVELS, key=lambda x: (abs(x - abs(v) / scale), -x)) * scale, v)
            for v in values]


def legal_block(values: list[float]) -> bool:
    """Check existence of a single E8M0 scale explaining all E2M1 codes."""
    if len(values) != 32 or not all(math.isfinite(x) for x in values):
        return False
    maximum = max(map(abs, values))
    if maximum == 0:
        return True
    center = math.floor(math.log2(maximum))
    for exponent in range(max(-127, center - 3), min(127, center + 2) + 1):
        scale = math.ldexp(1.0, exponent)
        if all(any(math.isclose(abs(x), level * scale, rel_tol=1e-8, abs_tol=1e-40)
                   for level in LEVELS) for x in values):
            return True
    return False


def evaluate(request: dict[str, Any]) -> dict[str, Any]:
    source = request['source']
    condition = request['condition']
    contract = request['contract']
    phase = request['phase']
    if not isinstance(source, str) or len(source) > 1_000_000:
        raise ValueError('source must be a Python source string of at most 1 MB')
    if not isinstance(condition, dict) or not isinstance(contract, dict):
        raise ValueError('condition and contract must be JSON objects')
    if phase not in ('evaluation', 'probe', 'measurement'):
        raise ValueError('phase must be evaluation, probe, or measurement')
    count = contract.get('num_blocks', 32)
    seed = contract.get('seed', 0)
    if type(count) is not int or not 1 <= count <= 10_000 or type(seed) is not int:
        raise ValueError('invalid num_blocks or seed')

    # Candidate output is redirected so the wire protocol stays valid JSON.
    namespace = {'__name__': 'quantforge_candidate'}
    parent_namespace = {'__name__': 'quantforge_parent'}
    output = io.StringIO()
    with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
        exec(compile(source, '<quantforge-candidate>', 'exec'), namespace)
        candidate = namespace.get('quantize')
        if not callable(candidate):
            raise ValueError('candidate must define quantize(values, condition)')
        exec(compile(request['parent_source'], '<quantforge-parent>', 'exec'), parent_namespace)
        parent = parent_namespace.get('quantize')
        if not callable(parent):
            raise ValueError('parent must define quantize(values, condition)')
        rng = random.Random(seed)
        total = baseline = 0.0
        changed = False
        for index in range(count):
            # Real numeric inputs, intentionally small and deterministic.
            block = [rng.gauss(0, 1) * (3.0 if (i + index) % 17 == 0 else 1.0)
                     for i in range(32)]
            decoded = list(candidate(block.copy(), condition.copy()))
            if not all(isinstance(x, (int, float)) and not isinstance(x, bool) for x in decoded):
                raise ValueError('candidate output must contain numbers')
            decoded = [float(x) for x in decoded]
            if not legal_block(decoded):
                raise ValueError('candidate produced non-finite or invalid Block32 E2M1/E8M0 output')
            ref = list(parent(block.copy(), {'id': 'parent', 'kind': 'primary'}))
            if not legal_block(ref):
                raise ValueError('parent produced invalid Block32 output')
            total += sum((x - q) ** 2 for x, q in zip(block, decoded))
            baseline += sum((x - q) ** 2 for x, q in zip(block, ref))
            changed |= decoded != ref
    score = total / (count * 32)
    baseline_score = baseline / (count * 32)
    tolerance = max(1e-12, baseline_score * 1e-9)
    outcome = ('improved' if score < baseline_score - tolerance else
               'worse' if score > baseline_score + tolerance else 'unchanged')
    result = {'success': True, 'safe': True, 'score': score, 'outcome': outcome,
              'signature': changed, 'details': {'baseline_score': baseline_score,
                                                 'num_blocks': count, 'seed': seed,
                                                 'phase': phase}}
    if phase == 'probe':
        prior = evaluate({'source': condition['candidate_source'], 'parent_source': request['parent_source'],
                          'condition': condition['primary_condition'],
                          'contract': contract, 'phase': 'evaluation'})
        delta = score - prior['score']
        result['response_valid'] = abs(delta) > 1e-12 and (
            condition['verdict'] != 'SUPPORTED' or delta < 0)
    return result


def main() -> None:
    try:
        request = json.load(sys.stdin)
        if not isinstance(request, dict):
            raise ValueError('request must be a JSON object')
        result = evaluate(request)
    except Exception as exc:
        result = {'success': False, 'safe': False, 'score': None, 'outcome': 'error',
                  'signature': False, 'details': {'error': f'{type(exc).__name__}: {exc}'}}
    json.dump(result, sys.stdout, allow_nan=False)
    sys.stdout.write('\n')


if __name__ == '__main__':
    main()
