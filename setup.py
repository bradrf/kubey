#!/usr/bin/env python
# -*- coding: utf-8 -*-

from setuptools import setup

with open('README.rst') as readme_file:
    readme = readme_file.read()

with open('HISTORY.rst') as history_file:
    history = history_file.read()

requirements = [
    'click>=6.7',
    'tabulate>=0.7.7',
    'configstruct>=0.3.0',
    'jmespath>=0.9.2',
]

test_requirements = [
    # TODO: put package test requirements here
]

setup(
    name='kubey',
    version='0.1.0',
    description="Simple wrapper to help find specific Kubernetes pods and containers and run asynchronous commands.",
    long_description=readme + '\n\n' + history,
    author="Brad Robel-Forrest",
    author_email='brad@bitpony.com',
    url='https://github.com/bradrf/kubey',
    packages=[
        'kubey',
    ],
    package_dir={'kubey':
                 'kubey'},
    entry_points={
        'console_scripts': [
            'kubey=kubey.cli:cli'
        ]
    },
    include_package_data=True,
    install_requires=requirements,
    license="MIT license",
    zip_safe=False,
    keywords='kubey',
    classifiers=[
        'Development Status :: 2 - Pre-Alpha',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: MIT License',
        'Natural Language :: English',
        "Programming Language :: Python :: 2",
        'Programming Language :: Python :: 2.7',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.3',
        'Programming Language :: Python :: 3.4',
        'Programming Language :: Python :: 3.5',
        'Programming Language :: Python :: 3.6',
    ],
    test_suite='tests',
    tests_require=test_requirements
)
