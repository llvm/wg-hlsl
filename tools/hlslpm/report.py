from argparse import ArgumentParser
import os

import github
from issue import Issues


def report_addArgs(subparsers):
    parser: ArgumentParser = subparsers.add_parser(
        'report', aliases=['r'], help="Generate output/report.md")
    parser.set_defaults(func=report)
    

def report(args):
    print("Fetching data...")
    gh = github.GH()
    issues = Issues(gh)

    print("Analyzing...")

    lines = ["# Roadmap"]



    print("Writing report...")
    filename = os.path.normpath("output/report.md")
    os.makedirs(os.path.dirname(filename), exist_ok=True)
    with open(filename, 'w') as f:
        f.writelines(lines)

