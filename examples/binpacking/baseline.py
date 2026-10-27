"""An initial next-fit heuristic for one-dimensional bin packing."""


def pack(items, capacity):
    """Return bins containing every item, each with sum at most capacity."""
    bins = []
    for item in items:
        if not bins or sum(bins[-1]) + item > capacity:
            bins.append([])
        bins[-1].append(item)
    return bins
