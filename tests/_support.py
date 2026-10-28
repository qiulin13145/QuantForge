"""Shared experiment specification for control and verdict tests."""


def proposal():
    return {
        "source": "def run(x):\n    return x + 1\n",
        "explanations": [{"id": "f"}, {"id": "c"}],
        "conditions": [
            {
                "id": "primary",
                "kind": "primary",
                "cost": 1,
                "predictions": {"f": "gain", "c": "gain"},
            },
            {
                "id": "cheap",
                "kind": "control",
                "cost": 1,
                "source": "def run(x):\n    return x\n",
                "predictions": {"f": "loss", "c": "gain"},
            },
            {
                "id": "expensive",
                "kind": "control",
                "cost": 2,
                "source": "def run(x):\n    return x\n",
                "predictions": {"f": "loss", "c": "gain"},
            },
        ],
    }
