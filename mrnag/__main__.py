"""Runnable module for Merge Request Nag Tool "Mr. Nag"."""
import csv
import sys
from argparse import ArgumentParser, Namespace
from datetime import datetime
from itertools import tee
from typing import Iterable
from mrnag import Project, aging_filter, inclusive_label_filter, exclusive_label_filter, fetch_project_details,\
    filter_non_wips, filter_wips, parse_config


def get_cli_parser() -> ArgumentParser:
    """Returns a configured command line parser."""
    parser: ArgumentParser = ArgumentParser(description='Mr. Nag.')
    wip_group = parser.add_mutually_exclusive_group()

    parser.add_argument('-c', '--config', required=True, help='Configuration file (YAML).')
    parser.add_argument('-t', '--to-format', choices=['csv', 'md'], help='The output format.')
    wip_group.add_argument('--only-wips',
                           action='store_true',
                           help='Limit results to only MRs marked as a "work in progress"')
    wip_group.add_argument('--wips', action='store_true', help='Include MRs marked as "work in progress" in output.')
    parser.add_argument('--include', action='append', help='Inclusive filter for MR labels.')
    parser.add_argument('--exclude', action='append', help='Exclusive filter for MR labels.')
    parser.add_argument('--minimum-age', type=int, help='Minimum age (in days).')

    return parser


def csv_formatter(projects: Iterable[Project]) -> None:
    """Formats the give projects as a CSV and prints it to stdout.

    :param projects: An iterable collections of projects.
    """
    headers = ['Name', 'Title', 'Author', 'Created', 'Last Updated', 'Total Approvals', 'Required Approvals',
               'Comments', 'WIP', 'Labels']
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
                ','.join(mr.labels or [])
            ])


def md_formatter(projects: Iterable[Project]) -> None:
    """Formats the give projects as a CSV and prints it to stdout.

    :param projects: An iterable collections of projects.
    """
    now: datetime = datetime.now()
    projects, projects_stats_itr = tee(projects)
    mr_count: int = 0
    proj_count: int = 0

    for proj in projects_stats_itr:
        if proj.merge_requests:
            proj_count += 1

        mr_count += len(proj.merge_requests)

    print(f"# Mr. Nag: {now.strftime('%Y-%m-%d')}\n")
    print(f'There are {mr_count} merge request{"s" if mr_count > 1 else ""}',
          f'in {proj_count} project{"s" if proj_count > 1 else ""}\n')

    for project in projects:
        print(f'## {project.name}\n')

        for mr in project.merge_requests:
            print(f'### {mr.title}\n')
            print(f'{mr.author}, {mr.created_at.diff_for_humans()}')
            print(f'{mr.approvals.total}/{mr.approvals.required} approvals,',
                  f'{mr.comment_count} comment{"s" if mr.comment_count == 0 or mr.comment_count > 1 else ""}')
            print()

        print()


def mrnag():
    """Executes the Mr. Nag command line interface."""
    parser = get_cli_parser()
    args: Namespace = parser.parse_args()
    forges, projects = parse_config(args.config)

    proj_list: Iterable[Project] = fetch_project_details(forges, projects)

    if args.only_wips:  # only WIPs
        proj_list = filter(filter_wips, proj_list)
    elif not args.wips:  # only non-WIPs
        proj_list = filter(filter_non_wips, proj_list)

    if args.include:
        proj_list = filter(inclusive_label_filter(args.include), proj_list)

    if args.exclude:
        proj_list = filter(exclusive_label_filter(args.exclude), proj_list)

    if args.minimum_age:
        proj_list = filter(aging_filter(args.minimum_age), proj_list)

    if args.to_format == 'md':
        md_formatter(proj_list)
    else:
        csv_formatter(proj_list)


mrnag()
