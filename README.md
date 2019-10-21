# Mr. Nag (mrnag)

*mrnag* aggregates merge requests across multiple projects.

More speficially *mrnag* provides utlitities for aggregating merge request data
for a collection of projects across one or more *forges*. The intention is to
support multiple forges, with GitLab being the focus of the initial
implementation.

> *Terminology*: In this context [forge] refers to a colloaborative web-based
> SCM tool (e.g. GitHub, GitLab, BitBucket, etc.).

*mrnag* works by taking a minimal project configuration and enriching it through
API calls to the associated forge. The result is a hydrated metadata object that
includes information about the project and it's merge requests. These projects
are then filtered and processed by a formatter to display/export the data.

[forge]: https://en.wikipedia.org/wiki/Forge_(software)


## Configuring Mr. Nag

*Mr. Nag* is configured with a YAML file. There are two section in the config
file: *Forges* and *Projects*.

The *forges* section of the config file defines the forges that Mr. Nag will use
to fetch projcet details. These configuration contain the API key/token required
by the individual forges. This can be expressed directly in the configuration
file or via an environment variable (e.g. if the forge type is "gitlab" and the
id is "abc, the API token environment variable would be `ABC_GITLAB_TOKEN`):

The *projects* section of the config file defines all of the projects that
Mr. Nag will report information about. The project configurations should include
a name for the project along with the minimal metadata need to use the Forge's
API (e.g. forge id, project id).


**Example Mr. Nag Configuration**:

```yaml
# config.yml --- Mr. Nag (mrnag) configuration file.
#
# Forge:
#  - id (str, required)
#  - type (string, required)
#  - api_url (string, required)
#  - token (string, optional)
#
# Project:
#  - project_id (int, required)
#  - forge (string, required)
#  - name (string, required)
forges:
  - id: abc
    type: gitlab
    api_url: https://abc-gitlab.yourdomain.com/api/v4
    token: xxxxxxxxxxxxxxxxxxxx

projects:
- forge: abc
  name: Foo Service
  project_id: 101
- forge: abc
  name: Bar App
  project_id: 16
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

### Project Dependencies

*mrnag* requires the following dependencies:

* [Python](https://www.python.org/) (3.7.x)

The following dependencies are optional:

* [PyEnv](https://github.com/yyuu/pyenv)

* [Virtualenv](https://virtualenv.pypa.io/)

* [Virtualenvwrapper](https://virtualenvwrapper.readthedocs.org/)


To install Python 3.7:

* Install pyenv

* Install Python

    ```sh
    cd mrnag
    pyenv install  # the Python version is defined in a file called .python-version
    ```

If you are using virtualenv/virtualenvwrapper:

```sh
mkvirtualenv -p $(pyenv which python3.7) mrnag -a .
```

Install Python dependencies:

```
pip install -r requirements.txt
```
