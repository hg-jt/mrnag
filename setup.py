#!/usr/bin/env python
from setuptools import find_packages, setup


with open("README.md", "r") as readme:
    long_description = readme.read()


setup(
    name='mrnag',
    version='1.0.0.dev0',
    description='Utilities for aggregating information about open merge requests.',
    long_description=long_description,
    packages=find_packages(exclude=['tests*']),
    install_requires=[
        'pendulum==2.0.5',
        'PyYaml==5.1.2',
        'requests==2.22.0'
    ],
    test_suite='tests'
)
