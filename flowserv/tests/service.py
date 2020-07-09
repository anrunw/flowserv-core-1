# This file is part of the Reproducible and Reusable Data Analysis Workflow
# Server (flowServ).
#
# Copyright (C) 2019-2020 NYU.
#
# flowServ is free software; you can redistribute it and/or modify it under the
# terms of the MIT License; see LICENSE file for more details.

"""Helper methods to initialize the API service object for test purposes."""

import os

from flowserv.tests.files import FakeStream

import flowserv.util as util


def create_group(api, workflow_id, users):
    """Create a new group for the given workflow.

    Parameters
    ----------
    api: flowserv.service.api.API
        Service API manager.
    workflow_id: string
        Unique workflow identifier.
    users: list(string)
        Identifier for group members.

    Returns
    -------
    string
    """
    doc = api.groups().create_group(
        workflow_id=workflow_id,
        name=util.get_unique_identifier(),
        user_id=users[0],
        members=users
    )
    return doc['id']


def create_ranking(api, workflow_id, user_id, count):
    """Create a ranking with n groups for the Hello World benchmark having a
    successful run each. Returns the group identifier in order of creation.
    The avg_len value is increased as groups are created and the max_len value
    is decreased.

    Parameters
    ----------
    api: flowserv.service.api.API
        Service API manager.
    workflow_id: string
        Unique workflow identifier.
    user_id: string
        Identifier for the group owner.
    count: int
        Number of groups that are created for the workflow.

    Returns
    -------
    list(string)
    """
    groups = list()
    for i in range(count):
        group_id = create_group(api, workflow_id=workflow_id, users=[user_id])
        # Start the new run. Then set it into SUCESS state.
        run_id, file_id = start_hello_world(api, group_id, user_id)
        data = {'avg_count': i, 'max_len': 100 - i, 'max_line': 'A'*i}
        write_results(
            api,
            run_id,
            [(data, None, 'results/analytics.json')]
        )
        api.runs().update_run(
            run_id=run_id,
            state=api.engine.success(
                run_id,
                files=['results/analytics.json']
            )
        )
        groups.append(group_id)
    return groups


def create_workflow(api, sourcedir, specfile=None):
    """Start a new workflow for a given template."""
    return api.workflows().create_workflow(
        name=util.get_unique_identifier(),
        sourcedir=sourcedir,
        specfile=specfile
    )['id']


def create_user(api):
    """Register a new user with the API and return the unique user identifier.

    Parameters
    ----------
    api: flowserv.service.api.API
        Service API manager.

    Returns
    -------
    string
    """
    user_name = util.get_unique_identifier()
    doc = api.users().register_user(
        username=user_name,
        password=user_name,
        verify=False
    )
    return doc['id']


def start_hello_world(api, group_id, user_id):
    """Start a new run for the Hello World template. Returns the run identifier
    and the identifier for the input file.

    Parameters
    ----------
    api: flowserv.service.api.API
        Service API manager.
    group_id: string
        Unique group identifier.
    user_id: string
        Unique user identifier.

    Returns
    -------
    string, string
    """
    file_id = api.uploads().upload_file(
        group_id=group_id,
        file=FakeStream(data=['Alice', 'Bob'], format='txt/plain'),
        name='n.txt',
        user_id=user_id
    )['id']
    run_id = api.runs().start_run(
        group_id=group_id,
        arguments=[{'id': 'names', 'value': file_id}],
        user_id=user_id
    )['id']
    api.engine.start(run_id)
    return run_id, file_id


def start_run(api, group_id, user_id, arguments=None):
    return api.runs().start_run(
        group_id=group_id,
        arguments=arguments,
        user_id=user_id
    )['id']


def upload_file(api, group_id, user_id, file):
    return api.uploads().upload_file(
        group_id=group_id,
        file=file,
        name=util.get_short_identifier(),
        user_id=user_id
    )['id']


def write_results(api, run_id, files):
    """Create a reult file for a given workflow run.


    Parameters
    ----------
    api: flowserv.service.api.API
        Service API manager.
    run_id: string
        Unique run identifier.
    files: list
        List of 3-tuples containing the file data, format, and relative path.
    """
    run = api.run_manager.get_run(run_id)
    for data, format, rel_path in files:
        filename = os.path.join(run.get_rundir(), rel_path)
        FakeStream(data=data, format=format).save(filename)
