from datetime import date
from typing import Iterable, List
import unittest
from issue import Category, Issue, IssueSection, Issues, parse_data, IssueData


class Test_ParseData(unittest.TestCase):
    def test_empty(self):
        self.assertEqual(None, parse_data(None).type)
        self.assertEqual(None, parse_data([]).type)
        self.assertEqual(None, parse_data([""]).type)
        self.assertEqual(None, parse_data(
            ["sduhas fliuash filsaudhfslaiudfhsa"]).type)

        # These don't start with "##", so aren't recognized
        self.assertEqual(None, parse_data(["Milestones"]).type)
        self.assertEqual(None, parse_data(["Workstreams"]).type)

        # These aren't recognized
        self.assertEqual(None, parse_data(["## Flibble"]).type)

    def test_type(self):
        self.assertEqual("Milestones", parse_data(["## Milestones"]).type)
        self.assertEqual("Workstreams", parse_data(["## Workstreams"]).type)

        # allow some non-matches before a real one
        self.assertEqual("Workstreams", parse_data(
            ["foo", "## Bar", "## Workstreams"]).type)

        # only the first one counts
        self.assertEqual("Workstreams", parse_data(
            ["## Workstreams", "## Milestones"]).type)

    def test_sections(self):
        self.assertEqual([], parse_data(["## Milestones"]).sections)

        d = parse_data(["## Milestones", "### section header"])
        self.assertEqual(["section header"], [s.title for s in d.sections])

        d = parse_data(["## Milestones", "### section header",
                       "### another section header"])
        self.assertEqual(["section header", "another section header"], [
                         s.title for s in d.sections])

        d = parse_data(["## Milestones", "### section header",
                       "line 1", "line 2", "### another", "line 3"])
        self.assertEqual(["section header", "another"],
                         [s.title for s in d.sections])
        self.assertEqual(["line 1", "line 2"], d.sections[0].contents)
        self.assertEqual(["line 3"], d.sections[1].contents)

        # A dummy section is created for stuff before the first section header
        d = parse_data(["## Milestones", "line 1",
                       "line 2", "### another", "line 3"])
        self.assertEqual([None, "another"], [s.title for s in d.sections])
        self.assertEqual(["line 1", "line 2"], d.sections[0].contents)
        self.assertEqual(["line 3"], d.sections[1].contents)


class Test_Issues(unittest.TestCase):
    def setUp(self):

        test_issues = [(1, Category.ProjectMilestone, date(2024, 1, 1), "[milestone] The First Milestone", ["About the milestone.", "## Workstreams",
                        "### WorkstreamA (#2)", "foo", "bar", "### Workstream B(#3)", "com", "baz"]),
                       (2, Category.Workstream, None, "[workstream] Super fast workstream",
                        ["About the workstream.", "## Milestones", "### Milestone 1 (#1)", "- [ ] item1", "- [ ] item2"]),
                       (3, Category.Workstream, None, "[workstream] Super slow workstream",
                        ["Taking it easy.", "## Milestones", "### Milestone 1 (#1)", "- [ ] item3"]),
                       (4, Category.Workstream, None,
                        "[workstream] Empty workstream", ["Some stuff that isn't a milestone list"]),
                       (5, Category.Workstream, None, "[workstream] Unlisted Workstream", ["## Milestones", "### m1 (#1)", "- [ ] item5"])]

        test_issues = [Issue(issue_id=f"id{id}",
                             issue_resourcePath=f"test/issues/{id}",
                             category=category,
                             target_date=target,
                             title=title,
                             body="\n".join(body)) for (id, category, target, title, body) in test_issues]

        self.test_issues = dict([(i.issue_id, i) for i in test_issues])

        class GH:
            def __init__(self, issues):
                self.issues = issues

            def project_items_summary(self):
                for i in self.issues:
                    yield i

            def populate_issues_body(self, issues):
                pass

        gh = GH(list(self.test_issues.values()))

        self.issues = Issues(gh)

    def test_findIssue(self):
        issue1 = self.issues.all_issues["test/issues/1"]
        issue2 = self.issues.all_issues["test/issues/2"]

        self.assertEqual(issue1, self.issues.findIssue(issue2, "test#1"))
        self.assertEqual(issue1, self.issues.findIssue(issue2, "#1"))

    def test_getIssueReference(self):
        issue1 = self.issues.all_issues["test/issues/1"]
        issue2 = self.issues.all_issues["test/issues/2"]
        issue3 = Issue(issue_id="id100",
                       issue_resourcePath="foo/bar/issues/100")

        self.assertEqual("#1", issue1.getIssueReference(issue1))
        self.assertEqual("#1", issue1.getIssueReference(issue2))
        self.assertEqual("test#1", issue1.getIssueReference(issue3))

    def test_MilestoneAndWorkstreamsIdentified(self):
        self.assertEqual(set(
            ["test/issues/1"]), set([i.issue_resourcePath for i in self.issues.milestones]))
        self.assertEqual(set(["test/issues/2", "test/issues/3", "test/issues/4", "test/issues/5"]),
                         set([i.issue_resourcePath for i in self.issues.workstreams]))

    def test_UpdateMilestone(self):
        milestone = getByResourcePath(self.issues.milestones, "test/issues/1")
        self.assertEqual("test/issues/1", milestone.issue_resourcePath)

        milestone.update(self.issues)

        self.assertEqual(["About the milestone.", "## Workstreams",
                          "### Super fast workstream (#2)", "- [ ] item1", "- [ ] item2", "", "### Super slow workstream (#3)", "- [ ] item3", "",
                          "### Unlisted Workstream (#5)", "- [ ] item5"],
                         milestone.body.splitlines())

    def test_UpdateWorkstream(self):
        workstream = getByResourcePath(self.issues.workstreams, "test/issues/2")
        workstream.update(self.issues)

        self.assertEqual(["About the workstream.", "## Milestones", "### The First Milestone (#1)",
                         "- [ ] item1", "- [ ] item2"], workstream.body.splitlines())

    def test_UpdateEmptyWorkstream(self):
        issue = getByResourcePath(self.issues.workstreams, "test/issues/4")
        issue.update(self.issues)

        self.assertEqual(
            ["Some stuff that isn't a milestone list"], issue.body.splitlines())
        
def getByResourcePath(issues:Iterable[Issue], resourcePath: str):
    return next(i for i in issues if i.issue_resourcePath == resourcePath)


if __name__ == '__main__':
    unittest.main()
