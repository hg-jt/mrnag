#!/usr/bin/env python
from setuptools import find_packages, setup
from mrnag import __version__


with open("README.md", "r") as readme:
    long_description = readme.read()


setup(
    name='mrnag',
    version=__version__,
    description='Utilities for aggregating information about open merge requests.',
    long_description=long_description,
    packages=find_packages(exclude=['tests*']),
    install_requires=[
        'Flask==1.1.2',
        'inflect==4.1.0',
        'humanize==2.4.0',
        'pendulum==2.1.0',
        'PyYaml==5.3.1',
        'requests==2.23.0'
    ],
    test_suite='tests'
)
