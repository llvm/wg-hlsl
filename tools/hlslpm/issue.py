from dataclasses import dataclass, field
from datetime import datetime, date
from enum import Enum
import re
from typing import Dict, List, Optional, Union
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

    def getReferencedIssue(self):
        if not self.title:
            return None

        m = re.match(".*\((.+)\)", self.title)
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
        else:
            reference = self.issue_resourcePath

        return reference.replace("/", "#")

    def update(self, issues):
        if not self.body:
            return

        if self.category == Category.ProjectMilestone:
            self.updateMilestone(issues)

    def updateMilestone(self, issues):
        """
        Milestones are expected to contain a list of workstreams, with the
        content that each workstream lists for this milestone. The workstream
        issue is authoritative for this content.
        """
        (pre, data, post) = split_body(self.body)
        data = parse_data(data)

        if data.type != "Workstreams":
            raise Exception(
                f"{self.issue_resourcePath} - body contains '{data.type}', but expected 'Workstreams'.")

        for s in data.sections:
            self.updateWorkstreamSectionInMilestone(issues, s)

        self.body = rebuild_body(pre, rebuild_data(data), post)

    def updateWorkstreamSectionInMilestone(self, issues, section: IssueSection):
        sectionIssue = issues.findIssue(self, section.getReferencedIssue())
        if not sectionIssue:
            return section
        
        section.title = self.buildSectionTitle(sectionIssue)
        
        return section
    
    def buildSectionTitle(self, issue):
        m = re.match(r"\[.*\](.*)", issue.title)
        if m:
            title = m[1].strip()
        else:
            title = issue.title

        return f"{title} ({issue.getIssueReference(self)})"


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
        body.append(f"### {section.title}")
        for line in section.contents:
            body.append(line)

    return body

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

    def rewriteMilestone(self, path):
        milestone = self.milestones[path]
        (pre, data, post) = split_body(milestone.body)

        milestoneData = parse_data(data)

        if milestoneData.type != "Workstreams":
            raise Exception(f"{path} - expected Workstreams, but got {milestoneData.type}")        

        return milestone
    
    def findIssue(self, contextIssue:Issue, reference:str):
        m = re.match(r"(.+)#(\d+)", reference)
        if m:
            # If reference is full path we can translate it to a referencePath
            reference = f"{m[1]}/{m[2]}"
        else:
            # Otherwise construct a full path given the context

            # remove the "#""
            m = re.match(r"#(\d+)", reference)
            if not m:
                raise Exception(f"Unable to parse reference {reference}")
            reference = m[1]

            basePath = contextIssue.getResourcePathBase()
            reference = f"{basePath}/{reference}"
        
        return self.all_issues[reference]
    

if __name__ == '__main__':
    testData = json.loads(r"""{"issue_id": "I_kwDOMbLzis6Rpmkm", "item_id": null, "item_updatedAt": null, "category": null, "issue_updatedAt": null, "title": "[workstream] Resources", "body": "HLSL has buffer, texture, and sampler types that need to be lowered to resource representations when lowered to DXIL and SPIR-V.\n\n## Milestones\n\n### Compile a runnable shader from Clang (#7)\n- [ ] llvm/llvm-project#101555\n- [ ] llvm/llvm-project#101557\n\n### Compile particle_life.hlsl (#20)\n- [ ] Structured buffers\n- [ ] CBuffer resource types and operations\n\n### Compile all DML shaders, and they pass the validator (#11)\n- [ ] #10\n\n### Render Textured Triangle (#13)\n- [ ] llvm/llvm-project#101558\n\n### Pixel and Vertex Shaders (#16)\n- [ ] Sampler Feedback\n\n### Mesh Shaders (#17)\n- [ ] Input/Output patches\n\n### Ray Tracing (#18)\n- [ ] Ray tracing payloads\n\n----\n\n\nRelated tasks that need to be updated or refined:\n- [ ] llvm/llvm-project#75830 \n- [ ] llvm/llvm-project#58051 \n- [ ] llvm/llvm-project#75981 \n- [ ] llvm/llvm-project#57848\n- [ ] llvm/llvm-project#58654\n"}""")
    item = Issue("dummy")
    item.__dict__ = testData

    (pre, data, post) = split_body(item.body)

    print("---- PRE")
    print(pre)

    print("---- DATA")
    print(data)

    print("---- POST")
    print(post)
