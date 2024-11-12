# Makes sure that the ProjectMilestone fields are set correctly
from argparse import ArgumentParser
import itertools
from typing import Dict, List, Set

import github
from issue import Category, Issue, Issues


def updateMilestoneField_addArgs(subparsers):
    parser: ArgumentParser = subparsers.add_parser(
        'update-milestone-field', aliases=['umf'])

    group = parser.add_mutually_exclusive_group()
    group.add_argument('--commit', action='store_true',
                       help='Commit changes to the github issues')
    parser.set_defaults(func=updateMilestoneField)


def updateMilestoneField(args):
    print("Fetching data...")
    gh = github.GH()
    issues = Issues(gh)

    seen: Set[str] = set()
    multipleParents: Set[str] = set()

    all = issues.all_issues_by_id

    def recursivelySetProjectMilestone(issue_id: str, milestoneIssue_id: str):
        if issue_id in seen:
            multipleParents.add(issue_id)
            return
        seen.add(issue_id)

        issue = all[issue_id]
        milestoneIssue = all[milestoneIssue_id]

        if issue.projectMilestone != milestoneIssue.projectMilestone:
            print(f"https://github.com{issue.issue_resourcePath}: {
                  issue.projectMilestone} --> {milestoneIssue.projectMilestone}")
            issue.projectMilestone = milestoneIssue.projectMilestone
            if args.commit:
                gh.set_project_milestone(issue.item_id, issue.projectMilestone)

        for child in issue.tracked_issues:
            recursivelySetProjectMilestone(child.issue_id, milestoneIssue_id)

    for i in issues.milestones:
        recursivelySetProjectMilestone(i.issue_id, i.issue_id)

    for i in multipleParents:
        reportMultipleParents(issues, i)


def reportMultipleParents(issues: Issues, issue_id):
    issue = issues.all_issues_by_id[issue_id]

    print(f"{issue.getIssueReference()} {
          issue.title} - is in multiple milestones:")

    def findPathsToMilestone(path: List[Issue], paths: List[Issue]):
        if path[-1].category == Category.ProjectMilestone:
            paths.append(path)
            return

        for i in path[-1].tracked_by_issues:
            findPathsToMilestone(path + [i], paths)

    paths:List[List[Issue]] = []
    findPathsToMilestone([issue], paths)

    for p in paths:
        p.reverse()
        print(f"    {" -> ".join([i.getIssueReference() for i in p])}")
    print("")


if __name__ == "__main__":
    class Args:
        commit = False
    updateMilestoneField(Args())
