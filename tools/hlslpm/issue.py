# Classes for dealing with issues, including aggregating and updating them.

from dataclasses import dataclass, field
from datetime import datetime, date
from enum import Enum
import re
from typing import Dict, List, Optional, Self, Union
import json

class Category(Enum):
    NoCategory = None
    Item = "Item"
    Deliverable = "Deliverable"
    Workstream = "Workstream"
    WorkstreamMilestone = "Workstream Milestone"
    ProjectMilestone = "Project Milestone"


class IssueSection:
    title: str = None
    contents: List[str]

    def __init__(self):
        self.contents = []    

    def getReferenceFromTitle(self):
        if not self.title:
            return None

        m = re.match(r".*\((.*#\d+)\)", self.title)
        if not m:
            return None
        
        return m[1]
    

class IssueData:
    type: str = None
    sections: List[IssueSection]

    def __init__(self):
        self.sections = []


@dataclass
class Issue:
    issue_id: str
    issue_resourcePath: Optional[str] = field(default=None)
    item_id: Optional[str] = field(default=None)
    item_updatedAt: Optional[datetime] = field(default=None)
    category: Optional[Category] = field(default=None)
    target_date: Optional[date] = field(default=None)
    issue_updatedAt: Optional[datetime] = field(default=None)
    title: Optional[str] = field(default=None)
    body: Optional[str] = field(default=None)

    def getResourcePathBase(self):
        m = re.match(r"(.*)/\d+", self.issue_resourcePath)
        if not m:
            return self.issue_resourcePath
        
        return m[1]

    def getIssueReference(self, contextIssue):
        contextBase = contextIssue.getResourcePathBase()
        selfBase = self.getResourcePathBase()

        if contextBase == selfBase:
            reference = self.issue_resourcePath[len(selfBase):]  
            return reference.replace("/", "#")
        else:
            m = re.match(r"(.*)/issues/(\d+)", self.issue_resourcePath)
            if not m:
                raise Exception(f"Unabled to parse issue resourcePath '{self.issue_resourcePath}'.")
            return f"{m[1]}#{m[2]}"

    
    def convertReferenceToResourcePath(self, reference):
        """
        Given a reference, in the context of this issue, convert it to a full
        resource path.
        """
        if not reference:
            return None
        
        m = re.match(r"(.+)#(\d+)", reference)
        if m:
            # If reference is full path we can translate it to a referencePath
            return f"{m[1]}/issues/{m[2]}"
        else:
            # Otherwise construct a full path given the context

            # remove the "#""
            m = re.match(r"#(\d+)", reference)
            if not m:
                return None
            reference = m[1]

            basePath = self.getResourcePathBase()
            return f"{basePath}/{reference}"


    def update(self, issues):
        if not self.body:
            return

        if self.category == Category.ProjectMilestone:
            self.updateMilestone(issues)
        elif self.category == Category.Workstream:
            self.updateWorkstream(issues)

    def updateMilestone(self, issues):
        """
        Milestones are expected to contain a list of workstreams, with the
        content that each workstream lists for this milestone. The workstream
        issue is authoritative for this content.

        ```
        text before the data

        ## Workstreams

        ### A workstream (#123)
        content

        ### Another workstream (#234)
        more content
        ----
        text after the data
        ```

        """
        (pre, data, post) = split_body(self.body)
        data = parse_data(data)

        if data.type != "Workstreams":
            raise Exception(
                f"{self.issue_resourcePath} - body contains '{data.type}', but expected 'Workstreams'.")

        # The actual data itself is fully regenerated from the list of workstreams
        workstreams:List[Issue] = issues.workstreams
        workstreams.sort(key=lambda a: a.issue_resourcePath)

        data.sections = []

        for w in workstreams:
            section = IssueSection()
            section.title = self.buildSectionTitle(w)
            section.contents = w.getContentsFor(self)

            nonBlankLines = [l for l in section.contents if l]
            if len(nonBlankLines) > 0:
                data.sections.append(section)
            
        self.body = rebuild_body(pre, rebuild_data(data), post)

    

    def updateWorkstream(self, issues):
        """
        Workstreams are expected to contain a list of milestones. The issue
        referenced in the title is authoritative, and so should be updated, but
        the workstream issues is authoritative for the contents under the
        milestone.

        ```
        text before the data

        ## Milestones

        ### A milestone (#123)
        content

        ### Another mileston (#234)
        content
        ----
        text after the data
        """
        (pre, data, post) = split_body(self.body)
        data = parse_data(data)

        if not data.type:
            return

        if data.type != "Milestones":
            raise Exception(
                f"{self.issue_resourcePath} - body contains '{data.type}', but expected 'Milestones'.")
        
        for s in data.sections:
            self.updateMilestoneSectionInWorkstream(issues, s)

        self.body = rebuild_body(pre, rebuild_data(data), post)

    def updateMilestoneSectionInWorkstream(self, issues, section: IssueSection):
        sectionIssue = issues.findIssue(self, section.getReferenceFromTitle())
        if not sectionIssue:
            return section
        
        section.title = self.buildSectionTitle(sectionIssue)
        
        return section


    def buildSectionTitle(self, issue:Self):
        try:
            if issue.title == None:
                return "Issue has no title - maybe draft?"

            m = re.match(r"\[.*\](.*)", issue.title)
            if m:
                title = m[1].strip()
            else:
                title = issue.title

            return f"{title} ({issue.getIssueReference(self)})"
        except:
            print(f"Exception working on issue {issue} {issue.issue_id} {issue.issue_resourcePath}")
            raise
                                                    
    def getContentsFor(self, issue) -> List[str]:
        (_, data, _) = split_body(self.body)
        data = parse_data(data)

        for s in data.sections:
            reference = self.convertReferenceToResourcePath(s.getReferenceFromTitle())
            if reference == issue.issue_resourcePath:
                return s.contents
            
        return []




