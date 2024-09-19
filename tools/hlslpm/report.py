from argparse import ArgumentParser
import itertools
import os
from typing import Callable, Iterable, List, Optional, Set
import github
from issue import Issue, IssueState, Issues
import mdformat


def report_addArgs(subparsers):
    parser: ArgumentParser = subparsers.add_parser(
        'report', aliases=['r'], help="Generate output/report-*.md")
    parser.set_defaults(func=report)


def report(args):
    print("Fetching data...")
    gh = github.GH()
    issues = Issues(gh)

    print("Analyzing...")

    r = Reporter(gh, issues)

    write_report(r.generateWorkstreamsReport(), "output/report-workstreams.md")
    write_report(r.generateMilestonesReport(), "output/report-milestones.md")
    write_report(r.generateWarningsReport(), "output/report-warnings.md")


def write_report(lines, filename):
    output = mdformat.text("\n".join(lines))

    filename = os.path.normpath(filename)
    print(f"Writing {filename}...")

    os.makedirs(os.path.dirname(filename), exist_ok=True)
    with open(filename, 'w', encoding='utf-8') as f:
        f.write(output)


class Reporter:
    gh: github.GH
    issues: Issues

    def __init__(self, gh, issues):
        self.gh = gh
        self.issues = issues

    def generateWorkstreamsReport(self) -> Iterable[str]:
        return itertools.chain(*[self.generateWorkstreamReport(w) for w in self.issues.workstreams])

    def generateMilestonesReport(self) -> Iterable[str]:
        return itertools.chain(*[self.generateMilestoneReport(w) for w in self.issues.milestones])

    def generateWarningsReport(self) -> Iterable[str]:
        return itertools.chain(*[self.generateWorkstreamWarningsReport(w) for w in self.issues.workstreams])

    def generateWorkstreamReport(self, workstreamIssue: Issue) -> Iterable[str]:
        lines = []

        lines.append(f"# {issue_link(workstreamIssue)}")

        lines += self.generateTrackedIssueList(workstreamIssue)

        return lines

    def generateWorkstreamWarningsReport(self, workstreamIssue: Issue) -> Iterable[str]:
        lines = self.generateWorkstreamMismatchReport(
            workstreamIssue) + self.generateUnlinkedWorkstreamReport(workstreamIssue)
        if len(lines) > 0:
            lines = [f"# {issue_link(workstreamIssue)}"] + lines

        return lines

    def generateMilestoneReport(self, milestoneIssue: Issue) -> Iterable[str]:
        lines = []
        lines.append(f"# {issue_link(milestoneIssue)}")
        lines += self.generateTrackedIssueList(milestoneIssue)
        return lines

    def generateTrackedIssueList(self, startIssue: Issue) -> Iterable[str]:

        lines = []

        def visit(issue: Issue, depth: int, seen: bool):
            # skip the top level
            if depth == 0:
                return

            indent = "  " * (depth-1)

            issueText = issue_link(issue, startIssue)

            lines.append(f"{indent} * {issueText}")

            if seen:
                lines.append(f"{indent}   * (see above)")

        visit_all(startIssue, visit)

        return lines

    def generateWorkstreamMismatchReport(self, workstreamIssue: Issue) -> Iterable[str]:

        mismatched_issues = []

        def visit(issue: Issue, depth: int, seen: bool):
            if seen:
                return

            if issue.workstream != workstreamIssue.workstream:
                mismatched_issues.append(issue)

        visit_all(workstreamIssue, visit)

        if len(mismatched_issues) == 0:
            return []

        lines = ["## Workstream Field Mismatches",
                 "These issues are linked to the main workstream issue, but don't have",
                 f"their workstream field set to '{workstreamIssue.workstream}'"]
        lines += ["|Issue|Workstream|", "|--|--|"]
        for issue in mismatched_issues:
            lines.append(f"| {issue_link(issue)} | {issue.workstream}")

        return lines

    def generateUnlinkedWorkstreamReport(self, workstreamIssue: Issue) -> Iterable[str]:
        linked_issues = []

        def visit(issue: Issue, depth: int, seen: bool):
            if not seen:
                linked_issues.append(issue.issue_id)

        visit_all(workstreamIssue, visit)

        workstreamIssues = [i.issue_id for i
                            in self.issues.all_issues.values()
                            if i.workstream == workstreamIssue.workstream
                            ]

        unlinked = set(workstreamIssues).difference(set(linked_issues))

        if len(unlinked) == 0:
            return []

        lines = ["## Unlinked workstream issues",
                 f"These issues have the workstream field set to '{
                     workstreamIssue.workstream}'",
                 "but are not linked to the workstream issue itself."]
        for i in unlinked:
            lines.append(f"* {issue_link(self.issues.all_issues_by_id[i])}")

        return lines


def visit_all(issue: Issue, visitor: Callable[[Issue, int, bool], None]):
    seen: Set[str] = set()

    def visit_worker(issue: Issue, depth):
        if issue.issue_id in seen:
            visitor(issue, depth, True)
            return

        seen.add(issue.issue_id)

        visitor(issue, depth, False)

        def state_key(issue: Issue):
            return issue.issue_state.name

        for i in sorted(issue.tracked_issues, key=state_key, reverse=True):
            visit_worker(i, depth + 1)

    visit_worker(issue, 0)


def issue_link(issue: Issue, contextIssue: Optional[Issue] = None) -> str:
    if not contextIssue:
        contextIssue = issue

    issueText = f"{issue.title} ([{issue.getIssueReference(
        contextIssue)}](https://github.com{issue.issue_resourcePath}))"

    if issue.issue_state == IssueState.Closed:
        issueText = f"✅{issueText}"
    else:
        issueText = f"🟦{issueText}"

    return issueText
