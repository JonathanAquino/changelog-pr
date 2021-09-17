import json
import os
import re
import subprocess
from functools import cached_property

import requests
import yaml


class ChangelogCIBase:
    """Base Class for Changelog PR"""

    github_api_url = 'https://api.github.com'

    def __init__(
        self,
        repository,
        event_path,
        config,
        current_branch,
        filename='CHANGELOG.md',
        token=None
    ):
        self.repository = repository
        self.filename = filename
        self.config = config
        self.current_branch = current_branch
        self.token = token

    @cached_property
    def _get_request_headers(self):
        """Get headers for GitHub API request"""
        headers = {
            'Accept': 'application/vnd.github.v3+json'
        }
        # if the user adds `GITHUB_TOKEN` add it to API Request
        # required for `private` repositories
        if self.token:
            headers.update({
                'authorization': 'Bearer {token}'.format(token=self.token)
            })

        return headers

    def get_changes_after_last_release(self):
        return NotImplemented

    def parse_changelog(self, version, changes):
        return NotImplemented

    def _get_file_mode(self):
        """Gets the mode that the changelog file should be opened in"""
        if os.path.exists(self.filename):
            # if the changelog file exists
            # opens it in read-write mode
            file_mode = 'r+'
        else:
            # if the changelog file does not exists
            # opens it in read-write mode
            # but creates the file first also
            file_mode = 'w+'

        return file_mode

    def _get_latest_release_date(self):
        """Using GitHub API gets latest release date"""
        url = (
            '{base_url}/repos/{repo_name}/releases/latest'
        ).format(
            base_url=self.github_api_url,
            repo_name=self.repository
        )

        response = requests.get(url, headers=self._get_request_headers)

        published_date = ''

        if response.status_code == 200:
            response_data = response.json()
            # get the published date of the latest release
            published_date = response_data['published_at']
        else:
            # if there is no previous release API will return 404 Not Found
            msg = (
                f'Could not find any previous release for '
                f'{self.repository}, status code: {response.status_code}'
            )
            print_message(msg, message_type='warning')

        return published_date

    def _commit_changelog(self, string_data):
        """Write changelog to the changelog file"""
        file_mode = self._get_file_mode()

        with open(self.filename, file_mode) as f:
            # read the existing data and store it in a variable
            body = f.read()
            # write at the top of the file
            f.seek(0, 0)
            f.write(string_data)

            if body:
                # re-write the existing data
                f.write('\n\n')
                f.write(body)

        # TODO: Remove this debug logging
        subprocess.run(['ssh', '-T', 'git@github.com'])

        subprocess.run(['git', 'add', self.filename])
        subprocess.run(
            ['git', 'commit', '-m', '(Changelog PR) Added Changelog']
        )
        subprocess.run(
            ['git', 'push', '-u', 'origin', self.current_branch]
        )

    def run(self):
        """Entrypoint to the Changelog PR"""
        version = '9.9.9'

        changes = self.get_changes_after_last_release()

        # exit the method if there is no changes found
        if not changes:
            return

        string_data = self.parse_changelog(version, changes)

        print_message('Commit Changelog', message_type='group')
        self._commit_changelog(string_data)
        print_message('', message_type='endgroup')

class ChangelogCIPullRequest(ChangelogCIBase):
    """Generates and commits changelog using pull requests"""

    def _get_changelog_line(self, item):
        """Generate each PR block of the changelog"""
        if self._get_pr_label_annotation(item):
            pr_label_annotation = '[{pr_label_annotation}] '.format(pr_label_annotation=self._get_pr_label_annotation(item))
        else:
            pr_label_annotation = ''
        return "## [#{number}]({url}) ({merge_date})\n- {pr_label_annotation}{title}\n\n".format(
            number=item['number'],
            url=item['url'],
            title=item['title'],
            merge_date=item['merged_at'][0:10],
            pr_label_annotation=pr_label_annotation
        )

    def _get_pr_label_annotation(self, pull_request):
        """
        Returns a string to put in the annotation in square brackets before the PR title.
        """
        pr_labels = self.config.pr_labels
        matching_pr_labels = []
        if not pr_labels:
            return ''
        for pr_label in pr_labels:
            if pr_label in pull_request['labels']:
                matching_pr_labels.append(pr_label)
        if not matching_pr_labels:
            return 'choose PR label: ' + ', '.join(pr_labels)
        return ', '.join(matching_pr_labels)

    def get_changes_after_last_release(self):
        """Get all the merged pull request after latest release"""
        previous_release_date = self._get_latest_release_date()

        if previous_release_date:
            merged_date_filter = 'merged:>=' + previous_release_date
        else:
            # if there is no release for the repo then
            # do not filter by merged date
            merged_date_filter = ''

        url = (
            '{base_url}/search/issues'
            '?q=repo:{repo_name}+'
            'is:pr+'
            'is:merged+'
            'sort:author-date-asc+'
            '{merged_date_filter}'
            '&sort=merged'
        ).format(
            base_url=self.github_api_url,
            repo_name=self.repository,
            merged_date_filter=merged_date_filter
        )

        items = []

        response = requests.get(url, headers=self._get_request_headers)

        if response.status_code == 200:
            response_data = response.json()

            # `total_count` represents the number of
            # pull requests returned by the API call
            if response_data['total_count'] > 0:
                for item in response_data['items']:
                    data = {
                        'title': item['title'],
                        'number': item['number'],
                        'url': item['html_url'],
                        'merged_at': item['closed_at'],
                        'labels': [label['name'] for label in item['labels']]
                    }
                    items.append(data)
            else:
                msg = (
                    f'There was no pull request '
                    f'made on {self.repository} after last release.'
                )
                print_message(msg, message_type='error')
        else:
            msg = (
                f'Could not get pull requests for '
                f'{self.repository} from GitHub API. '
                f'response status code: {response.status_code}'
            )
            print_message(msg, message_type='error')

        return items

    def parse_changelog(self, version, changes):
        return ''.join(
            map(self._get_changelog_line, changes)
        )

