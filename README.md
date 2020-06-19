# Mr. Nag (mrnag)

*mrnag* aggregates merge requests across multiple projects.

More speficially *mrnag* provides utlitities for aggregating merge request data
for a collection of projects across one or more *forges*. The intention is to
support multiple forges, with GitLab being the focus of the initial
implementation.

> *Terminology*: In this context [forge] refers to a collaborative web-based
> SCM tool (e.g. GitHub, GitLab, BitBucket, etc.).

*mrnag* works by taking a minimal project configuration and enriching it through
API calls to the associated forge. The result is a hydrated metadata object that
includes information about the project and it's merge requests. These projects
are then filtered and processed by a formatter to display/export the data.

In addtion to providing a collection of utilities, *mrnag* includes a CLI and a
web service implementation intended to be used as an integration point with a
Slack "slash command".

[forge]: https://en.wikipedia.org/wiki/Forge_(software)


## Configuring Mr. Nag

*Mr. Nag* is configured with a YAML file that describes a collection of *Forges*
and the projects within that forge.

Each *forge* entry contains some metadata about the forge and a list of
projects. The metadata contains the API key/token required by the individual
forges. This can be expressed directly in the configuration file or via an
environment variable (e.g. if the forge type is "gitlab" and the id is "abc, the
API token environment variable would be `ABC_GITLAB_TOKEN`):

The *projects* entries define all of the projects that Mr. Nag will report
information about. The project configurations should include a name for the
project along with the minimal metadata needed to use the Forge's API
(e.g. project id).


**Example Mr. Nag Configuration**:

```yaml
# config.yml --- Mr. Nag (mrnag) configuration file.
#
# Forge:
#  - id (str, required)
#  - type (string, required)
#  - api_url (string, required)
#  - token (string, optional)
#  - projects (list, optional)
#
# Project:
#  - project_id (int, required)
#  - name (string, required)
forges:
  - id: abc
    type: gitlab
    api_url: https://abc-gitlab.yourdomain.com/api/v4
    token: xxxxxxxxxxxxxxxxxxxx
    projects:
    - name: Foo Service
      project_id: 101
    - name: Bar App
      project_id: 16
  - id: github
    type github
    api_url: https://api.github.com
    token: xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
    project:
      - name: Project
        project_id: ?
```


## Using Mr. Nag

### Running Mr. Nag With Docker

*Mr. Nag* is packaged as a Docker image and hosted from Docker Hub.

To run the Mr. Nag docker image, you will need to provide a configuration
file. Since the application is running inside a container, the easiest way to
accomplish this is to create a configuration file in a local directory and mount
that directory to some location in the container. For example, if you have a
config file called `config.yml` in your home directory, you could run Mr. Nag
with the following command:

```sh
docker run --rm -it -v ~:/data hgjt/mrnag:latest -c /data/config.yml
```

Stepping through this command:

* The `--rm` will remove the container when the command is done executing
* The `-it` ensures that Mr. Nag is being run interactively
* The `-v ~:/data` is mounting your local home directory to */data* in the container
* `hgjt/mrnag:latest` is referencing the *latest* build of the Mr. Nag docker
  image. This is built from the *develop* branch as changes are pushed/merged.
* `-c /data/config.yml` is referencing the config file that is mounted inside
  the container.
* Any other CLI options can be appended to this command.

> *TIP*: To see the Mr. Nag usage screen, run this command, but replace the `-c
> /data/config.yml` with `-h`.


## Configuring Your Development Environment

*mrnag* requires the 3.7 (or newer).


### To Install Python:

* Install [pyenv](https://github.com/yyuu/pyenv)

    On OS X with [Homebrew]:

    ```sh
    brew update
    brew install pyenv
    ```

    For other platforms, see the [pyenv] installation instructions.

* Configure *pyenv*

    To enable *pyenv*, you need to add the following to your shell configuration
    (*~/.bash_profile* or *.bashrc* for bash or *~/.zshrc* for zsh):

    ```sh
    eval "$(pyenv init -)"
    ```

    > *NOTE*: The pyenv configuration shuould be added towards the end of your
    > shell configuration file to ensure that the pyenv shims are added to the
    > front of your configured `PATH`. See the [Basic GitHub Checkout] section
    > in pyenv's documentation for more information about shell configuration.

* Install the version of Python defined in the *.python-version* file.

    ```sh
    cd mrnag
    pyenv install  # the Python version is defined in a file called .python-version
    ```

### Install Project Dependencies

* Create a project specific virtual environment to isolate dependencies

    Use the built-in [venv] module to create a local directory called "venv"
    with all project dependencies:
    
    ```sh
    python -m venv --prompt mrnag venv
    ```

    The project's virtual environment can be activated by sourcing the
    `activate` script that matches your shell. For example when using bash/zsh,
    run:

    ```sh
    source venv/bin/activate
    ```

* Upgrade Pip

    ```sh
    pip install --upgrade pip
    ```

* Install Python dependencies:

    ```sh
    pip install -r requirements.txt
    ```

[Homebrew]: https://brew.sh/
[pyenv]: https://github.com/yyuu/pyenv
[Basic GitHub Checkout]: https://github.com/pyenv/pyenv#basic-github-checkout
[venv]: https://docs.python.org/3/tutorial/venv.html
