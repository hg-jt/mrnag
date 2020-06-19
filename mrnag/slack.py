"""Provides a service interface to Mr. Nag for a Slack app."""
import os
from dataclasses import asdict, dataclass, field
from typing import Dict, List, Optional

import inflect
import pendulum
import requests
from flask import Flask, Response, request
from flask.helpers import make_response
from humanize import naturaldelta
from zappa.asynchronous import task

from mrnag import Forge, Project, parse_config, process_projects, __version__


MRNAG_CONFIG_FILE = os.environ.get('MRNAG_CONFIG_FILE', 'config.yml')  #: path to configuration file

OAUTH_TOKEN = os.environ.get('SLACK_OAUTH_TOKEN')

PLURALIZER: inflect.engine = inflect.engine()

app: Flask = Flask('mrnag')


class NoProjects(Exception):
    """Error indicating no projects were found with open merge request."""
    pass


@dataclass
class SlashCommandRequest():
    """Represents the inbound request coming from a Slack slash command."""
    command: str = ''  #: The slash command that was invoked.
    text: str = ''  #: The text content following the slash command.
    token: str = ''  #: A verification token to ensure the request originated from Slack.
    channel_id: str = ''  #: The channel the slash command was called from.
    user_name: str = ''  #: The user that invoked the slash command.
    response_url: str = ''  #: The url to use for asynch responses.
    subcommand: Optional[str] = None  #: The subcommand, if one is provided (i.e he first word following the command).
    subcommand_opts: List[str] = field(default_factory=list)  #: A list of words after the name).

    def __post_init__(self):
        """Post-initialization for parsing out ``subcommand``."""
        if not self.subcommand and self.text:
            cmd_str_parts: List[str] = self.text.split()

            if cmd_str_parts:
                self.subcommand = cmd_str_parts[0]

                if len(cmd_str_parts) > 1:
                    self.subcommand_opts = cmd_str_parts[1:]

@app.route('/', methods=['GET'])
def info():
    """Provide basic info about Mr. Nag."""
    return {
        'version': __version__
    }


@app.route('/mrnag/slack', methods=['POST'])
def slash_mrnag() -> Response:
    """Provides the entry point for a Slack slash command.

    This function receives a request posted from a Slack slash command, parses
    the request into a SlackCommandRequest and dispatches the request out to
    the appropriate subcommand handler.
    """
    cmd_request: SlashCommandRequest = SlashCommandRequest(
        request.form.get('command', ''),
        request.form.get('text'),
        request.form.get('token'),
        request.form.get('channel_id'),
        request.form.get('user_name'),
        request.form.get('response_url')
    )

    if cmd_request.subcommand == 'help':
        return help_command(cmd_request)

    if cmd_request.subcommand == 'version':
        return version_command(cmd_request)

    # call async task
    get_merge_requests(asdict(cmd_request))

    return make_response({'response_type': 'ephemeral', 'text': 'Mr. Nag is calculating...'})


@task
def get_merge_requests(async_request: dict):
    """Async task for responding to a mrnag slash command."""
    cmd_request: SlashCommandRequest = SlashCommandRequest(**async_request)
    forges: List[Forge] = parse_config(MRNAG_CONFIG_FILE)
    slack_message: dict = {}

    if cmd_request.subcommand == 'queue':
        slack_message = queue_command(cmd_request, forges)
    elif cmd_request.subcommand == 'signup':
        slack_message = signup_command(cmd_request, forges)
    else:
        slack_message = show_command(cmd_request, forges)

    requests.post(cmd_request.response_url, json=slack_message, headers={'Authorization': f'Bearer {OAUTH_TOKEN}'})


def show_command(cmd_request: SlashCommandRequest, forges: List[Forge]) -> dict:
    if cmd_request.subcommand_opts:
        # first work can be "private", "sort", "wip"
        # /mrnag private
        # /mrnag sort age desc
        # /mrnag private sort age desc
        # /mrnag show private sort age desc
        # /mrnag wip
        # /mrnag private wip
        # /mrnag private wip sort desc
        # /mrnag wip
        # TODO: check for private and change the response type to ephemeral
        projects: List[Project] = []
    else:
        projects: List[Project] = process_projects(forges)

    return format_slack_response(projects, cmd_request.user_name)


