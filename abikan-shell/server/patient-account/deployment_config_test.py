"""Deployment configuration must fail closed without exposing secret values."""

from __future__ import annotations

import unittest
from unittest.mock import patch

import server
from deployment_config import ConfigurationError, validate_deployment_config


def valid_environment(mode: str = "production") -> dict[str, str]:
    return {
        "ABIKAN_ENVIRONMENT": mode,
        "ABIKAN_OPENMRS_ADMIN_USER": "hospital-service-account",
        "ABIKAN_OPENMRS_ADMIN_PASSWORD": "unique-openmrs-deployment-value",
        "ABIKAN_OPENELIS_USER": "hospital-laboratory-reader",
        "ABIKAN_OPENELIS_PASSWORD": "unique-laboratory-deployment-value",
        "ABIKAN_ODOO_USER": "hospital-finance-service",
        "ABIKAN_ODOO_PASSWORD": "unique-finance-deployment-value",
    }


class DeploymentConfigurationTests(unittest.TestCase):
    def test_environment_must_be_explicit(self) -> None:
        values = valid_environment()
        values.pop("ABIKAN_ENVIRONMENT")
        with self.assertRaises(ConfigurationError) as caught:
            validate_deployment_config(values)
        self.assertIn("ABIKAN_ENVIRONMENT", str(caught.exception))

    def test_missing_secret_fails_without_echoing_other_values(self) -> None:
        values = valid_environment()
        private_value = values.pop("ABIKAN_OPENMRS_ADMIN_PASSWORD")
        with self.assertRaises(ConfigurationError) as caught:
            validate_deployment_config(values)
        message = str(caught.exception)
        self.assertIn("ABIKAN_OPENMRS_ADMIN_PASSWORD", message)
        self.assertNotIn(private_value, message)
        self.assertNotIn(values["ABIKAN_ODOO_PASSWORD"], message)

    def test_production_rejects_well_known_development_defaults(self) -> None:
        values = valid_environment()
        weak_value = "changeme"
        values["ABIKAN_ODOO_PASSWORD"] = weak_value
        with self.assertRaises(ConfigurationError) as caught:
            validate_deployment_config(values)
        message = str(caught.exception)
        self.assertIn("ABIKAN_ODOO_PASSWORD", message)
        self.assertNotIn(weak_value, message)

    def test_development_accepts_local_values_but_still_requires_them(self) -> None:
        values = valid_environment("development")
        values["ABIKAN_OPENMRS_ADMIN_PASSWORD"] = "admin"
        self.assertEqual(validate_deployment_config(values), "development")

    def test_unique_production_configuration_is_accepted(self) -> None:
        self.assertEqual(validate_deployment_config(valid_environment()), "production")

    def test_server_refuses_to_bind_before_configuration_is_valid(self) -> None:
        with (
            patch.dict("os.environ", {}, clear=True),
            patch.object(server, "ThreadingHTTPServer") as http_server,
        ):
            with self.assertRaises(ConfigurationError):
                server.main()
        http_server.assert_not_called()


if __name__ == "__main__":
    unittest.main()
