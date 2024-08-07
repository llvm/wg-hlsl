from typing import List
import unittest
from issue import Category, Issue, parse_data, IssueData
from issues import Issues


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

        test_issues = [(1, Category.ProjectMilestone, "[milestone] The First Milestone", ["About the milestone.", "## Workstreams",
                        "### WorkstreamA (#2)", "foo", "bar", "### Workstream B(#3)", "com", "baz"]),
                       (2, Category.Workstream, "[workstream] Super fast workstream",
                        ["About the workstream.", "## Milestones", "### Milestone 1 (#1)", "- [ ] item1", "- [ ] item2"]),
                       (3, Category.Workstream, "[workstream] Super slow workstream",
                        ["Taking it easy.", "## Milestones", "### Milestone 1 (#1)", "- [ ] item3"])]

        test_issues = [Issue(issue_id=f"id{id}",
                             issue_resourcePath=f"test/{id}",
                             category=category,
                             title=title,
                             body="\n".join(body)) for (id, category, title, body) in test_issues]

        self.test_issues = dict([(i.issue_id, i) for i in test_issues])

        class GH:
            def __init__(self, issues):
                self.issues = issues

            def project_items_summary(self):
                for i in self.issues:
                    yield i

            def get_issues(self, issues):
                for i in issues:
                    yield i

        gh = GH(list(self.test_issues.values()))

        self.issues = Issues(gh)

    def test_MilestoneAndWorkstreamsIdentified(self):
        self.assertEqual(set(["test/1"]), self.issues.milestones.keys())
        self.assertEqual(set(["test/2", "test/3"]), self.issues.workstreams.keys())


if __name__ == '__main__':
    unittest.main()
