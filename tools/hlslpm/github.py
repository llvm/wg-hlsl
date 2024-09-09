# Class for working with github's graphql API.

from enum import Enum
from dataclasses import dataclass, field
import os
import sys
from typing import Any, Generator, List, Optional
import requests
from datetime import datetime, date
import json

from issue import Category, Issue


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

    def project_items_summary(self) -> Generator[Issue, Any, None]:
        query = read_file_relative_to_this_script("gql/project_item_summary.gql")

        pageInfo = {'endCursor': None, 'hasNextPage': True}

        while pageInfo['hasNextPage']:
            response = self.graphql(query, {'after': pageInfo['endCursor']})

            items = maybe_get(response, 'data', 'organization',
                              'projectV2', 'items')
            for node in items['nodes']:
                yield Issue(
                    title=maybe_get(node, 'content', 'title'),
                    item_id=node['id'],
                    item_updatedAt=to_datetime(maybe_get(node, 'updatedAt')),
                    category=Category(
                        maybe_get(node, 'category', 'name')),
                    target_date=to_date(maybe_get(node, 'target', 'date')),
                    issue_id=maybe_get(node, 'content', 'id'),
                    issue_resourcePath=maybe_get(
                        node, 'content', 'resourcePath'),
                    issue_updatedAt=to_datetime(maybe_get(node, 'content', 'updatedAt')))

            pageInfo = maybe_get(items, 'pageInfo')

    def populate_issues_body(self, issues: List[Issue]):
        query = read_file_relative_to_this_script("gql/get_issue_text.gql")
        chunk_size = 50

        issue_id_chunks = [issues[i:i+chunk_size]
                           for i in range(0, len(issues), chunk_size)]

        for chunk in issue_id_chunks:
            response = self.graphql(
                query, {'issueIds': [issue.issue_id for issue in chunk]})

            nodes = maybe_get(response, "data", "nodes")
            for (issue, node) in zip(chunk, nodes):
                issue.body = node["body"]

    def set_issue_body(self, id, body):
        query = read_file_relative_to_this_script("gql/set_issue_body.gql")
        self.graphql(query, {"id": id, "body": body})


def maybe_get(d: dict, *args):
    """
    Helper for grabbing items in nested dictionaries.

    >>> maybe_get({ "foo" : { "bar" : 1 } }, "foo", "bar")
    1
    """
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


def to_date(str):
    if not str:
        return None
    return datetime.strptime(str, '%Y-%m-%d')


def get_pat():
    try:
        return read_file_relative_to_this_script("pat.txt").strip()
    except:
        print(
            f"Couldn't read pat.txt not found - create a pat on github and store it in pat.txt next to {__file__}.")
        sys.exit(1)


def read_file_relative_to_this_script(filename):
    with open(os.path.join(os.path.dirname(__file__), filename), 'r') as f:
        return f.read()


if __name__ == '__main__':
    gh = GH()

    if False:
        items_summary = [i for i in gh.project_items_summary()]
        print(f"{len(items_summary)} items")

        interesting = [i for i in items_summary if i.category ==
                       Category.ProjectMilestone or i.category == Category.Workstream]

        gh.populate_issues_body(interesting)

        milestones = [i for i in interesting if i.category ==
                      Category.ProjectMilestone]
        workstreams = [
            i for i in items_summary if i.category == Category.Workstream]

        print("Milestones:")
        for milestone in milestones:
            print(
                f"{milestone.issue_resourcePath} - {milestone.title} - {milestone.target_date}")

        print("Workstreams:")
        for workstream in workstreams:
            print(workstream.title)

    if False:
        issues = [Issue(issue_id="I_kwDOMbLzis6Rpmkm")]
        gh.populate_issues_body(issues)

        for i in issues:
            print(f"Title: {i.title}")
            print(f"Body: {i.body}")
            print('-----')
            # Serialize 'issues' list to JSON
            json_data = json.dumps([i.__dict__ for i in issues])
            print(json_data)
