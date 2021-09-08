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
        pull_request_branch,
        filename='CHANGELOG.md',
        token=None
    ):
        self.repository = repository
        self.filename = filename
        self.config = config
        self.pull_request_branch = pull_request_branch
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

        subprocess.run(['git', 'add', self.filename])
        subprocess.run(
            ['git', 'commit', '-m', '(Changelog PR) Added Changelog']
        )
        subprocess.run(
            ['git', 'push', '-u', 'origin', self.pull_request_branch]
        )

    def run(self):
        """Entrypoint to the Changelog PR"""
        version = '9.9.9'

        if not version:
            # if the pull request title is not valid, exit the method
            # It might happen if the pull request is not meant to be release
            # or the title was not accurate.
            msg = (
                f'Could not find matching version number. '
                f'Regex tried: {self.config.version_regex} '
                f'Aborting Changelog Generation'
            )
            print_message(msg, message_type='error')
            return

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

    @staticmethod
    def _get_changelog_line(item):
        """Generate each line of changelog"""
        return "* [#{number}]({url}): {title}\n".format(
            number=item['number'],
            url=item['url'],
            title=item['title']
        )

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
        """Parse the pull requests data and return a string"""
        string_data = (
            '# ' + self.config.header_prefix + ' ' + version + '\n\n'
        )

        group_config = self.config.group_config

        if group_config:
            for config in group_config:

                if len(changes) == 0:
                    break

                items_string = ''

                for pull_request in changes:
                    # check if the pull request label matches with
                    # any label of the config
                    if (
                        any(
                            label in pull_request['labels']
                            for label in config['labels']
                        )
                    ):
                        items_string += self._get_changelog_line(pull_request)
                        # remove the item so that one item
                        # does not match multiple groups
                        changes.remove(pull_request)

                if items_string:
                    string_data += '\n#### ' + config['title'] + '\n\n'
                    string_data += '\n' + items_string

            if changes:
                # if they do not match any user provided group
                # Add items in `Other Changes` group
                string_data += '\n#### Other Changes\n\n'
                string_data += ''.join(
                    map(self._get_changelog_line, changes)
                )
        else:
            # If group config does not exist then append it without and groups
            string_data += ''.join(
                map(self._get_changelog_line, changes)
            )

        return string_data


class ChangelogCICommitMessage(ChangelogCIBase):
    """Generates and commits changelog using commit messages"""

    @staticmethod
    def _get_changelog_line(item):
        """Generate each line of changelog"""
        return "* [{sha}]({url}): {message}\n".format(
            sha=item['sha'][:6],
            url=item['url'],
            message=item['message']
        )

    def get_changes_after_last_release(self):
        """Get all the merged pull request after latest release"""
        previous_release_date = self._get_latest_release_date()

        url = '{base_url}/repos/{repo_name}/commits?since={date}'.format(
            base_url=self.github_api_url,
            repo_name=self.repository,
            date=previous_release_date or ''
        )

        items = []

        response = requests.get(url, headers=self._get_request_headers)

        if response.status_code == 200:
            response_data = response.json()

            if len(response_data) > 0:
                for item in response_data:
                    message = item['commit']['message']
                    # Exclude merge commit
                    if not (
                        message.startswith('Merge pull request #') or
                        message.startswith('Merge branch')
                    ):
                        data = {
                            'sha': item['sha'],
                            'message': message,
                            'url': item['html_url']
                        }
                        items.append(data)
                    else:
                        print_message(f'Skipping Merge Commit "{message}"')
            else:
                msg = (
                    f'There was no commit '
                    f'made on {self.repository} after last release.'
                )
                print_message(msg, message_type='error')
        else:
            msg = (
                f'Could not get commits for '
                f'{self.repository} from GitHub API. '
                f'response status code: {response.status_code}'
            )
            print_message(msg, message_type='error')

        return items

    def parse_changelog(self, version, changes):
        """Parse the commit data and return a string"""
        string_data = (
            '# ' + self.config.header_prefix + ' ' + version + '\n\n'
        )
        string_data += ''.join(map(self._get_changelog_line, changes))

        return string_data


