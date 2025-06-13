## How to Manage Python, Its Dependencies and Its Environments

`uv` is the only tool required locally.

### Updating Dependencies and/or Python

To add/update/remove any dependencies and/or to upgrade Python, simply:
1. first add/update/remove such dependencies to/in/from the desired group(s) below `[project.optional-dependencies]` ("extras") in `pyproject.toml`, and/or upgrade Python itself in `.python-version`
  _⚠️ dependencies for the charm itself are also defined below `[project.optional-dependencies]` as extras, specifically in the `charm` section, and not below `[project]` as project dependencies (see above why) ⚠️_
2. then run:
    - either `uv lock` to just update your lock file
    - or alternatively `uv sync --extra <your-extra-a> --extra <your-extra-b>` (or `uv sync --all-extras`) if you also want to update your local environment together with your lock file, so that you will be able to run Python code from your `uv` environment locally using `uv run python3 <whatever>`

By point 2., `uv` will let you know if there are any dependency conflicts to solve.

### Running `tox` Environments

To run `tox` environments locally, just:
1. install `tox` as an `uv` tool together with the required `tox-uv` plugin: `uv tool install tox --with tox-uv`
2. make sure the specific tox managed by uv is found by default: `uv tool update-shell`
3. run `tox` as you would natively (e.g.: `tox -e lint`)

### Running Python Environments

To run Python commands/scripts locally from any environments with any combination of dependency extras, simply run `uv run --extra <your-extra-a> --extra <your-extra-b> python3 <whatever>` (or `uv sync --all-extras python3 <whatever>`)
