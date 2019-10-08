# Mr. Nag (mrnag)

*mrnag* aggregates merge requests across multiple projects.

More speficially *mrnag* provides utlitities for aggregating merge request data
for a collection of projects across one or more *forges*. The intention is to
support multiple forges, with GitLab being the focus of the initial
implementation.

> *Terminology*: In this context [forge] refers to a colloaborative web-based
> SCM tool (e.g. GitHub, GitLab, BitBucket, etc.).

*mrnag* works by taking a minimal project configuration and enriching it through
a API calls to the associated forge. The result is a hydrated metadata object
that includes information about the project and it's merge requests. These
projects are then filtered and processed by a formatter to display/export the
data.

[forge]: https://en.wikipedia.org/wiki/Forge_(software)


## Before You Begin

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
