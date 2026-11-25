import unittest
from unittest import mock

import support  # noqa: F401  (sys.path)
from omi_hub.application import pipeline, release, setup
from omi_hub.domain.errors import RuleError
from omi_hub.domain.release import po_approved

CFG = {"owner": "o", "repo": "r", "default_branch": "develop", "main_branch": "main", "po": "boss"}


class FakeGh:
    GhError = Exception

    def __init__(self, default="main", ruleset_err=None):
        self.calls, self.default, self.ruleset_err = [], default, ruleset_err
        self.open_pr, self.commits, self.reviews, self.auto_fails = None, ["feat: a (#1)"], [], False
        self.branches, self.locked, self.codeowners_err = {"main", "develop"}, set(), None

    def branch_exists(self, cfg, name):
        return name in self.branches

    def ensure_codeowners(self, cfg, branch, po):
        if branch in self.locked:  # ruleset chặn push thẳng
            raise self.GhError("Repository rule violations found")
        if self.codeowners_err:
            raise self.GhError(self.codeowners_err)
        self.calls.append(("ensure_codeowners", (branch, po), {}))

    def default_branch(self, owner, repo):
        return self.default

    def __getattr__(self, name):  # ghi lại mọi lời gọi ghi
        return lambda *a, **k: self.calls.append((name, a[1:], k))

    def ensure_ruleset(self, cfg, branch):
        self.calls.append(("ensure_ruleset", (branch,), {}))
        return self.ruleset_err

    def open_pr_for_branch(self, cfg, head):
        return self.open_pr

    def compare_commits(self, cfg, base, head):
        return self.commits

    def pr_reviews(self, cfg, pr):
        return self.reviews

    def create_pr(self, cfg, title, body, head, base=None, reviewer=None):
        self.calls.append(("create_pr", (title, head), {"base": base, "reviewer": reviewer}))
        return 9

    def merge_pr(self, cfg, pr, release=False, auto=False):
        if auto and self.auto_fails:
            raise self.GhError("auto-merge not allowed")
        self.calls.append(("merge_pr", (pr,), {"release": release, "auto": auto}))


class TestReleaseFlow(unittest.TestCase):
    def run_flow(self, g, old=None):
        cfg = {"owner": "o", "repo": "r"}
        with mock.patch.object(setup, "gh", g):
            err = setup.release_flow(cfg, "boss", old or {})
        return cfg, err

    def test_ac70_1_init_sets_up_develop_codeowners_ruleset(self):
        g = FakeGh(default="master")
        _, warns = self.run_flow(g)
        self.assertEqual(warns, [])
        self.assertEqual([c[0] for c in g.calls],
                         ["ensure_codeowners", "ensure_branch", "set_default_branch", "ensure_ruleset"])
        self.assertEqual(g.calls[0][1], ("master", "boss"))  # CODEOWNERS lên nhánh chính, trước ruleset
        self.assertEqual(g.calls[1][1], ("develop", "master"))
        self.assertEqual(g.calls[3][1], ("master",))

    def test_ac70_1_ruleset_unsupported_warns_not_fails(self):
        _, warns = self.run_flow(FakeGh(ruleset_err="Upgrade to GitHub Pro"))
        self.assertEqual(len(warns), 1)
        self.assertIn("Upgrade to GitHub Pro", warns[0])

    def test_ac70_1_po_change_after_ruleset_goes_via_develop(self):
        g = FakeGh(default="develop")
        g.locked = {"main"}
        cfg, warns = self.run_flow(g, {"main_branch": "main"})
        self.assertIn(("ensure_codeowners", ("develop", "boss"), {}), g.calls)
        self.assertNotIn(("ensure_codeowners", ("main", "boss"), {}), g.calls)
        self.assertEqual(len(warns), 1)
        self.assertEqual(cfg["po"], "boss")

    def test_ac70_2_config_targets_develop(self):
        cfg, _ = self.run_flow(FakeGh())
        self.assertEqual((cfg["default_branch"], cfg["main_branch"], cfg["po"]), ("develop", "main", "boss"))

    def test_ac70_2_rerun_keeps_main_branch(self):
        cfg, _ = self.run_flow(FakeGh(default="develop"), {"main_branch": "master"})
        self.assertEqual(cfg["main_branch"], "master")

    def test_ac70_1_other_codeowners_error_not_hidden(self):
        g = FakeGh()
        g.codeowners_err = "HTTP 403: Resource not accessible by integration"
        with self.assertRaises(Exception) as ctx:
            self.run_flow(g)
        self.assertIn("403", str(ctx.exception))
        self.assertEqual(g.calls, [])  # không rẽ sang develop

    def test_ac70_2_lost_config_finds_master(self):
        g = FakeGh(default="develop")
        g.branches = {"develop", "master"}
        cfg, _ = self.run_flow(g)
        self.assertEqual(cfg["main_branch"], "master")
        g.branches = {"develop"}
        with self.assertRaises(RuleError):
            self.run_flow(g)

    def test_ac70_2_init_requires_po(self):
        with mock.patch.object(setup, "CONFIG", mock.Mock(exists=lambda: False)):
            with self.assertRaises(RuleError):
                setup.init({}, po=None)


