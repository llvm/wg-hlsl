from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
import re
from typing import List, Optional, Union
import json


class Category(Enum):
    NoCategory = None
    Item = "Item"
    Deliverable = "Deliverable"
    Workstream = "Workstream"
    WorkstreamMilestone = "Workstream Milestone"
    ProjectMilestone = "Project Milestone"


@dataclass
class Issue:
    issue_id: str
    issue_resourcePath: Optional[str] = field(default=None)
    item_id: Optional[str] = field(default=None)
    item_updatedAt: Optional[datetime] = field(default=None)
    category: Optional[Category] = field(default=None)
    issue_updatedAt: Optional[datetime] = field(default=None)
    title: Optional[str] = field(default=None)
    body: Optional[str] = field(default=None)


def split_body(body:str):
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


class IssueSection:
    title: str = None
    contents: List[str]

    def __init__(self):
        self.contents = []

class IssueData:
    type: str = None
    sections: List[IssueSection]

    def __init__(self):
        self.sections = []
    

def parse_data(data: List[str]) -> IssueData:
    """
    The data section can list milestones or workstreams, depending on the title
    that starts with "##".  Anything before this title is ignored.

    Then each milestone/workstream is identified with "###", and the contents of
    the section is preserved.
    """
    d = IssueData()

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