class ChangelogCIConfiguration:
    """Configuration class for Changelog PR"""

    DEFAULT_PR_LABELS = []

    def __init__(self, config_file):
        # Initialize with default configuration
        self.pr_labels = self.DEFAULT_PR_LABELS

        self.user_raw_config = self.get_user_config(config_file)

        self.validate_configuration()

    @staticmethod
    def get_user_config(config_file):
        """
        Read user provided configuration file and
        return user configuration
        """
        if not config_file:
            print_message(
                'No Configuration file found, '
                'falling back to default configuration to parse changelog',
                message_type='warning'
            )
            return

        try:
            # parse config files with the extension .yml and .yaml
            # using YAML syntax
            if config_file.endswith('yml') or config_file.endswith('yaml'):
                loader = yaml.safe_load
            # parse config files with the extension .json
            # using JSON syntax
            elif config_file.endswith('json'):
                loader = json.load
            else:
                print_message(
                    'We only support `JSON` or `YAML` file for configuration '
                    'falling back to default configuration to parse changelog',
                    message_type='error'
                )
                return

            with open(config_file, 'r') as file:
                config = loader(file)

            return config

        except Exception as e:
            msg = (
                f'Invalid Configuration file, error: {e}, '
                'falling back to default configuration to parse changelog'
            )
            print_message(msg, message_type='error')
            return

    def validate_configuration(self):
        """
        Validate all the configuration options and
        update configuration attributes
        """
        if not self.user_raw_config:
            return

        if not isinstance(self.user_raw_config, dict):
            print_message(
                'Configuration does not contain required mapping '
                'falling back to default configuration to parse changelog',
                message_type='error'
            )
            return

        self.validate_pr_labels()

    def validate_pr_labels(self):
        """Validate and set pr_labels configuration option"""
        pr_labels = self.user_raw_config.get('pr_labels')

        if not pr_labels:
            msg = '`pr_labels` was not provided'
            print_message(msg, message_type='warning')
            return

        if not isinstance(pr_labels, list):
            msg = '`pr_labels` is not valid, It must be an Array/List.'
            print_message(msg, message_type='error')
            return

        self.pr_labels = pr_labels

def print_message(message, message_type=None):
    """Helper function to print colorful outputs in GitHub Actions shell"""
    # https://docs.github.com/en/actions/reference/workflow-commands-for-github-actions
    if not message_type:
        return subprocess.run(['echo', f'{message}'])

    if message_type == 'endgroup':
        return subprocess.run(['echo', '::endgroup::'])

    return subprocess.run(['echo', f'::{message_type}::{message}'])

if __name__ == '__main__':
    # Default environment variable from GitHub
    # https://docs.github.com/en/actions/configuring-and-managing-workflows/using-environment-variables
    event_path = os.environ['GITHUB_EVENT_PATH']
    repository = os.environ['GITHUB_REPOSITORY']
    current_branch = os.environ['INPUT_BRANCH']
    # User inputs from workflow
    filename = os.environ['INPUT_CHANGELOG_FILENAME']
    config_file = os.environ['INPUT_CONFIG_FILE']
    # Token provided from the workflow
    token = os.environ.get('GITHUB_TOKEN')
    # Committer username and email address
    username = os.environ['INPUT_COMMITTER_USERNAME']
    email = os.environ['INPUT_COMMITTER_EMAIL']

    # Group: Checkout git repository
    print_message('Checkout git repository', message_type='group')

    subprocess.run(
        [
            'git', 'fetch', '--prune', '--unshallow', 'origin',
            current_branch
        ]
    )
    subprocess.run(['git', 'checkout', current_branch])

    print_message('', message_type='endgroup')

    # Group: Configure Git
    print_message('Configure Git', message_type='group')

    subprocess.run(['git', 'config', 'user.name', username])
    subprocess.run(['git', 'config', 'user.email', email])

    print_message('', message_type='endgroup')

    print_message('Parse Configuration', message_type='group')

    config = ChangelogCIConfiguration(config_file)

    print_message('', message_type='endgroup')

    # Group: Generate Changelog
    print_message('Generate Changelog', message_type='group')

    # Initialize the Changelog PR
    ci = ChangelogCIPullRequest(
        repository,
        event_path,
        config,
        current_branch,
        filename=filename,
        token=token
    )
    # Run Changelog PR
    ci.run()

    print_message('', message_type='endgroup')
