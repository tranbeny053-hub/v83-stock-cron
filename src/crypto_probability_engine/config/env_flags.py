"""Environment flag parsing."""


TRUE_VALUES = {"1", "true", "yes", "on"}


def parse_bool(value: str | None, *, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in TRUE_VALUES
