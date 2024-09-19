# Main entry point for tool that mangages the HLSL Project on llvm.

from argparse import ArgumentParser
import os
from typing import List
from issue import Issue, Issues
import github
from updateMilestoneField import updateMilestoneField_addArgs


def saveIssues(basePath, issues: List[Issue]):
    for issue in issues:
        filename = os.path.normpath(os.path.join(
            basePath, issue.issue_resourcePath.strip("/")))
        os.makedirs(os.path.dirname(filename), exist_ok=True)

        with open(filename, 'w') as f:
            f.write(issue.body)


def updateIssues_addArgs(subparsers):
    parser: ArgumentParser = subparsers.add_parser(
        'update-issues', aliases=['ui'])

    group = parser.add_mutually_exclusive_group()
    group.add_argument('--save', action='store_true',
                       help="Saves before/after issues")
    group.add_argument('--commit', action='store_true',
                       help="Commit changes to the github issues")
    parser.set_defaults(func=updateIssues)


def updateIssues(args):
    print("Fetching data...")
    gh = github.GH()
    issues = Issues(gh)

    tracked = issues.milestones + issues.workstreams

    bodyBefore = dict([(i.issue_id, i.body) for i in tracked])

    if args.save:
        print(f"Saving {len(tracked)} issues before updating...")
        saveIssues("output/before", tracked)

    print(f"Processing...")
    for issue in tracked:
        issue.update(issues)

    bodyAfter = dict([(i.issue_id, i.body) for i in tracked])

    if args.save:
        print(f"Saving {len(tracked)} issues after updating...")
        saveIssues("output/after", tracked)

    for id in bodyBefore.keys():
        if bodyBefore[id] != bodyAfter[id]:
            print(
                f"{issues.all_issues_by_id[id].getIssueReference()} body changed!")

            if args.commit:
                gh.set_issue_body(id, bodyAfter[id])



if __name__ == '__main__':

    parser = ArgumentParser(description="HLSL Project Manager")

    subparsers = parser.add_subparsers(
        required=True, title="subcommands", description="valid subcommands", help="additional help")
    updateIssues_addArgs(subparsers)
    updateMilestoneField_addArgs(subparsers)

    args = parser.parse_args()

    args.func(args)
