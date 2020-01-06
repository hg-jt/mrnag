"""Merge Request Nag Tool "Mr. Nag".

MIT License -- Copyright (c) 2019 hg-jt
"""
import logging
from datetime import datetime
from dataclasses import dataclass, field
from concurrent.futures import ThreadPoolExecutor
from os import environ
from typing import Callable, Iterable, List, Optional
import pendulum
from requests import Response, Session
from yaml import SafeLoader, load as yml_load


LOG = logging.getLogger(__name__)


@dataclass
class MergeRequestApprovals:
    """Represents the approvals for a merge/pull request"""
    total: int = 0
    required: int = 0


@dataclass
class MergeRequest:
    """Represents metadata about a merge/pull request."""
    title: str
    author: str
    created_at: datetime
    updated_at: datetime
    approvals: MergeRequestApprovals = field(default_factory=MergeRequestApprovals, init=False)
    labels: List[str] = field(default_factory=list)
    wip: bool = False
    comment_count: int = 0
    merge_request_id: int = None
    url: str = None


@dataclass
class Project:
    """Represents a project in a source code management system (i.e. a "forge")."""
    project_id: int
    forge: str
    name: str
    merge_requests: List[MergeRequest] = field(default_factory=list, init=False)
    url: str = None


@dataclass
class Forge:
    """Represents a "forge" (i.e. a web-based SCM repo manager).

    This class attempts to automatically load a GitLab API token from an
    environment variable that uses the forge type and forge id. For example,
    if the forge type is "gitlab" and the id is "abc, the API token environment
    variable would be ABC_GITLAB_TOKEN.

    *NOTE*: Dashes will be removed from the forge id.
    """
    id: str
    type: str
    api_url: str
    token: str
    projects: List[Project] = field(default_factory=list)

    def __post_init__(self):
        """Post-initialization for ``token`` and ``projects``."""
        if not self.token:  # get token from environment variable
            self.token = environ.get(f"{self.id.replace('-', '')}_{self.type}_TOKEN".upper())

        if self.projects:  # find "raw" dicts and convert them to Project objects
            projects: List[Project] = []

            for project in self.projects:
                if isinstance(project, dict):
                    projects.append(Project(**project, forge=self.id))
                elif isinstance(project, Project):
                    projects.append(project)
                else:
                    LOG.warning('Unable to parse project metadata, unexpected type: %s', type(project))

            self.projects = projects

    def fetch_project(self, project: Project) -> Project:
        """Fetch the project details.

        Sub-classes should override this method.

        :param project: The project to fetch the details for.
        :return: A hydrated project.
        """
        raise NotImplementedError()


@dataclass
class Gitlab(Forge):
    """Provides a minimal GitLab client for fetching project and merge request details."""
    session: Session = field(default_factory=Session, init=False, repr=False)

    def __post_init__(self):
        super().__post_init__()
        self.session.headers['PRIVATE-TOKEN'] = self.token

    def fetch_project(self, project: Project) -> Project:
        """Fetch the project details.

        :param project: The project to fetch the details for.
        :return: A hydrated project.
        """
        project: Project = self.get_merge_request_details(self.get_project_details(project))

        return project

    def get_merge_request_details(self, project: Project) -> Project:
        """Get merge request information from GitLab.

        :param project: The project to enrich.
        :return: The given project, enriched with merge request data.
        """
        resp: Response = self.session.get(f'{self.api_url}/projects/{project.project_id}/merge_requests?state=opened')

        if not resp.ok:
            # TODO: mark the project to indicate something went wrong
            # TODO: smoother handling of error state
            raise Exception('Unable to get list of merge request.')

        for mr in resp.json():
            merge_request: MergeRequest = MergeRequest(
                mr['title'],
                mr.get('author', {}).get('name'),
                timestamp_to_datetime(mr['created_at']),
                timestamp_to_datetime(mr['updated_at']),
                mr['labels'],
                comment_count=mr['user_notes_count'],
                merge_request_id=mr['iid'],
                url=mr['web_url']
            )

            resp = self.session.get(
                f'{self.api_url}/projects/{project.project_id}/merge_requests/{mr["iid"]}/approvals'
            )

            if not resp.ok:
                raise Exception('Unable to get approval details')  # TODO: smoother handling of error state

            approvals: dict = resp.json()
            merge_request.approvals.total = len(approvals['approved_by'])
            merge_request.approvals.required = approvals.get('approvals_required', 0)
            merge_request.wip = mr.get('work_in_progress', False)

            project.merge_requests.append(merge_request)

        return project

    def get_project_details(self, project: Project) -> Project:
        """Get project metadata from GitLab.

        :param project: The project to enrich.
        :return: The given project, enriched with additional metadata.
        """
        resp: Response = self.session.get(f'{self.api_url}/projects/{project.project_id}')

        if not resp.ok:
            raise Exception('Unable to fetch project details')  # TODO: smoother handling of error state

        gl_project: dict = resp.json()

        if not project.name:
            project.name = gl_project.get('name', gl_project.get('id'))

        project.url = gl_project['web_url']

        return project


