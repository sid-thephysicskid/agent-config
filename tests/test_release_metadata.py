#!/usr/bin/env python3
"""Package metadata and the publish workflow agree."""
import json
import os
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def read(*parts):
    with open(os.path.join(ROOT, *parts)) as fh:
        return fh.read()


class ReleaseMetadataTest(unittest.TestCase):
    def setUp(self):
        self.version = read("VERSION").strip()
        self.package = json.loads(read("package.json"))

    def test_versions_match(self):
        self.assertEqual(self.package["version"], self.version)
        self.assertEqual(self.package["name"], "@sid-thephysicskid/agent-config")
        self.assertEqual(self.package["publishConfig"]["access"], "public")

    def test_changelog_has_current_version(self):
        self.assertIn("## [%s]" % self.version, read("CHANGELOG.md"))

    def test_packaged_paths_exist(self):
        for entry in self.package["files"]:
            if not entry.startswith("!"):
                self.assertTrue(os.path.exists(os.path.join(ROOT, entry)), entry)

    def test_publish_uses_trusted_publishing(self):
        # Comments are stripped so an explanation cannot satisfy an assertion.
        workflow = "\n".join(line.split("#")[0] for line in
                             read(".github", "workflows", "publish.yml").splitlines())
        for needed in ("types: [published]", "id-token: write", "GITHUB_REF_NAME",
                       "./scripts/gates --full", "npm publish"):
            self.assertIn(needed, workflow)
        for forbidden in ("NODE_AUTH_TOKEN", "NPM_TOKEN"):
            self.assertNotIn(forbidden, workflow)


if __name__ == "__main__":
    unittest.main(verbosity=2)
