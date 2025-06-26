## How to Manage Python Dependencies and Environments

`poetry` and optionally `tox` are the only tools required locally. `poetry` is required both to manage dependencies and to run `tox` environments (as `tox` internally relies on `poetry` to run its environments), while `tox` is only required to the latter purpose. Refer to the respective official docs for [installing poetry](https://python-poetry.org/docs/#installation) and [installing tox](https://tox.wiki/en/latest/installation.html).


### Updating Dependencies

To add/update/remove any dependencies and/or to upgrade Python, simply:

1. first add/update/remove such dependencies to/in/from the desired group(s) below `[tool.poetry.group.<your-group>.dependencies]` in `pyproject.toml`, and/or upgrade Python itself in `requires-python` under `[project]`

    _⚠️ dependencies for the charm itself are also defined as dependencies of a dedicated group called `charm`, specifically below `[tool.poetry.group.charm.dependencies]`, and not as project dependencies below `[project.dependencies]` or `[tool.poetry.dependencies]` ⚠️_

2. then run `poetry lock --regenerate` to update your lock file

3. optionally, if you also want to update your local environment for running Python commands/scripts, see [Running Python Environments](#running-python-environments) below

By point 2., `poerty` will let you know if there are any dependency conflicts to solve.


### Running `tox` Environments

To run `tox` environments locally, ensure to have both `poetry` and `tox` installed first and then simply run your `tox` environments natively (e.g.: `tox -e lint`). `tox` will internally rely on `poetry` to install and run its environments.


### Running Python Environments

To run Python commands/scripts locally from any environments built from any combinations of dependency groups:
1. install any dependency groups that compose the environment of interest: `poetry install --only <your-group-a>,<your-group-b>` (or all groups, if you prefer: `poetry install --all-groups`)
2. run Python commands/scripts via poetry: `poetry run python3 <whatever>`