def split_body(body: str):
    """An issue's body is made up of three sections:

    * pre
    * data
    * post

    Data is identified by a line starting with "## Milestones" or "##
    Workstreams".

    The post section starts with a horizontal rule (at least 3 '-' characters).
    """
    pre = []
    data = []
    post = []

    state = "pre"

    for line in body.splitlines():
        if state == "pre":
            if line.startswith("## Milestones") or line.startswith("## Workstreams"):
                state = "data"
            else:
                pre.append(line)
        if state == "data":
            if line.startswith('---'):
                state = "post"
            else:
                data.append(line)
        if state == "post":
            post.append(line)

    return (pre, data, post)


def rebuild_body(pre: List[str], body: List[str], post: List[str]):
    return "\n".join(pre + body + post)


def parse_data(data: List[str]) -> IssueData:
    """
    The data section can list milestones or workstreams, depending on the title
    that starts with "##".  Anything before this title is ignored.

    Then each milestone/workstream is identified with "###", and the contents of
    the section is preserved.
    """
    d = IssueData()

    if not data:
        return d

    currentSection = None

    for line in data:
        if d.type == None:
            m = re.match("## (Milestones|Workstreams)", line)
            if m:
                d.type = m[1]
            continue

        # Check for a new section
        m = re.match("### (.*)", line)
        if m:
            if currentSection:
                d.sections.append(currentSection)
            currentSection = IssueSection()
            currentSection.title = m[1].strip()
        else:
            if not currentSection:
                # create a dummy section for stray lines before a section header
                currentSection = IssueSection()
            currentSection.contents.append(line)

    if currentSection:
        d.sections.append(currentSection)

    return d


def rebuild_data(data: IssueData) -> List[str]:
    body = [f"## {data.type}"]

    for section in data.sections:
        if section.title:
            body.append(f"### {section.title}")

        for line in section.contents:
            body.append(line)
            
        if body[-1] != "":
            body.append("")

    return body

class Issues:
    all_issues: Dict[str, Issue]
    milestones: List[Issue]
    workstreams: List[Issue]
    tracked_issues_not_in_project: List[str]

    def __init__(self, gh):
        def is_interesting(i: Issue):
            return i.category in [Category.ProjectMilestone, Category.Workstream]

        self.all_issues = dict([(i.issue_resourcePath, i)
                               for i in gh.project_items_summary()])

        interesting = [i for i in self.all_issues.values()
                       if is_interesting(i)]
        gh.populate_issues_body(interesting)

        self.milestones = [i for i in interesting if i.category == Category.ProjectMilestone]
        self.workstreams = [i for i in interesting if i.category == Category.Workstream]
    
    def findIssue(self, contextIssue:Issue, reference:str):
        if not reference:
            return None
        
        reference = contextIssue.convertReferenceToResourcePath(reference)        
        return self.all_issues[reference]
    
