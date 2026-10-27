"""Example candidate for the Block32 numerical evaluator, not a model quantizer."""
import math

def quantize(values, condition):
    levels = (0.0, 0.5, 1.0, 1.5, 2.0, 3.0, 4.0, 6.0)
    largest = max(abs(v) for v in values)
    exponent = max(-127, min(127, math.floor(math.log2(largest)) - 2)) if largest else -127
    scale = math.ldexp(1.0, exponent)
    return [math.copysign(min(levels, key=lambda x: (abs(x - abs(v) / scale), -x)) * scale, v)
            for v in values]
