"""Keep authored mounted commands bound to this provider's actual targets."""

from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills/construction-costs"


class SkillPathsTests(unittest.TestCase):
    def test_declared_plugin_and_all_mounted_commands_resolve(self) -> None:
        manifest = json.loads((ROOT / ".tessl-plugin/plugin.json").read_text())
        self.assertEqual(manifest["name"], "jbaruch/nanoclaw-construction")
        self.assertIn("skills/construction-costs", manifest["skills"])
        self.assertIn("rules/nanoclaw-skill-root.md", manifest["rules"])
        text = (SKILL / "SKILL.md").read_text()
        targets = re.findall(
            r"python3 /home/node/\.claude/skills/tessl__construction-costs/(scripts/[A-Za-z0-9_.-]+)",
            text,
        )
        self.assertEqual(set(targets), {"scripts/costs.py"})
        for target in targets:
            with self.subTest(target=target):
                actual = SKILL / target
                self.assertTrue(actual.is_file())
                self.assertFalse(actual.is_symlink())
        self.assertNotIn("python3 .tessl/", text)

    def test_one_shot_declares_no_partial_or_hidden_cadence(self) -> None:
        text = (SKILL / "SKILL.md").read_text()
        frontmatter = text.split("---", 2)[1]
        self.assertNotRegex(frontmatter, r"(?m)^(?:cadence|script):")

    def test_every_camera_command_resolves_and_the_cadence_is_complete(self) -> None:
        manifest = json.loads((ROOT / ".tessl-plugin/plugin.json").read_text())
        self.assertIn("skills/construction-site", manifest["skills"])
        site = ROOT / "skills/construction-site"
        text = (site / "SKILL.md").read_text()
        frontmatter = text.split("---", 2)[1]
        self.assertRegex(
            frontmatter, r'(?m)^cadence: "30 18 \* \* \* \(TZ=America/Chicago\)"$'
        )
        script = re.search(r'(?m)^script: "([^"]+)"$', frontmatter)
        assert script is not None
        self.assertTrue((site / script.group(1)).is_file())
        documents = text + (site / "references/reading-frames.md").read_text()
        targets = re.findall(
            r"python3 /home/node/\.claude/skills/tessl__construction-site/(scripts/[A-Za-z0-9_.-]+)",
            documents,
        )
        self.assertEqual(set(targets), {"scripts/frames.py"})
        self.assertTrue((site / "scripts/frames.py").is_file())
        for reference in re.findall(
            r"skills/construction-site/(references/[a-z-]+\.md)", text
        ):
            self.assertTrue((site / reference).is_file())
