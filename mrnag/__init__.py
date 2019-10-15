"""Merge Request Nag Tool "Mr. Nag".

MIT License -- Copyright (c) 2019 hg-jt
"""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from os import environ
from typing import Callable, Dict, Iterable, List, Optional, Tuple
from requests import Response, Session
from yaml import SafeLoader, load as yml_load


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
    created_at: str
    approvals: MergeRequestApprovals = field(default_factory=MergeRequestApprovals, init=False)
    labels: List[str] = field(default_factory=list)
    wip: bool = False


@dataclass
class Project:
    """Represents a project in a source code management system (a.k.a a "forge")."""
    project_id: int
    forge: str
    name: str
    merge_requests: List[MergeRequest] = field(default_factory=list, init=False)


@dataclass
class Forge:
    """Represents a "forge" (i.e. a web-based SCM repo manager).

    This class attempts to automatically load a GitLab API token from an
    environment variable that uses the forge type and forge id. For example,
    if the forge type is "gitlab" and the id is "abc, the API token environment
    variable would be ABC_GITLAB_TOKEN.
    """
    id: str
    type: str
    api_url: str
    token: str

    def __post_init__(self):
        if not self.token:
            self.token = environ.get(f'{self.id}_{self.type}_TOKEN'.upper())

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
            raise Exception('Unable to merge request details')  # TODO: smoother handling of error state

        for mr in resp.json():
            merge_request: MergeRequest = MergeRequest(
                mr['title'],
                mr.get('author', {}).get('name'),
                mr['created_at'],
                mr['labels']
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

        gl_project = resp.json()

        if not project.name:
            project.name = gl_project.get('name', gl_project.get('id'))

        return project


def fetch_project_details(forges: Dict[str, Forge], projects: List[Project], workers: int = -1) -> List[Project]:
    """Fetches project details for all the given projects.

    :param forges: A dictionary of forges (key -> Forge).
    :param projects: A list of projects.
    :param workers: The number of worker threads. Defautls to -1, which will set the
                    worker count to the length of the project list.
    :return: A list of hydrated projects.
    """
    if workers < 0:
        workers = len(projects)

    with ThreadPoolExecutor(max_workers=workers) as executor:
        def project_details(project: Project) -> Project:
            forge: Forge = forges.get(project.forge)

            if not forge:
                # TODO: mark the project to indicate something went wrong
                return project

            return forge.fetch_project(project)

        hydrated_projects: List[Project] = executor.map(project_details, projects)

    return hydrated_projects


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
    :return: The project with a filtered list of merge request or None, if no merge requests remain.
    """
    if not project:
        return None

    project.merge_requests = list(filter(lambda mr: not mr.wip, project.merge_requests))

    return project if project.merge_requests else None


def parse_config(filename: str) -> Tuple[Dict[str, Forge], List[Project]]:
    """Parses the configuration file.

    :param filename:
    :return: A tuple containing a dictionary of key -> forge and a list of projects.
    """
    forges: List[Forge] = []
    forge_classes = {
        'gitlab': Gitlab
    }

    with open(filename, 'r') as config_file:
        app_config = yml_load(config_file, Loader=SafeLoader)

    for forge in app_config.get('forges'):
        forge_class = forge_classes.get(forge.get('type', '').lower(), Forge)
        forges.append(forge_class(**forge))

    projects: List[Project] = [Project(**project) for project in app_config.get('projects')]

    return {forge.id: forge for forge in forges}, projects


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
