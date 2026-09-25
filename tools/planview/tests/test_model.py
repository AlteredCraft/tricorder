import unittest
from pathlib import Path

from planview.model import load, parse_entry, slug, status_key

from .fixture import make_tree

REPO_PLANNING = Path(__file__).resolve().parents[3] / "planning"


class StatusTest(unittest.TestCase):
    def test_status_key(self):
        self.assertEqual(status_key("In progress"), "in-progress")
        self.assertEqual(status_key("Partial (user-approved 2026-09-24)"), "partial")
        self.assertEqual(status_key("Dropped (no longer needed)"), "dropped")
        self.assertEqual(status_key("Revoked by ADR-0009 (2026-01-01): reason"), "revoked")
        self.assertEqual(status_key("???"), "unknown")

    def test_slug_matches_github(self):
        self.assertEqual(slug("M-0001: Validate the handheld investigation"), "m-0001-validate-the-handheld-investigation")
        self.assertEqual(slug("Open"), "open")


class ResolveTest(unittest.TestCase):
    def test_root_relative_links_resolve_against_base(self):
        from planview.model import resolve
        self.assertEqual(resolve("/README.md#x", "planning/plans/a.md", Path("/repo")).path, "README.md")
        self.assertEqual(resolve("/../etc/passwd", "planning/a.md", Path("/repo")).path, None)
        self.assertEqual(resolve("../../../etc/passwd", "planning/a.md", Path("/repo")).path, None)


class EntryTest(unittest.TestCase):
    def test_tags_commits_adrs(self):
        e = parse_entry("- 2026-09-21 — [C2 pass] [C3 pass] Loops. Evidence: `20260921-dev` · `7bd5211`, `fbf930d`. → ADR-0010")
        self.assertEqual(e.date, "2026-09-21")
        self.assertEqual(e.tags, [(2, "pass"), (3, "pass")])
        self.assertEqual(e.commits, ["7bd5211", "fbf930d"])
        self.assertEqual(e.adrs, ["ADR-0010"])
        self.assertFalse(e.superseded)

    def test_run_names_are_not_commits(self):
        e = parse_entry("- 2026-09-21 — [C1] Note. Evidence: `20260921` · #45.")
        self.assertEqual(e.commits, [])
        self.assertEqual(e.prs, ["45"])
        self.assertEqual(e.tags, [(1, "")])


class LoadTest(unittest.TestCase):
    def setUp(self):
        self.tmp, self.base = make_tree()
        self.plan = load(self.base / "planning")

    def tearDown(self):
        self.tmp.cleanup()

    def test_hierarchy(self):
        (ms,) = self.plan.milestones
        self.assertEqual((ms.id, ms.title, ms.key), ("M-0001", "Ship the thing", "in-progress"))
        self.assertEqual(ms.active_spec, "planning/plans/G-0001.01-first.md")
        (goal,) = self.plan.goals_for(ms)
        self.assertEqual(goal.id, "G-0001")
        self.assertEqual([s.id for s in self.plan.specs_for(goal)], ["G-0001.01", "G-0001.02"])
        spec = self.plan.by_id("G-0001.01")
        self.assertIs(self.plan.parent_of(spec), goal)
        self.assertIs(self.plan.milestone_of(spec), ms)
        self.assertEqual([s.title for s in self.plan.sections], ["Later"])

    def test_spec_fields(self):
        spec = self.plan.by_id("G-0001.01")
        self.assertEqual(spec.kind, "spec")
        self.assertEqual(spec.goal_id, "G-0001")
        self.assertEqual(spec.adr_ids, ["ADR-0001"])
        self.assertEqual(spec.revisions, ["2026-01-02: tightened check 2."])
        self.assertEqual([(c.number, c.verdict) for c in spec.checks], [(1, "pass"), (2, "open"), (3, "fail")])
        self.assertEqual(spec.checks[1].text, "Three runs at speed.")
        self.assertEqual(len(spec.observed), 4)
        self.assertTrue(spec.observed[2].superseded)
        self.assertEqual([o.needs_user for o in spec.open_items], [False, True])

    def test_kinds(self):
        kinds = {d.path.split("/")[-1]: d.kind for d in self.plan.docs.values()}
        self.assertEqual(kinds["ADR-template.md"], "template")
        self.assertEqual(kinds["protocol.md"], "reference")
        self.assertEqual(kinds["ADR-0001-choice.md"], "adr")
        self.assertEqual(kinds["milestones.md"], "milestones")

    def test_backlinks(self):
        adr = self.plan.by_id("ADR-0001")
        self.assertIn("planning/plans/G-0001.01-first.md", self.plan.backlinks[adr.path])

    def test_entries_newest_first(self):
        self.assertEqual([e.date for e in self.plan.entries()], ["2026-01-04", "2026-01-03", "2026-01-02", "2026-01-01"])

    def test_lint(self):
        messages = "\n".join(f"{i.level} {i.message}" for i in self.plan.issues)
        self.assertIn("G-0001 table says G-0001.02 is 'Partial'; its header says 'Confirmed'", messages)
        self.assertIn("G-0009 isn't listed by any milestone", messages)
        self.assertIn("G-0001.02 is confirmed but still has 1 Open item(s)", messages)
        self.assertIn("G-0001.02 is Confirmed but not every check is [pass]", messages)
        self.assertIn("G-0001.01 entry 2026-01-04 cites no commit or PR", messages)
        self.assertIn("broken link to nope.md", messages)
        self.assertNotIn("entry 2026-01-03 cites no commit", messages)  # a PR counts
        self.assertNotIn("ADR-template", messages)


@unittest.skipUnless((REPO_PLANNING / "milestones.md").exists(), "not inside the tricorder repo")
class RepoPlanningTest(unittest.TestCase):
    """The real planning dir parses into a connected tree without errors."""

    def test_real_planning(self):
        plan = load(REPO_PLANNING)
        self.assertTrue(plan.milestones)
        for ms in plan.milestones:
            self.assertTrue(plan.goals_for(ms))
        self.assertTrue(all(s.checks for s in plan.of_kind("spec")))
        self.assertFalse([i for i in plan.issues if i.level == "error"])


if __name__ == "__main__":
    unittest.main()