class TestPrLint(unittest.TestCase):
    def lint(self, head, cfg):
        g = FakeGh()
        g.pr_view = lambda c, pr: ("Release", "no template", head)
        with mock.patch.object(pipeline, "gh", g):
            return pipeline.pr_lint(cfg, 9)

    def test_ac70_3_release_pr_skips_template(self):
        self.assertEqual(self.lint("develop", CFG), 0)
        self.assertEqual(self.lint("feature-x", CFG), 1)  # PR task vẫn bị kiểm
        self.assertEqual(self.lint("develop", {"default_branch": "develop"}), 1)  # chưa bật release


class TestRelease(unittest.TestCase):
    def run_release(self, g, merge=False):
        with mock.patch.object(release, "gh", g):
            return release.release(dict(CFG), merge)

    def test_ac70_3_creates_pr_with_po_review(self):
        g = FakeGh()
        self.assertEqual(self.run_release(g), 0)
        name, (title, head), kw = g.calls[0]
        self.assertEqual((name, head, kw), ("create_pr", "develop", {"base": "main", "reviewer": "boss"}))
        self.assertTrue(title.startswith("[Release] develop → main"))
        self.assertEqual(g.calls[1], ("merge_pr", (9,), {"release": True, "auto": True}))

    def test_ac70_3_reuses_open_pr_and_survives_no_auto_merge(self):
        g = FakeGh()
        g.open_pr = 5
        self.run_release(g)
        self.assertEqual(g.calls, [])
        g2 = FakeGh()
        g2.auto_fails = True
        self.assertEqual(self.run_release(g2), 0)

    def test_ac70_3_nothing_to_release(self):
        g = FakeGh()
        g.commits = []
        self.assertEqual(self.run_release(g), 0)
        self.assertEqual(g.calls, [])

    def test_ac70_4_merge_only_when_po_approved(self):
        g = FakeGh()
        g.open_pr = 5
        g.reviews = [{"author": "dev", "state": "APPROVED"}]
        self.assertEqual(self.run_release(g, merge=True), 1)
        self.assertEqual(g.calls, [])
        g.reviews.append({"author": "Boss", "state": "APPROVED"})
        self.assertEqual(self.run_release(g, merge=True), 0)
        self.assertEqual(g.calls, [("merge_pr", (5,), {"release": True, "auto": False})])

    def test_ac70_4_latest_po_verdict_wins(self):
        approve, reject = {"author": "boss", "state": "APPROVED"}, {"author": "boss", "state": "CHANGES_REQUESTED"}
        comment = {"author": "boss", "state": "COMMENTED"}
        self.assertFalse(po_approved([approve, reject], "boss"))
        self.assertTrue(po_approved([reject, approve, comment], "boss"))
        self.assertFalse(po_approved([], "boss"))

    def test_ac70_4_requires_release_config(self):
        with mock.patch.object(release, "gh", FakeGh()), self.assertRaises(RuleError):
            release.release({"default_branch": "main"})


if __name__ == "__main__":
    unittest.main()
