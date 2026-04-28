"""Schema contract validation for runtime artifacts."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict


class ContractValidationError(ValueError):
    """Raised when a runtime artifact violates a JSON schema contract."""


class ContractValidator:
    """Loads and validates runtime contract schemas."""

    def __init__(self, runtime_dir: Path) -> None:
        self.runtime_dir = runtime_dir
        self._schema_cache: Dict[str, Dict[str, object]] = {}

    def validate(self, contract_name: str, payload: Dict[str, object]) -> None:
        schema = self._load_schema(contract_name)
        try:
            import jsonschema  # type: ignore
        except ImportError as exc:
            raise RuntimeError(
                "jsonschema is required for runtime contract validation. "
                "Install with `pip install jsonschema`."
            ) from exc

        try:
            jsonschema.validate(instance=payload, schema=schema)
        except Exception as exc:  # pragma: no cover - vendor exception type variability
            raise ContractValidationError(
                f"Contract validation failed for {contract_name}: {exc}"
            ) from exc

    def _load_schema(self, contract_name: str) -> Dict[str, object]:
        if contract_name in self._schema_cache:
            return self._schema_cache[contract_name]

        schema_file = {
            "handoff_packet": "schemas/handoff_packet.schema.json",
            "stage_result": "schemas/stage_result.schema.json",
            "gate_result": "schemas/gate_result.schema.json",
            "run_state": "schemas/run_state.schema.json",
        }.get(contract_name)

        if schema_file is None:
            raise ValueError(f"Unknown contract name: {contract_name}")

        path = self.runtime_dir / schema_file
        schema = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(schema, dict):
            raise ValueError(f"Schema at {path} is not a JSON object")

        self._schema_cache[contract_name] = schema
        return schema
