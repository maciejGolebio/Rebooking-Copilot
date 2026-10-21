"""recommendations.json (D-05): one file per run, validated before it is written by re-parsing it with its pydantic models.

The schema is generated from the pydantic models and committed at schemas/recommendations.schema.json; a test keeps
the two identical.
Regenerate it with:  uv run python -m rebooking_copilot.output
"""

import json
from pathlib import Path
from typing import Literal

from pydantic import AwareDatetime

from rebooking_copilot.base import OutputModel
from rebooking_copilot.decision import Recommendation
from rebooking_copilot.loader import FareSnapshot
from rebooking_copilot.policy import DEFAULT_POLICY, PolicyConfig

SCHEMA_PATH = Path(__file__).resolve().parents[2] / "schemas" / "recommendations.schema.json"


class RecommendationsFile(OutputModel):
    schema_version: Literal["1"] = "1"
    as_of: AwareDatetime
    captured_at: AwareDatetime
    reasoner: str  # the requested mode; each recommendation records who actually decided it
    policy: PolicyConfig
    recommendations: tuple[Recommendation, ...]


def build_file(recs: tuple[Recommendation, ...], snapshot: FareSnapshot, *, reasoner_id: str, policy: PolicyConfig = DEFAULT_POLICY) -> RecommendationsFile:
    as_of = recs[0].as_of if recs else snapshot.captured_at
    return RecommendationsFile(as_of=as_of, captured_at=snapshot.captured_at, reasoner=reasoner_id, policy=policy, recommendations=recs)


def write_file(path: Path, file: RecommendationsFile) -> Path:
    """Serialise, validate the exact bytes against the schema (by re-parsing them), then write."""
    text = file.model_dump_json(by_alias=True, indent=2) + "\n"
    RecommendationsFile.model_validate_json(text)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def schema_json() -> str:
    schema = RecommendationsFile.model_json_schema(by_alias=True, mode="serialization")
    return json.dumps(schema, indent=2, sort_keys=True) + "\n"


if __name__ == "__main__":
    SCHEMA_PATH.parent.mkdir(parents=True, exist_ok=True)
    SCHEMA_PATH.write_text(schema_json(), encoding="utf-8")
    print(f"wrote {SCHEMA_PATH}")
