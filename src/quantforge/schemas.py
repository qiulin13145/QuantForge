"""Structured proposer outputs for each stage of the search cycle."""

PROPOSAL_SCHEMA = {
    "type": "object",
    "required": ["source", "explanations", "conditions"],
    "properties": {
        "source": {"type": "string"},
        "explanations": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"id": {"type": "string"}, "claim": {"type": "string"}},
                "required": ["id", "claim"],
                "additionalProperties": False,
            },
        },
        "conditions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "kind": {"type": "string", "enum": ["primary", "control"]},
                    "cost": {"type": "number"},
                    "source": {"type": "string"},
                    "predictions": {
                        "type": "object",
                        "additionalProperties": {"type": "string"},
                    },
                },
                "required": ["id", "kind", "cost", "predictions"],
                "additionalProperties": False,
            },
        },
    },
    "additionalProperties": False,
}

RESIDUAL_SCHEMA = {
    "type": "object",
    "required": ["id", "question", "scope", "probe_input"],
    "properties": {
        "id": {"type": "string"},
        "question": {"type": "string"},
        "scope": {"type": "string"},
        "probe_input": {},
    },
    "additionalProperties": False,
}

RESPONSE_SCHEMA = {
    "type": "object",
    "required": ["source"],
    "properties": {"source": {"type": "string"}},
    "additionalProperties": False,
}
