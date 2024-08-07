from typing import Dict, List
import github
from issue import Category, Issue


class Issues:
    all_issues: Dict[str, Issue]
    milestones: Dict[str, Issue]
    workstreams: Dict[str, Issue]

    def __init__(self, gh):
        self.milestones = []
        self.workstreams = []

        def is_interesting(i: Issue):
            return i.category in [Category.ProjectMilestone, Category.Workstream]

        self.all_issues = dict([(i.issue_resourcePath, i)
                               for i in gh.project_items_summary()])

        interesting = [i for i in self.all_issues.values()
                       if is_interesting(i)]
        interesting = [i for i in gh.get_issues(interesting)]

        self.milestones = [
            i for i in interesting if i.category == Category.ProjectMilestone]
        self.workstreams = [
            i for i in interesting if i.category == Category.Workstream]


if __name__ == '__main__':
    # issues = Issues(github.GH())

    def issue(i: int, category: Category, body: List[str]):
        newIssue = Issue(issue_id=f"id{i}")
        newIssue.category = category
        newIssue.issue_resourcePath = f"test/{i}"
        newIssue.body = "\n".join(body)
        return newIssue

    test_issues = [issue(1, Category.ProjectMilestone, ["## Workstreams", "### WorkstreamA (#2)"]),
                   issue(2, Category.Workstream, [
                         "## Milestones", "### Some Milestone (#1)", "foo"])
                   ]
    
    class GHStub:
        def project_items_summary(self):
            for i in test_issues:
                yield i

        def get_issues(self, issues):
            for i in issues:
                yield i

    issues = Issues(GHStub())

    print(issues.milestones)
    print(issues.workstreams)
