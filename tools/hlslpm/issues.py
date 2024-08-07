from typing import Dict

from issue import Category, Issue


class Issues:
    all_issues: Dict[str, Issue]
    milestones: Dict[str, Issue]
    workstreams: Dict[str, Issue]

    def __init__(self, gh):
        def is_interesting(i: Issue):
            return i.category in [Category.ProjectMilestone, Category.Workstream]

        self.all_issues = dict([(i.issue_resourcePath, i)
                               for i in gh.project_items_summary()])

        interesting = [i for i in self.all_issues.values()
                       if is_interesting(i)]
        interesting = [i for i in gh.get_issues(interesting)]

        self.milestones = dict([
            (i.issue_resourcePath, i) for i in interesting if i.category == Category.ProjectMilestone])
        self.workstreams = dict([
            (i.issue_resourcePath, i) for i in interesting if i.category == Category.Workstream])
