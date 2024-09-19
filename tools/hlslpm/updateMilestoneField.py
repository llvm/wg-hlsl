# Makes sure that the ProjectMilestone fields are set correctly
from argparse import ArgumentParser
from typing import Dict

import github
from issue import Issues

def updateMilestoneField_addArgs(subparsers):
    parser: ArgumentParser = subparsers.add_parser(
        'update-milestone-field', aliases=['umf'])

    group = parser.add_mutually_exclusive_group()
    group.add_argument('--commit', action='store_true',
                       help='Commit changes to the github issues')
    parser.set_defaults(func=updateMilestoneField)

def updateMilestoneField(args):
    print("Fetching data...")
    gh = github.GH();
    issues = Issues(gh)
    
    # key: issue (id) we've seen
    # value: the milestone issue (id) associated with it
    seen:Dict[str, str] = dict()

    all = issues.all_issues_by_id

    def recursivelySetProjectMilestone(issue_id: str, milestoneIssue_id: str):
        issue = all[issue_id]
        milestoneIssue = all[milestoneIssue_id]

        if issue_id in seen:        
            seenIssue = all[seen[issue_id]]
            print(f"WARNING: {issue.getIssueReference()} seen under both {milestoneIssue.getIssueReference()} and {seenIssue.getIssueReference()}")
            return

        seen[issue_id] = milestoneIssue_id
        if issue.projectMilestone != milestoneIssue.projectMilestone:
            print(f"{issue.getIssueReference()}: {issue.projectMilestone} --> {milestoneIssue.projectMilestone}")
            issue.projectMilestone = milestoneIssue.projectMilestone
            if args.commit:
                gh.set_project_milestone(issue.item_id, issue.projectMilestone)

        for child in issue.tracked_issues:
            recursivelySetProjectMilestone(child.issue_id, milestoneIssue_id)



    for i in issues.milestones:
        recursivelySetProjectMilestone(i.issue_id, i.issue_id)

