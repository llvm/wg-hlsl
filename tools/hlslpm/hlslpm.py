import os
from typing import List
import issue
from issue import Issue, Issues
import github


def saveIssues(basePath, issues:List[Issue]):
    for issue in issues:
        filename = os.path.normpath(os.path.join(basePath, issue.issue_resourcePath.strip("/")))
        os.makedirs(os.path.dirname(filename), exist_ok=True)

        with open(filename, 'w') as f:
            f.write(issue.body)


if __name__ == '__main__':
    print("Fetching data...")
    gh = github.GH()
    issues = Issues(gh)


    tracked = list(issues.milestones.values()) + list(issues.workstreams.values())

    print(f"Saving {len(tracked)} issues before updating...")
    saveIssues("output/before", tracked)

    print(f"Updating...")
    for issue in tracked:
        issue.update(issues)

    print(f"Saving {len(tracked)} issues after updating...")
    saveIssues("output/after", tracked)
    
        