class ChangelogCIConfiguration:
    """Configuration class for Changelog PR"""

    # The regular expression used to extract semantic versioning is a
    # slightly less restrictive modification of
    # the following regular expression
    # https://semver.org/#is-there-a-suggested-regular-expression-regex-to-check-a-semver-string
    DEFAULT_SEMVER_REGEX = (
        r"v?(0|[1-9]\d*)\.(0|[1-9]\d*)\.?(0|[1-9]\d*)?(?:-(("
        r"?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*)(?:\.(?:0|["
        r"1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*))*))?(?:\+(["
        r"0-9a-zA-Z-]+(?:\.[0-9a-zA-Z-]+)*))?"
    )
    DEFAULT_VERSION_PREFIX = "Version:"
    DEFAULT_GROUP_CONFIG = []
    # Changelog types
    PULL_REQUEST = 'pull_request'
    COMMIT = 'commit_message'

    def __init__(self, config_file):
        # Initialize with default configuration
        self.header_prefix = self.DEFAULT_VERSION_PREFIX
        self.version_regex = self.DEFAULT_SEMVER_REGEX
        self.changelog_type = self.PULL_REQUEST
        self.group_config = self.DEFAULT_GROUP_CONFIG

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

        self.validate_header_prefix()
        self.validate_commit_changelog()
        self.validate_version_regex()
        self.validate_changelog_type()
        self.validate_group_config()

    def validate_header_prefix(self):
        """Validate and set header_prefix configuration option"""
        header_prefix = self.user_raw_config.get('header_prefix')

        if not header_prefix or not isinstance(header_prefix, str):
            msg = (
                '`header_prefix` was not provided or not valid, '
                f'falling back to `{self.header_prefix}`.'
            )
            print_message(msg, message_type='warning')
        else:
            self.header_prefix = header_prefix

    def validate_version_regex(self):
        """Validate and set validate_version_regex configuration option"""
        version_regex = self.user_raw_config.get('version_regex')

        if not version_regex:
            msg = (
                '`version_regex` is not provided, '
                f'Falling back to {self.version_regex}.'
            )
            print_message(msg, message_type='warning')
            return

        try:
            # This will raise an error if the provided regex is not valid
            re.compile(version_regex)
            self.version_regex = version_regex
        except Exception:
            msg = (
                '`version_regex` is not valid, '
                f'Falling back to {self.version_regex}.'
            )
            print_message(msg, message_type='warning')

    def validate_changelog_type(self):
        """Validate and set changelog_type configuration option"""
        changelog_type = self.user_raw_config.get('changelog_type')

        if not (
            changelog_type and
            isinstance(changelog_type, str) and
            changelog_type in [self.PULL_REQUEST, self.COMMIT]
        ):
            msg = (
                '`changelog_type` was not provided or not valid, '
                f'the options are "{self.PULL_REQUEST}" or "{self.COMMIT}", '
                f'falling back to default value of "{self.changelog_type}".'
            )
            print_message(msg, message_type='warning')
        else:
            self.changelog_type = changelog_type

    def validate_group_config(self):
        """Validate and set group_config configuration option"""
        group_config = self.user_raw_config.get('group_config')

        if not group_config:
            msg = '`group_config` was not provided'
            print_message(msg, message_type='warning')
            return

        if not isinstance(group_config, list):
            msg = '`group_config` is not valid, It must be an Array/List.'
            print_message(msg, message_type='error')
            return

        for item in group_config:
            self.validate_group_config_item(item)

    def validate_group_config_item(self, item):
        """Validate and set group_config item configuration option"""
        if not isinstance(item, dict):
            msg = (
                '`group_config` items must have key, '
                'value pairs of `title` and `labels`'
            )
            print_message(msg, message_type='error')
            return

        title = item.get('title')
        labels = item.get('labels')

        if not title or not isinstance(title, str):
            msg = (
                '`group_config` item must contain string title, '
                f'but got `{title}`'
            )
            print_message(msg, message_type='error')
            return

        if not labels or not isinstance(labels, list):
            msg = (
                '`group_config` item must contain array of labels, '
                f'but got `{labels}`'
            )
            print_message(msg, message_type='error')
            return

        if not all(isinstance(label, str) for label in labels):
            msg = (
                '`group_config` labels array must be string type, '
                f'but got `{labels}`'
            )
            print_message(msg, message_type='error')
            return

        self.group_config.append(item)


def print_message(message, message_type=None):
    """Helper function to print colorful outputs in GitHub Actions shell"""
    # https://docs.github.com/en/actions/reference/workflow-commands-for-github-actions
    if not message_type:
        return subprocess.run(['echo', f'{message}'])

    if message_type == 'endgroup':
        return subprocess.run(['echo', '::endgroup::'])

    return subprocess.run(['echo', f'::{message_type}::{message}'])


CHANGELOG_PR_CLASSES = {
    ChangelogCIConfiguration.PULL_REQUEST: ChangelogCIPullRequest,
    ChangelogCIConfiguration.COMMIT: ChangelogCICommitMessage
}


if __name__ == '__main__':
    # Default environment variable from GitHub
    # https://docs.github.com/en/actions/configuring-and-managing-workflows/using-environment-variables
    event_path = os.environ['GITHUB_EVENT_PATH']
    repository = os.environ['GITHUB_REPOSITORY']
    pull_request_branch = os.environ['GITHUB_HEAD_REF']
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
            pull_request_branch
        ]
    )
    subprocess.run(['git', 'checkout', pull_request_branch])

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
    # Get CI class using configuration
    changelog_pr_class = CHANGELOG_PR_CLASSES.get(
        config.changelog_type
    )

    # Initialize the Changelog PR
    ci = changelog_pr_class(
        repository,
        event_path,
        config,
        pull_request_branch,
        filename=filename,
        token=token
    )
    # Run Changelog PR
    ci.run()

    print_message('', message_type='endgroup')
