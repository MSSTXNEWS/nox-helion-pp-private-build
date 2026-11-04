"""T06 regression: P05 offline .NET smoke must not hide its Json declaration in a comment."""
import pathlib
import re
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
SMOKE = ROOT / "Packages/P05/Space/tests/Program.cs"
PROJECT = ROOT / "Packages/P05/Space/tests/SpaceFeedClientR16Smoke.csproj"


class P05SmokeSourceGate(unittest.TestCase):
    def test_json_fixture_is_executable_code_not_a_comment(self):
        source = SMOKE.read_text(encoding="utf-8")
        self.assertNotIn(r"\nvar Json", source)
        self.assertRegex(source, r"(?m)^var Json\s*=\s*JsonSerializer\.Serialize\(")
        self.assertIn("Encoding.UTF8.GetBytes(Json)", source)

    def test_project_compiles_actual_smoke_source(self):
        project = PROJECT.read_text(encoding="utf-8")
        self.assertIn("<TargetFramework>net8.0</TargetFramework>", project)
        self.assertIn('<Compile Include="Program.cs" />', project)
        self.assertIn('<Compile Include="../SpaceFeedClient.cs"', project)


if __name__ == "__main__":
    unittest.main()
