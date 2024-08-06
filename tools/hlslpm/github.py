from enum import Enum
from dataclasses import dataclass, field
import os
import sys
from typing import List, Optional
import requests
from datetime import datetime


class GH:
    def __init__(self):
        self.accessToken = get_pat()

    def graphql(self, query: str, variables={}):
        response = requests.post("https://api.github.com/graphql",
                                 json={'query': query, 'variables': variables},
                                 headers={'Authorization': f'Bearer {self.accessToken}',
                                          'Content-Type': 'application/json'})

        response.raise_for_status()

        return response.json()


class Category(Enum):
    NoCategory = None
    Item = "Item"
    Deliverable = "Deliverable"
    Workstream = "Workstream"
    WorkstreamMilestone = "Workstream Milestone"
    ProjectMilestone = "Project Milestone"


@dataclass
class Item:
    issue_id: str
    item_id: Optional[str] = field(default=None)
    item_updatedAt: Optional[datetime] = field(default=None)
    category: Optional[Category] = field(default=None)
    issue_updatedAt: Optional[datetime] = field(default=None)
    title: Optional[str] = field(default=None)
    body: Optional[str] = field(default=None)


def maybe_get(d: dict, *args):
    for a in args:
        if d != None and type(d) == dict:
            d = d.get(a, None)
        else:
            break
    return d


def to_datetime(str):
    if not str:
        return None
    return datetime.strptime(str, '%Y-%m-%dT%H:%M:%SZ')


def project_items_summary(gh: GH):
    query = read_file("gql/project_item_summary.gql")

    pageInfo = {'endCursor': None, 'hasNextPage': True}

    while pageInfo['hasNextPage']:
        response = gh.graphql(query, {'after': pageInfo['endCursor']})

        items = maybe_get(response, 'data', 'organization',
                          'projectV2', 'items')
        for node in items['nodes']:
            yield Item(
                item_id=node['id'],
                item_updatedAt=to_datetime(maybe_get(node, 'updatedAt')),
                category=Category(maybe_get(node, 'fieldValueByName', 'name')),
                issue_id=maybe_get(node, 'content', 'id'),
                issue_updatedAt=to_datetime(maybe_get(node, 'content', 'updatedAt')))

        pageInfo = maybe_get(items, 'pageInfo')


def get_issues(gh: GH, issues: List[Item]):
    query = read_file("gql/get_issue_text.gql")
    chunk_size = 50

    issue_id_chunks = [issues[i:i+chunk_size]
                       for i in range(0, len(issues), chunk_size)]

    for chunk in issue_id_chunks:
        response = gh.graphql(
            query, {'issueIds': [issue.issue_id for issue in chunk]})

        nodes = maybe_get(response, "data", "nodes")
        for (issue, node) in zip(chunk, nodes):
            issue.title = node["title"]
            issue.body = node["body"]
            yield issue


def get_pat():
    try:
        return read_file("pat.txt").strip()
    except:
        print(
            f"Couldn't read pat.txt not found - create a pat on github and store it in pat.txt next to {__file__}.")
        sys.exit(1)


def read_file(filename):
    with open(os.path.join(os.path.dirname(__file__), filename), 'r') as f:
        return f.read()


if __name__ == '__main__':
    gh = GH()

    if True:
        items_summary = [i for i in project_items_summary(gh)]
        print(f"{len(items_summary)} items")

        interesting = [i for i in items_summary if i.category ==
                       Category.ProjectMilestone or i.category == Category.Workstream]
        
        interesting = [i for i in get_issues(gh, interesting)]

        milestones = [i for i in interesting if i.category == Category.ProjectMilestone]
        workstreams = [i for i in items_summary if i.category == Category.Workstream]

        print("Milestones:")
        for milestone in milestones:
            print(milestone.title)

        print("Workstreams:")
        for workstream in workstreams:
            print(workstream.title)

    if True:
        issues = [i for i in get_issues(
            gh, [Item(issue_id="I_kwDOMbLzis6Rpmkm")])]

        for i in issues:
            print(f"Title: {i.title}")
            print(f"Body: {i.body}")
            print('-----')