@dataclass
class Github(Forge):
    """Provides a minimal GitHub client for fetching project and merge request details."""
    session: Session = field(default_factory=Session, init=False, repr=False)
    repo_and_pr_query = """
        query RepoWithPullRequests($repo_owner: String!,
                                   $repo_name: String!,
                                   $pr_count: Int!,
                                   $pr_cursor: String,
                                   $label_cursor: String,
                                   $review_cursor: String,
                                   $bpr_cursor: String) {
          repository(owner: $repo_owner, name: $repo_name) {
            name
            url
            pullRequests(states: OPEN, first: $pr_count, after: $pr_cursor) {
              totalCount
              nodes {
                number
                title
                createdAt
                updatedAt
                author {
                  login
                }
                permalink
                baseRefName
                labels(first: 10, after: $label_cursor) {
                  nodes {
                    name
                  }
                  pageInfo {
                    endCursor
                    hasNextPage
                  }
                }
                reviews(first: 10, after: $review_cursor) {
                  totalCount
                  nodes {
                    state
                  }
                  pageInfo {
                    endCursor
                    hasNextPage
                  }
                }
              }
              pageInfo {
                endCursor
                hasNextPage
              }
            }
            branchProtectionRules(first: 25, after: $bpr_cursor) {
              totalCount
              nodes {
                requiredApprovingReviewCount
                requiresApprovingReviews
                pattern
              }
              pageInfo {
                endCursor
                hasNextPage
              }
            }
          }
        }
    """

    def fetch_project(self, project: Project) -> Project:
        owner, repo = project.project_id.split('/')
        resp: Response = self.session.post(
            'https://api.github.com/graphql',
            json={
                'query': self.repo_and_pr_query,
                'variables': {
                    'repo_owner': owner,
                    'repo_name': repo,
                    'pr_count': 10,
                    'pr_cursor': None,
                    'label_cursor': None,
                    'bpr_cursor': None
                }
            },
            headers={'Authorization': f'token {self.token}'}
        )

        if not resp.ok:
            # TODO: mark the project to indicate something went wrong
            # TODO: smoother handling of error state
            raise Exception('Unable to get list of merge requests.')

        data: dict = resp.json().get('data', {})
        project.url = data.get('url')

        for pr in data.get('repository', {}).get('pullRequests').get('nodes'):
            merge_request: MergeRequest = MergeRequest(
                pr['title'],
                pr.get('author', {}).get('login'),
                timestamp_to_datetime(pr['createdAt']),
                timestamp_to_datetime(pr['updatedAt']),
                [label.get('name') for label in pr.get('labels', {}).get('nodes', [])],
                comment_count=pr.get('reviews').get('totalCount', 0),  # TODO: check state?
                merge_request_id=pr['number'],
                url=pr['permalink']
            )

            project.merge_requests.append(merge_request)
            # TODO: get WIP status
            # TODO: parse approval info

        return project


def timestamp_to_datetime(timestamp) -> Optional[datetime]:
    """Convert a timestamp string to a datetime object with timezone info.

    :param timestamp: timestamp string.
    :return: A datetime object with timezone info or None.
    """
    if not timestamp:
        return None

    try:
        return pendulum.parse(timestamp)
    except ValueError:
        return None


def fetch_project_details(forges: List[Forge], workers: int = -1) -> List[Project]:
    """Fetch the project and merge request details across all forges.

    :param forges: A list of Forge objects to process.
    :param workers: The maximum number of threads to use.
    :return: A list of Project objects.
    """
    projects: List[Project] = []

    for forge in forges:
        if workers < 0:
            workers = len(forge.projects)

        with ThreadPoolExecutor(max_workers=workers) as executor:
            projects.extend(list(executor.map(forge.fetch_project, forge.projects)))

    return projects


def filter_wips(project: Project) -> Optional[Project]:
    """Reduces merge request list to just merge requests that are marked as WIP.

    :param project: The project to filter.
    :return: The project with a filtered list of merge request or None, if no merge requests remain.
    """
    if not project:
        return None

    project.merge_requests = list(filter(lambda mr: mr.wip, project.merge_requests))

    return project if project.merge_requests else None


