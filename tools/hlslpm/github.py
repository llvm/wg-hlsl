# Class for working with github's graphql API.

import itertools
import os
import sys
from typing import Any, Generator, List
import requests
from datetime import datetime
import json

from issue import Category, Issue, IssueState


class GH:
    def __init__(self):
        self.accessToken = get_pat()
        self.queries = {}
        self.projectMilestoneFieldInfo = None

    def graphql(self, query: str, variables={}):
        response = requests.post("https://api.github.com/graphql",
                                 json={'query': query, 'variables': variables},
                                 headers={'Authorization': f'Bearer {self.accessToken}',
                                          'Content-Type': 'application/json'})

        response.raise_for_status()

        return response.json()

    def project_items_summary(self) -> Generator[Issue, Any, None]:
        query = self.get_query(
            "gql/project_item_summary.gql")

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
                    workstream=maybe_get(node, 'workstream', 'name'),
                    projectMilestone=maybe_get(
                        node, 'projectMilestone', 'name'),
                    issue_id=maybe_get(node, 'content', 'id'),
                    issue_state=IssueState(
                        maybe_get(node, 'content', 'state')),
                    issue_resourcePath=maybe_get(
                        node, 'content', 'resourcePath'),
                    issue_updatedAt=to_datetime(maybe_get(node, 'content', 'updatedAt')))

            pageInfo = maybe_get(items, 'pageInfo')

    def populate_issues_body(self, issues: List[Issue]):
        query = self.get_query("gql/get_issue_text.gql")
        chunk_size = 50

        issue_id_chunks = [issues[i:i+chunk_size]
                           for i in range(0, len(issues), chunk_size)]

        for chunk in issue_id_chunks:
            response = self.graphql(
                query, {'issueIds': [issue.issue_id for issue in chunk]})

            nodes = maybe_get(response, "data", "nodes")
            for (issue, node) in zip(chunk, nodes):
                issue.body = node["body"]

    def get_issues_tracked_graphql(self, issueIds, numIssuesToGet, after=None):
        query = self.get_query("gql/get_issues_tracked.gql")

        response = self.graphql(
            query, {"issueIds": issueIds, "numIssuesToGet": numIssuesToGet, "after": after})

        nodes = maybe_get(response, "data", "nodes")

        results = []
        for (issueId, node) in zip(issueIds, nodes):
            trackedIssues = [trackedIssue["id"]
                             for trackedIssue in maybe_get(node, "trackedIssues", "nodes")]
            pageInfo = maybe_get(node, "trackedIssues", "pageInfo")

            if pageInfo["hasNextPage"]:
                cursor = pageInfo["endCursor"]
            else:
                cursor = None

            results.append((issueId, trackedIssues, cursor))

        return results

    def get_issues_tracked(self, issueIds: List[str]):
        issueIdsBatches = itertools.batched(issueIds, 100)
        batchedTrackedIssues = [self.get_issues_tracked_graphql(
            list(issueIds), 100) for issueIds in issueIdsBatches]

        for (issueId, trackedIssues, cursor) in itertools.chain(*batchedTrackedIssues):
            while cursor != None:
                (_, nextIssues, cursor) = self.get_issues_tracked_graphql(
                    [issueId], 100, cursor)[0]
                trackedIssues += nextIssues
            yield (issueId, trackedIssues)

    def set_issue_body(self, id, body):
        query = self.get_query("gql/set_issue_body.gql")
        self.graphql(query, {"id": id, "body": body})

    def set_project_milestone(self, project_item_id, projectMilestone):
        if not self.projectMilestoneFieldInfo:
            self.projectMilestoneFieldInfo = self.get_project_field_info(
                "ProjectMilestone")

        query = self.get_query("gql/set_issue_project_milestone.gql")

        f = self.projectMilestoneFieldInfo
        params = {
            "projectId":f["projectId"],
            "fieldId":f["fieldId"],
            "itemId":project_item_id,
            "projectMilestone":f["options"][projectMilestone]
        }

        r = self.graphql(query, params)
        if "errors" in r:
            raise Exception(r["errors"])

    def get_project_field_info(self, fieldName: str):
        query = self.get_query("gql/get_project_field_id.gql")

        params = {
            "project": "llvm",
            "projectNumber": 4,
            "fieldName": fieldName
        }

        result = self.graphql(query, params)

        rawOptions = maybe_get(result, "data", "organization", "projectV2", "field", "options")
        options = dict([(o["name"], o["id"]) for o in rawOptions])

        return {
            "projectId": maybe_get(result, "data", "organization", "projectV2", "id"),
            "fieldId": maybe_get(result, "data", "organization", "projectV2", "field", "id"),
            "options": options
        }

    def get_query(self, name):
        if name in self.queries:
            return self.queries[name]

        query = read_file_relative_to_this_script(name)
        self.queries[name] = query

        return query


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

    if False:
        r = gh.get_issues_tracked(["I_kwDOMbLzis6Rpmkm", "I_kwDOBITxeM5SPFcF"])
        print(list(r))

    r = gh.get_project_field_info("ProjectMilestone")
    print(r)
