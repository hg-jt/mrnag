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
class LabelFilters:
    """Represents the label filters to apply to a project."""
    include: List[str] = field(default_factory=list)
    exclude: List[str] = field(default_factory=list)


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
    assignees: List[str] = field(default_factory=list, init=False)


@dataclass
class Project:
    """Represents a project in a source code management system (i.e. a "forge")."""
    project_id: int
    forge: str
    name: str
    merge_requests: List[MergeRequest] = field(default_factory=list, init=False)
    labels: LabelFilters = field(default_factory=LabelFilters)
    url: str = None
    wip_count: int = 0

    def __post_init__(self):
        """Post-initialization for parsing ``labels``."""
        if isinstance(self.labels, dict):
            self.labels = LabelFilters(
                include=self.labels.get('include', []),
                exclude=self.labels.get('exclude', [])
            )

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
                timestamp_to_datetime(mr['created_at'], tz='utc'),
                timestamp_to_datetime(mr['updated_at'], tz='utc'),
                mr['labels'],
                comment_count=mr['user_notes_count'],
                merge_request_id=mr['iid'],
                url=mr['web_url']
            )

            for assignee in mr.get('assignees', []):
                merge_request.assignees.append(assignee.get('username'))

            resp = self.session.get(
                f'{self.api_url}/projects/{project.project_id}/merge_requests/{mr["iid"]}/approvals'
            )

            if not resp.ok:
                raise Exception('Unable to get approval details')  # TODO: smoother handling of error state

            approvals: dict = resp.json()
            merge_request.approvals.count = len(approvals['approved_by'])
            merge_request.approvals.required = approvals.get('approvals_required', 0)
            merge_request.wip = mr.get('work_in_progress', False)

            if merge_request.wip:
                project.wip_count += 1

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


def timestamp_to_datetime(timestamp: str, tz: Optional[str] = None) -> Optional[datetime]:
    """Convert a timestamp string to a datetime object with timezone info.

    :param timestamp: timestamp string.
    :return: A datetime object with timezone info or None.
    """
    if not timestamp:
        return None

    try:
        if tz:
            return pendulum.parse(timestamp, tz=tz)

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
        'gitlab': Gitlab
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
        _labels: List[str] = labels + project.labels.include

        if _labels:
            project.merge_requests = list(
                filter(lambda mr: any(label in mr.labels for label in _labels), project.merge_requests)
            )

        return project if project.merge_requests else None

    return inclusive_filter


def exclusive_label_filter(labels: List[str]) -> Callable:
    """Creates a function for selecting merge requests that do not contain any of the given labels.

    :param labels: A list of merge request labels.
    :return: A function that can be used with the filter builtin.
    """
    def exclusive_filter(project: Project):
        _labels: List[str] = labels + project.labels.exclude

        if _labels:
            project.merge_requests = list(
                filter(lambda mr: not any(label in mr.labels for label in _labels), project.merge_requests)
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

    proj_itr = filter(inclusive_label_filter(include or []), proj_itr)
    proj_itr = filter(exclusive_label_filter(exclude or []), proj_itr)

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