def filter_non_wips(project: Project) -> Optional[Project]:
    """Reduces merge request list to just merge requests that are not marked as WIP.

    :param project: The project to filter.
    :return: The project with a filtered list of merge requests or None, if no merge requests remain.
    """
    if not project:
        return None

    project.merge_requests = list(filter(lambda mr: not mr.wip, project.merge_requests))

    return project if project.merge_requests else None


def parse_config(filename: str) -> List[Forge]:
    """Parses the configuration file.

    :param filename:
    :return: A list of forges.
    """
    forges: List[Forge] = []
    forge_classes = {
        'gitlab': Gitlab,
        'github': Github
    }

    with open(filename, 'r') as config_file:
        app_config = yml_load(config_file, Loader=SafeLoader)

    for forge_md in app_config.get('forges'):
        forge_class = forge_classes.get(forge_md.get('type', '').lower(), Forge)
        forges.append(forge_class(**forge_md))

    return forges


def inclusive_label_filter(labels: List[str]) -> Callable:
    """Creates a function for selecting merge requests with one or more of the given labels.

    :param labels: A list of merge request labels.
    :return: A function that can be used with the filter builtin.
    """
    def inclusive_filter(project: Project):
        project.merge_requests = list(
            filter(lambda mr: any(label in mr.labels for label in labels), project.merge_requests)
        )

        return project if project.merge_requests else None

    return inclusive_filter


def exclusive_label_filter(labels: List[str]) -> Callable:
    """Creates a function for selecting merge requests that do not contain any of the given labels.

    :param labels: A list of merge request labels.
    :return: A function that can be used with the filter builtin.
    """
    def exclusive_filter(project: Project):
        project.merge_requests = list(
            filter(lambda mr: any(label not in mr.labels for label in labels), project.merge_requests)
        )

        return project if project.merge_requests else None

    return exclusive_filter


def aging_filter(days):
    """Creates a function for selecting merge requests that are older than the given number of days.

    :param days: The minimum age of a merge request.
    :return: A function that can be used the the filter builtin.
    """
    now: datetime = pendulum.now(tz='UTC')

    def mr_aging_filter(project: Project) -> Optional[Project]:
        if not project:
            return None

        project.merge_requests = list(filter(lambda mr: (now - mr.created_at).days > days,
                                             project.merge_requests))

        return project if project.merge_requests else None

    return mr_aging_filter


def process_projects(forges: List[Forge],
                     only_wips: bool = False,
                     wips: bool = False,
                     include: Optional[List[str]] = None,
                     exclude: Optional[List[str]] = None,
                     minimum_age: int = 0,
                     order_by: str = 'created',
                     sort: str = 'desc') -> List[Project]:
    """
    Processes projects by fetching additional details from the configured
    forges and applying filtering and sorting.

    *NOTE*: Most of the filters and sorting can be done at the API layer, but
    is currently implemented here, after *all* the data is fetched. This should
    be revisited when there are multiple forges implemented.

    :param forges: A list of forges.
    :param only_wips: A flag to filter results to just merge requests that are
                      marked as a "work in progress". Disabled by default.
    :param wips: A flag to include merge requests that are marked as a
                 "work in progress". Disabled by default.
    :param include: A list of labels to filter merge requests by. Disabled by default.
    :param exclude: A list of labels to filter out merge requests. Disabled by default.
    :param minimum_age: The minimum age (in days) to filter merge requests by. Default is 0.
    :param order_by: The field to order by (e.g. 'created' or 'updated'). Default is 'created'.
    :param sort: The direction to sort by (e.g. 'asc' or 'desc'). Default is 'asc'.
    :return: A list of projects.
    """
    if not forges:
        raise ValueError('No forge configuration provided')

    proj_itr: Iterable[Project] = fetch_project_details(forges)

    if only_wips:  # only WIPs
        proj_itr = filter(filter_wips, proj_itr)
    elif not wips:  # only non-WIPs
        proj_itr = filter(filter_non_wips, proj_itr)

    if include:
        proj_itr = filter(inclusive_label_filter(include), proj_itr)

    if exclude:
        proj_itr = filter(exclusive_label_filter(exclude), proj_itr)

    if minimum_age:
        proj_itr = filter(aging_filter(minimum_age), proj_itr)

    projects = list(proj_itr)

    if order_by:
        if order_by.lower() == 'updated':
            for project in projects:
                project.merge_requests.sort(key=lambda mr: mr.updated_at, reverse=(sort == 'desc'))
        else:  # default to sorting by creation date
            for project in projects:
                project.merge_requests.sort(key=lambda mr: mr.created_at, reverse=(sort == 'desc'))

    return projects
