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
        self.assertEqual(
            set(targets),
            {
                "scripts/source_from_mail.py",
                "scripts/source_from_text.py",
                "scripts/payment_proposal.py",
            },
        )
        for target in targets:
            with self.subTest(target=target):
                actual = SKILL / target
                self.assertTrue(actual.is_file())
                self.assertFalse(actual.is_symlink())
        self.assertNotIn("python3 .tessl/", text)
        self.assertNotIn(
            "node /home/node/.claude/skills/tessl__construction-costs/scripts/construction-journal-callback",
            text,
        )

    def test_one_shot_declares_no_partial_or_hidden_cadence(self) -> None:
        text = (SKILL / "SKILL.md").read_text()
        frontmatter = text.split("---", 2)[1]
        self.assertNotRegex(frontmatter, r"(?m)^(?:cadence|script):")
        self.assertTrue((SKILL / "references/callback-contract.md").is_file())
