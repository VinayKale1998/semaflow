import re
import logging
from pathlib import Path
from typing import Any, Callable

import yaml

from .models import ModelSelection, ResolvedSQL

logger = logging.getLogger(__name__)

_SEMANTIC_LAYER_PATH = Path(__file__).parent.parent / "semantic" / "semantic_layer.yaml"


class ResolverError(Exception):
    pass


# Maps YAML scalar type names to Python coercer callables.
# All inputs arrive as strings from ModelSelection.filters; coercers are responsible
# for raising ValueError/TypeError on bad input.
TYPE_COERCERS: dict[str, Callable[[str], Any]] = {
    "integer": int,
    "float": float,
    "string": str,
    "boolean": lambda v: v.lower() in ("true", "1", "yes"),
    "date": str,  # kept as string; SQL uses ISO-format date literals
}


def _load_semantic_layer() -> dict:
    with open(_SEMANTIC_LAYER_PATH) as f:
        return yaml.safe_load(f)


def _validate_semantic_layer(semantic_layer: dict) -> None:
    """Raise RuntimeError at startup if any template placeholder lacks a parameter entry.

    Catches config drift between sql_template and parameters early — before any
    request is served.
    """
    for measure_key, measure in semantic_layer.get("measures", {}).items():
        template = measure.get("sql_template", "")
        placeholders = set(re.findall(r"\{(\w+)\}", template))
        declared = set(measure.get("parameters", {}).keys())
        undeclared = placeholders - declared
        if undeclared:
            raise RuntimeError(
                f"semantic_layer.yaml: measure '{measure_key}' has undeclared "
                f"placeholder(s): {sorted(undeclared)!r}. "
                "Add each one to the measure's parameters section."
            )


# Load and validate once at import time so any misconfiguration is a startup crash,
# not a per-request failure.
_SEMANTIC_LAYER: dict = _load_semantic_layer()
_validate_semantic_layer(_SEMANTIC_LAYER)


def _valid_glossary_keys(namespace: dict) -> list[str]:
    """Return keys that have a sql fragment (excludes metadata keys like dataset_reference_date)."""
    return [k for k, v in namespace.items() if isinstance(v, dict) and "sql" in v]


def _resolve_glossary_param(
    param_name: str,
    param_def: dict,
    glossary_refs: list[str],
    glossary: dict,
) -> str:
    category = param_def["category"]
    matches = [ref for ref in glossary_refs if ref.startswith(f"{category}.")]

    if len(matches) > 1:
        raise ResolverError(
            f"Parameter '{param_name}': ambiguous — multiple glossary refs match "
            f"category '{category}': {matches}. Supply at most one."
        )

    if len(matches) == 1:
        ref = matches[0]
        key = ref.split(".", 1)[1]
        namespace = glossary.get(category, {})
        entry = namespace.get(key)
        valid = _valid_glossary_keys(namespace)

        if entry is None:
            raise ResolverError(
                f"Parameter '{param_name}': unknown glossary ref '{ref}'. "
                f"Valid keys for '{category}': {valid!r}"
            )
        if not isinstance(entry, dict) or "sql" not in entry:
            raise ResolverError(
                f"Parameter '{param_name}': glossary ref '{ref}' exists but has "
                f"no 'sql' fragment. Valid keys for '{category}': {valid!r}"
            )
        return entry["sql"]

    # No matching ref supplied — fall back to default if declared.
    if "default" in param_def:
        return param_def["default"]

    raise ResolverError(
        f"Parameter '{param_name}': required glossary ref for category "
        f"'{category}' not provided and no default is set."
    )


def _resolve_scalar_param(
    param_name: str,
    param_def: dict,
    filters: dict[str, str],
) -> Any:
    scalar_type = param_def["type"]
    coercer = TYPE_COERCERS.get(scalar_type)

    if coercer is None:
        raise ResolverError(
            f"Parameter '{param_name}': unknown scalar type '{scalar_type}' in "
            f"semantic_layer.yaml. Valid types: {sorted(TYPE_COERCERS.keys())!r}"
        )

    if param_name in filters:
        raw = filters[param_name]
        try:
            return coercer(raw)
        except (ValueError, TypeError) as exc:
            raise ResolverError(
                f"Parameter '{param_name}': cannot coerce {raw!r} to "
                f"{scalar_type}: {exc}"
            ) from exc

    if "default" in param_def:
        return param_def["default"]

    raise ResolverError(
        f"Parameter '{param_name}': required scalar parameter not found in "
        "filters and no default is set."
    )


def resolve(selection: ModelSelection) -> ResolvedSQL:
    """Assemble SQL from a ModelSelection by substituting template parameters.

    Glossary-kind parameters resolve to SQL fragments; scalar-kind parameters
    are coerced to their declared type and substituted literally.

    Note: scalar string values are substituted directly into the SQL template.
    The guardrails layer is the backstop against injection; callers must not
    bypass it.

    Raises ResolverError on any resolution failure.
    """
    measure_def = _SEMANTIC_LAYER["measures"][selection.measure]
    template: str = measure_def["sql_template"]
    params_def: dict = measure_def.get("parameters", {})
    glossary: dict = _SEMANTIC_LAYER.get("glossary", {})

    substitutions: dict[str, Any] = {}

    for param_name, param_def in params_def.items():
        kind = param_def.get("kind")
        if kind == "glossary":
            substitutions[param_name] = _resolve_glossary_param(
                param_name, param_def, selection.glossary_refs, glossary
            )
        elif kind == "scalar":
            substitutions[param_name] = _resolve_scalar_param(
                param_name, param_def, selection.filters
            )
        else:
            raise ResolverError(
                f"Parameter '{param_name}': unknown kind '{kind}' in "
                "semantic_layer.yaml. Valid values: 'glossary', 'scalar'."
            )

    sql = template.format(**substitutions).strip()

    return ResolvedSQL(
        sql=sql,
        measure=selection.measure,
        parameters_applied={k: str(v) for k, v in substitutions.items()},
    )
