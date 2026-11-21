#!/usr/bin/env python3
"""6A05 auxiliary CI dependency: selftools package import remains usable."""
import unittest

import selftools


class SelftoolsCompatTests(unittest.TestCase):
    def test_package_import_and_one_registry(self):
        self.assertEqual(len(selftools.MODULES), 30)
        first = selftools.build_registry()
        second = selftools.build_registry()
        self.assertIs(first, second)
        names = {item["name"] for item in first.describe()}
        self.assertEqual(len(names), 30)
        self.assertIn("repo_read", names)
        self.assertIn("health_probe", names)


if __name__ == "__main__":
    unittest.main()
