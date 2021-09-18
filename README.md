![Changelog PR Banner](https://i.imgur.com/f5k5sTw.png)

![GitHub Workflow Status](https://img.shields.io/github/workflow/status/JonathanAquino/changelog-pr/Changelog%20CI?label=Changelog%20CI&style=flat-square)
[![GitHub](https://img.shields.io/github/license/JonathanAquino/changelog-pr?style=flat-square)](https://github.com/JonathanAquino/changelog-pr/blob/master/LICENSE)

## What is Changelog PR?

Changelog PR is a GitHub Action that enables a project to utilize an
automatically generated changelog. Unlike similar GitHub Actions, this tool
does not require the repo to implement SemVer - instead, each changelog entry
has a date. This can be useful for APIs which, unlike libraries, may not use SemVer.

The changelog looks like this:

## [#15](https://github.com/JonathanAquino/changelog-pr/pull/15) (2021-09-18)
- [enhancement] Include the skip_changelog_label in the instructional text for choosing a PR label

## [#14](https://github.com/JonathanAquino/changelog-pr/pull/14) (2021-09-18)
- [breaking-changes] Implement pr_title_removal_regex

## [#13](https://github.com/JonathanAquino/changelog-pr/pull/13) (2021-09-18)
- [enhancement] Modify the formatting of the changelog header

## How Does It Work?

Changelog PR uses `python` and the `GitHub API` to generate the changelog for a
repository. When a PR is merged to main/master, the action runs. First, it reads
the Last Generated On date from the changelog header. Then, it fetches the pull
requests merged after that date using the GitHub API. After that, it applies the
rules from the config for adding labels like "breaking-changes", removing parts
of the PR title like "[WIP]", or even skipping the PR if it has the "skip-changelog"
label. Finally, it writes the generated changelog at the beginning of
the `CHANGELOG.md` (or user-provided filename) file and commits it to main/master.

## Installation

1. To install this action, you need to copy the following two files into
the same places in your repo:

- [.github/workflows/changelog-pr.yaml](https://github.com/JonathanAquino/changelog-pr/blob/main/.github/workflows/changelog-pr.yaml)
- [changelog-pr-config.yaml](https://github.com/JonathanAquino/changelog-pr/blob/main/changelog-pr-config.yaml)

2. Follow the instructions in those files to tweak them.

3. Add a line to your pull request template (pull_request_template.md) to remind people
to set a label:

- [ ] Label your PR for the changelog: skip-changelog, breaking-changes, new-feature, enhancement, bug, implementation-changes

## Why Use Changelog PR Over git log?

The main value add of Changelog PR over just using git log is that it shows the all-important
label (breaking-changes, new-feature, bug, etc.).

You can also get the labels on the GitHub [Pull Requests page](https://github.com/JonathanAquino/changelog-pr/pulls?q=is%3Apr+is%3Amerged+)
but unfortunately it can't be sorted by merge date, only creation date.

## Why Use Changelog PR Over Changelog CI?

Changelog PR is a fork of the wonderful [Changelog CI](https://github.com/saadmk11/changelog-ci/)
GitHub action. The one reason to use Changelog PR over Changelog CI is if your repo does
not use SemVer.

If your repo is not SemVer-based (as many APIs are not), Changelog PR is preferred
because it automatically generates changelogs, assigning a date to each. With Changelog CI,
you need to add version numbers to your project, you need to remember to run Changelog CI
every couple of weeks, and when you run it you need to (a) remember all the PRs that were done
to decide whether it is a major version, minor version, or patch version (b) create an empty
PR titled Release 1.2.3 to trigger Changelog CI.

## When Not To Use Changelog PR

If your repo uses SemVer, you're better off using a GitHub action that can handle SemVer,
like https://github.com/saadmk11/changelog-ci/ (or writing your changelog manually).
If it does not, you're better off using Changelog PR (see Why Use Changelog PR? above).

## Caveats To Using Changelog PR

Changelog PR has some drawbacks that you might want to know:

1. The dates are in the UTC timezone. If you want a different timezone, you can fork this
   project and update the code.
2. In the rare case where two PRs are merged at the same time, there may be a race condition
   where one of the Changelog PR runs will fail to update the changelog.
3. Changelog PR queries the GitHub API for all merged PRs since the last run. If you are
   merging PRs to a feature branch, those PRs will be included in the changelog on the default
   branch.
4. You'll see in the instructions in [changelog-pr.yaml](https://github.com/JonathanAquino/changelog-pr/blob/main/.github/workflows/changelog-pr.yaml)
   that, if your main/master branch is protected, we use branch-protection-bot to turn off
   Include Administrators from branch protection temporarily while Changelog PR runs.
   This means that the branch will not be protected from admins for about a minute after
   you merge your PR.
5. Also if your main/master branch is protected, you'll see in [changelog-pr.yaml](https://github.com/JonathanAquino/changelog-pr/blob/main/.github/workflows/changelog-pr.yaml)
   that we ask you to use a Personal Access Token for an admin user. Unfortunately Changelog PR
   will run twice after you merge your PR: once for the PR merge and once for the changelog commit.
   For the regular GITHUB_TOKEN, GitHub Actions is smart enough to not trigger a new action.

## Acknowledgements

This project is a fork of the excellent [Changelog CI](https://github.com/saadmk11/changelog-ci/) project.
