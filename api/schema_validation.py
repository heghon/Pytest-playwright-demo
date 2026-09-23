import json
from functools import lru_cache
from pathlib import Path

from jsonschema import Draft202012Validator

SCHEMA_DIR = Path(__file__).resolve().parent / "schemas"


"""
    Reads schemas/<name>.schema.json, once per name per session.

    A missing schema says which ones do exist, because the name comes from a
    feature file — a typo there is a sentence a human wrote, not a stack trace
    they want to read.
"""
@lru_cache(maxsize=None)
def load_schema(name: str) -> dict:
    path = SCHEMA_DIR / f"{name}.schema.json"
    if not path.is_file():
        available = sorted(p.name.removesuffix(".schema.json") for p in SCHEMA_DIR.glob("*.schema.json"))
        raise AssertionError(
            f"There is no '{name}' schema in {SCHEMA_DIR.name}/. "
            f"Available: {', '.join(available) or 'none'}."
        )
    return json.loads(path.read_text(encoding="utf-8"))


"""
    Checks a payload against a named schema, reporting every violation.

    jsonschema.validate() raises on the first problem it meets, which turns a
    response with four wrong fields into four consecutive runs. iter_errors
    collects the lot, so one failed scenario tells the whole story — and each
    line is prefixed with the JSON path, so "$.dimensions.width" points at the
    exact field instead of leaving you to search the body for it.
"""
def assert_matches_schema(payload, name: str, described_as: str = "payload") -> None:
    validator = Draft202012Validator(load_schema(name))
    errors = sorted(validator.iter_errors(payload), key=lambda error: error.json_path)
    if not errors:
        return

    problems = "\n".join(f"  {error.json_path}: {error.message}" for error in errors)
    plural = "problem" if len(errors) == 1 else "problems"
    raise AssertionError(
        f"The {described_as} does not match the '{name}' schema "
        f"({len(errors)} {plural}):\n{problems}"
    )
