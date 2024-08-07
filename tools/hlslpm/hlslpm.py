from typing import Dict, List
import github
from issue import Category, Issue


class Issues:
    all_issues: Dict[str, Issue]
    milestones: Dict[str, Issue]
    workstreams: Dict[str, Issue]

    def __init__(self):
        self.milestones = []
        self.workstreams = []

        gh = github.GH()

        def is_interesting(i: Issue):
            return i.category in [Category.ProjectMilestone, Category.Workstream]
        
        self.all_issues = dict([(i.issue_resourcePath, i) for i in github.project_items_summary(gh)])

        interesting = [i for i in self.all_issues.values() if is_interesting(i)]
        interesting = [i for i in github.get_issues(gh, interesting)]

        self.milestones = [i for i in interesting if i.category == Category.ProjectMilestone]
        self.workstreams = [i for i in interesting if i.category == Category.Workstream]



if __name__ == '__main__':
    issues = Issues(123)

    print(issues.milestones)
    print(issues.workstreams)