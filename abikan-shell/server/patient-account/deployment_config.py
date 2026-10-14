"""Fail-closed deployment configuration validation for the Hospital EMR backend."""

from __future__ import annotations

import os
from collections.abc import Mapping


class ConfigurationError(RuntimeError):
    """Raised when required backend deployment configuration is unsafe."""


REQUIRED_SERVICE_VARIABLES = (
    "ABIKAN_OPENMRS_ADMIN_USER",
    "ABIKAN_OPENMRS_ADMIN_PASSWORD",
    "ABIKAN_OPENELIS_USER",
    "ABIKAN_OPENELIS_PASSWORD",
    "ABIKAN_ODOO_USER",
    "ABIKAN_ODOO_PASSWORD",
)

ALLOWED_ENVIRONMENTS = {"development", "test", "production"}

# These are well-known weak placeholders, not deployment secrets.
WEAK_PRODUCTION_VALUES = {
    "123456",
    "admin",
    "admin123",
    "changeme",
    "default",
    "password",
    "postgres",
    "root",
    "test",
}


def validate_deployment_config(
    environment: Mapping[str, str] | None = None,
) -> str:
    values = environment if environment is not None else os.environ
    deployment_environment = str(values.get("ABIKAN_ENVIRONMENT") or "").strip().lower()
    if deployment_environment not in ALLOWED_ENVIRONMENTS:
        raise ConfigurationError(
            "ABIKAN_ENVIRONMENT must be explicitly set to development, test, or production."
        )

    missing = [
        name for name in REQUIRED_SERVICE_VARIABLES if not str(values.get(name) or "").strip()
    ]
    if missing:
        raise ConfigurationError(
            "Required deployment configuration is missing: " + ", ".join(sorted(missing))
        )

    if deployment_environment == "production":
        weak = [
            name
            for name in REQUIRED_SERVICE_VARIABLES
            if str(values.get(name) or "").strip().lower() in WEAK_PRODUCTION_VALUES
        ]
        if weak:
            raise ConfigurationError(
                "Production configuration contains development/default values for: "
                + ", ".join(sorted(weak))
            )

    return deployment_environment
