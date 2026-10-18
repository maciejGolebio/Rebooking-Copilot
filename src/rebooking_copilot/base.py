"""Shared config for models that appear in the output: frozen, strict about fields, camelCase in JSON (D-05)."""

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel


class OutputModel(BaseModel):
    """Constructed by field name in code; serialised with camelCase aliases (`model_dump(by_alias=True)`)."""

    model_config = ConfigDict(frozen=True, extra="forbid", alias_generator=to_camel, validate_by_name=True, validate_by_alias=True)
