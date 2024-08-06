from dataclasses import dataclass
import os
import sys
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

@dataclass
class ItemSummary:
    item_id: str
    item_updatedAt: datetime
    category: str
    issue_id: str
    issue_updatedAt: datetime

def maybe_get(d:dict, *args):
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

    pageInfo = { 'endCursor': None, 'hasNextPage': True }

    while pageInfo['hasNextPage']:
        response = gh.graphql(query, {'after': pageInfo['endCursor']})

        items = maybe_get(response, 'data', 'organization', 'projectV2', 'items')
        for node in items['nodes']:
            yield ItemSummary(
                item_id=node['id'],
                item_updatedAt=to_datetime(maybe_get(node, 'updatedAt')),
                category=maybe_get(node, 'fieldValueByName', 'name'),
                issue_id=maybe_get(node, 'content', 'id'),
                issue_updatedAt=to_datetime(maybe_get(node,'content','updatedAt')))
            
        pageInfo = maybe_get(items, 'pageInfo')



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

    items_summary = [i for i in project_items_summary(gh)]
    print(f"{len(items_summary)} items")

    milestones = [i for i in items_summary if i.category == "Project Milestone"]

    for milestone in milestones:
        print(milestone)

    # print(gh.graphql(read_file("gql/project_item_summary.gql")))
