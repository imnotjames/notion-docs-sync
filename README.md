# Notion Documentation Sync

Synchronizes documentation files to [Notion.so](https://notion.so).
Reads in files as files & Markdown, converting them to Notion pages & blocks.

## Usage

### Command Line

Run with Poetry:

```bash
poetry run notion-docs-sync --notion-token $NOTION_TOKEN $DOCS_PATH $NOTION_URL
```

### Getting a Notion Token

The Notion token is stored in cookies during an authentication as `token_v2`.
This can be retrieved in Firefox with the [Storage Inspector][firefox-storage-inspector]
or in Chrome with the [Chrome DevTools Application tab.][chrome-devtools]

The value of this can be used to make changes to your account as well as
any workspace you have access to.  There does not seem to be an easy way to
invalidate this token so however you end up storing it, keep it secure!

### Github Actions

**Warning:** If you include the Notion token directly in your workflow definition
you will be allowing anyone with access to the repository to act on your behalf in
Notion.  Use the [Github Repository Secrets][gh-secrets] feature!

#### Inputs

* `docs_path` - The path that should be published to Notion.
* `notion_url` - The URL to a page in Notion that serves as the root of the documentation.
* `notion_token` - The Notion Access token to use for publishing.

#### Example Workflow

Create a Workflow with the following definition:

```
on:
  push:
    branches:
      - master

jobs:
  release:
    timeout-minutes: 10
    runs-on: ubuntu-latest
    steps:
        - uses: actions/checkout@v2

        - name: Notion Documentation Sync
          uses: imnotjames/notion-docs-sync@latest
          with:
            docs_path: ./docs/
            notion_url: ${{ secrets.NOTION_URL }}
            notion_token: ${{ secrets.NOTION_TOKEN }}
```

[gh-secrets]: https://help.github.com/en/actions/configuring-and-managing-workflows/creating-and-storing-encrypted-secrets
[firefox-storage-inspector]: https://developer.mozilla.org/en-US/docs/Tools/Storage_Inspector
[chrome-devtools]: https://developers.google.com/web/tools/chrome-devtools/storage/cookies
