"""Static guards against reintroducing backend credentials into source/browser config."""

from __future__ import annotations

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PASSWORD_DEFAULT = re.compile(
    r'os\.environ\.get\(\s*["\'][A-Z0-9_]*(?:PASSWORD|SECRET|TOKEN|KEY)'
    r'["\']\s*,\s*["\'][^"\']+["\']\s*\)'
)
FRONTEND_SECRET = re.compile(r"VITE_[A-Z0-9_]*(?:PASSWORD|SECRET|TOKEN|PRIVATE_KEY)")
HARDCODED_BASIC_IDENTITY = re.compile(
    r'(?:AUTH\s*=\s*["\'][^"\']+:[^"\']+["\']|basic\(["\'][^"\']+["\']\))'
)


class DeploymentSecretSourceTests(unittest.TestCase):
    def test_python_sources_have_no_password_environment_fallbacks(self) -> None:
        offenders: list[str] = []
        for directory in (ROOT / "scripts", ROOT / "server" / "patient-account"):
            for path in directory.glob("*.py"):
                if PASSWORD_DEFAULT.search(path.read_text()):
                    offenders.append(str(path.relative_to(ROOT)))
        self.assertEqual(offenders, [])

    def test_scripts_have_no_hardcoded_basic_auth_identity(self) -> None:
        offenders = [
            str(path.relative_to(ROOT))
            for path in (ROOT / "scripts").glob("*.py")
            if HARDCODED_BASIC_IDENTITY.search(path.read_text())
        ]
        self.assertEqual(offenders, [])

    def test_frontend_has_no_browser_exposed_backend_secret_names(self) -> None:
        offenders: list[str] = []
        for path in (ROOT / "src").rglob("*"):
            if path.suffix in {".ts", ".tsx", ".js", ".jsx"} and FRONTEND_SECRET.search(
                path.read_text()
            ):
                offenders.append(str(path.relative_to(ROOT)))
        self.assertEqual(offenders, [])


if __name__ == "__main__":
    unittest.main()
