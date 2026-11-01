"""Small, explicit configuration surface for the existing stdio server."""

import os


def request_timeout():
    """Return bounded connect/read deadlines; never silently accept no timeout."""
    values = []
    for name, default in (
        ("QBT_CONNECT_TIMEOUT_SECONDS", "5"),
        ("QBT_READ_TIMEOUT_SECONDS", "30"),
    ):
        try:
            value = float(os.getenv(name, default))
        except ValueError as exc:
            raise ValueError(f"{name} must be a number between 0 and 120") from exc
        if not 0 < value <= 120:
            raise ValueError(f"{name} must be between 0 and 120")
        values.append(value)
    return tuple(values)
