"""Runnable module for Merge Request Nag Tool "Mr. Nag"."""
import csv
import sys
from argparse import ArgumentParser, Namespace
from typing import Iterable
from mrnag import Project, parse_config, process_projects


def get_cli_parser() -> ArgumentParser:
    """Returns a configured command line parser."""
    parser: ArgumentParser = ArgumentParser(description='Mr. Nag.')
    wip_group = parser.add_mutually_exclusive_group()

    parser.add_argument('-c', '--config', required=True, help='Configuration file (YAML).')
    wip_group.add_argument('--only-wips',
                           action='store_true',
                           help='Limit results to only MRs marked as a "work in progress"')
    wip_group.add_argument('--wips', action='store_true', help='Include MRs marked as "work in progress" in output.')
    parser.add_argument('--include', action='append', help='Inclusive filter for MR labels.')
    parser.add_argument('--exclude', action='append', help='Exclusive filter for MR labels.')
    parser.add_argument('--minimum-age', type=int, help='Minimum age (in days).')
    parser.add_argument('--order-by',
                        choices=['created', 'updated'],
                        default='created',
                        help='The field to order merge requests by within each project.')
    parser.add_argument('--sort', choices=['asc', 'desc'], default='asc', help='The sort direction.')

    return parser


def csv_formatter(projects: Iterable[Project]) -> None:
    """Formats the give projects as a CSV and prints it to stdout.

    :param projects: An iterable collections of projects.
    """
    headers = ['Name', 'Title', 'Author', 'Created', 'Last Updated', 'Total Approvals', 'Required Approvals',
               'Comments', 'WIP', 'Labels', 'Assignees']
    csv_writer = csv.writer(sys.stdout)

    csv_writer.writerow(headers)
    for project in projects:
        for mr in project.merge_requests:
            csv_writer.writerow([
                project.name,
                mr.title,
                mr.author,
                mr.created_at,
                mr.updated_at,
                mr.approvals.total,
                mr.approvals.required,
                mr.comment_count,
                mr.wip,
                ','.join(mr.labels or []),
                ','.join(mr.assignees or [])
            ])


def mrnag():
    """Executes the Mr. Nag command line interface."""
    args: Namespace = get_cli_parser().parse_args()

    projects = process_projects(
        parse_config(args.config),
        args.only_wips,
        args.wips,
        args.include,
        args.exclude,
        args.minimum_age,
        args.order_by,
        args.sort)

    csv_formatter(projects)


mrnag()
