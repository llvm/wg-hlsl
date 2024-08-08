import sys
import argparse
import os
from typing import List
from issue import Issue, Issues
import github


def saveIssues(basePath, issues:List[Issue]):
    for issue in issues:
        filename = os.path.normpath(os.path.join(basePath, issue.issue_resourcePath.strip("/")))
        os.makedirs(os.path.dirname(filename), exist_ok=True)

        with open(filename, 'w') as f:
            f.write(issue.body)


if __name__ == '__main__':

    parser = argparse.ArgumentParser(description="HLSL Project Manager")
    parser.add_argument('--save', action='store_true', help="Saves before/after issues")
    parser.add_argument('--update', action='store_true', help="Update github issues")

    args = parser.parse_args()

    if args.save and args.update:
        print("Only one of --preview or --update can be specified")
    

    print("Fetching data...")
    gh = github.GH()
    issues = Issues(gh)


    tracked = list(issues.milestones.values()) + list(issues.workstreams.values())

    bodyBefore = dict([(i.issue_id, i.body) for i in tracked])

    if args.save:
        print(f"Saving {len(tracked)} issues before updating...")
        saveIssues("output/before", tracked)

    print(f"Updating...")
    for issue in tracked:
        issue.update(issues)

    bodyAfter = dict([(i.issue_id, i.body) for i in tracked])

    if args.save:
        print(f"Saving {len(tracked)} issues after updating...")
        saveIssues("output/after", tracked)

    for id in bodyBefore.keys():
        if bodyBefore[id] != bodyAfter[id]:
            print(f"{id} changed!")

            if args.update:
                gh.set_issue_body(id, bodyAfter[id])
        




