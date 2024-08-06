import os
import sys
import requests


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

    print(gh.graphql(read_file("gql/project_item_summary.gql")))