def queue_command(cmd_request: SlashCommandRequest, forges: List[Forge]) -> dict:
    return {}


def version_command(cmd_request: SlashCommandRequest) -> dict:
    return {
        'response_type': 'ephemeral',
        'blocks': [make_section(f'Mr. Nag v{__version__}')]
    }


def help_command(cmd_request: SlashCommandRequest) -> dict:
    """Return a command usage message."""
    divider: dict = {'type': 'divider'}
    usage_command: str = cmd_request.subcommand_opts[0].lower() if cmd_request.subcommand_opts else None
    usage_blocks: Dict[str, dict] = {
        'show': make_section("""_Displays a list of open merge requests, by project._
        This is the default subcommand if one is not provided. Without any
        further filtering, the result will be a list of open, non-WIP'd merge
        requests sorted with oldest first per project.
        """),
        'queue': make_section("""_Displays a list of open merge request assigned to a specific user, by project._"""),
        'help': make_section("""._Displays this help message_."""),
        'version': make_section('Displays version information for the deployed version of Mr. Nag.')
    }

    help_response: List[dict] = [make_section('/mrnag *help*')]

    if usage_command in usage_blocks.keys():
        help_response.append(divider)
        help_response.append(usage_blocks.get(usage_command, make_section(f'No help docs for {usage_command} :(')))
    else:
        for block in usage_blocks.values():
            help_response.append(divider)
            help_response.append(block)

    return {
        'response_type': 'ephemeral',
        'blocks': help_response
    }


def format_slack_response(projects: List[Project], requestor: str = '', response_type: str = 'ephemeral') -> Dict:
    if not projects:
        raise NoProjects('No projects with open merge request were found')

    mr_count: int = sum([len(proj.merge_requests) for proj in projects])
    proj_count: int = len(projects)
    summary: str = '{} says there {} _{}_ open merge {} in _{}_ {}.'.format(
        requestor or 'Mr. Nag',
        PLURALIZER.plural('is', mr_count),
        mr_count,
        PLURALIZER.plural('request', mr_count),
        proj_count,
        PLURALIZER.plural('project', proj_count)
    )

    slack_post: dict = {
        'response_type': response_type,
        'blocks': [make_section(summary)]
    }

    for proj in projects:
        slack_post['blocks'].append({'type': 'divider'})
        slack_post['blocks'] += project_to_slack_blocks(proj)

    return slack_post


def project_to_slack_blocks(project: Project) -> List[Dict]:
    """Creates a collection of Slack blocks that represent the current state of a ``Project``.

    This function will create a list of JSON serializable dict objects.
    """
    wip_count: int = project.wip_count
    project_link: str = f'*<{project.url}|{project.name}>*'
    title_tail: str = f"{wip_count} {PLURALIZER.plural('WIP', wip_count)}" if wip_count else ''
    blocks: List[dict] = [
        make_section(f'{project_link} ({title_tail})' if wip_count else project_link)
    ]

    for mr in project.merge_requests:
        mr_field_preamble: str = f'*{mr.title}*\n{mr.author} {naturaldelta(pendulum.now("utc") - mr.created_at)} ago'
        mr_field_assignees: str = f'Assigned to: {", ".join(mr.assignees)}\n' if mr.assignees else ''
        mr_field_postamble: str = '<{}|{}/{} approvals, {} comments>'.format(
            mr.url,
            mr.approvals.count,
            mr.approvals.required,
            mr.comment_count
        )  # TODO Code: 123-45 // Reviewer(s): xxxxxx

        blocks.append(make_section(f'{mr_field_preamble}\n{mr_field_assignees}{mr_field_postamble}'))

    return blocks


def make_section(text: str) -> Dict:
    """Create a Slack "section" block."""
    return dict(
        type='section',
        text=dict(type='mrkdwn', text=text)
    )
