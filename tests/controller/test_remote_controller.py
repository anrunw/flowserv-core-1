# This file is part of the Reproducible and Reusable Data Analysis Workflow
# Server (flowServ).
#
# Copyright (C) 2019-2020 NYU.
#
# flowServ is free software; you can redistribute it and/or modify it under the
# terms of the MIT License; see LICENSE file for more details.

"""Unit tests for the generic remote workflow engine controller."""

import os
import pytest
import time

from flowserv.config.api import FLOWSERV_API_BASEDIR
from flowserv.config.database import FLOWSERV_DB
from flowserv.service.api import service
from flowserv.tests.remote import RemoteTestClient, RemoteTestController
from flowserv.tests.service import (
    create_group, create_user, create_workflow, start_run
)

import flowserv.model.workflow.state as st
import flowserv.tests.serialize as serialize


# Template directory
DIR = os.path.dirname(os.path.realpath(__file__))
TEMPLATE_DIR = os.path.join(DIR, '../.files/benchmark/remote')


def test_cancel_remote_workflow(tmpdir):
    """Cancel the execution of a remote workflow."""
    # -- Setup ----------------------------------------------------------------
    #
    # Start a new run for the workflow template.
    os.environ[FLOWSERV_DB] = 'sqlite:///{}/flowserv.db'.format(str(tmpdir))
    os.environ[FLOWSERV_API_BASEDIR] = str(tmpdir)
    from flowserv.service.database import database
    database.__init__()
    database.init()
    engine = RemoteTestController(
        client=RemoteTestClient(runcount=100),
        poll_interval=1,
        is_async=True
    )
    with service(engine=engine) as api:
        workflow_id = create_workflow(api, source=TEMPLATE_DIR)
        user_id = create_user(api)
        group_id = create_group(api, workflow_id, [user_id])
        run_id = start_run(api, group_id, user_id)
    # Poll workflow state every second.
    with service(engine=engine) as api:
        run = api.runs().get_run(run_id=run_id, user_id=user_id)
    while run['state'] == st.STATE_PENDING:
        time.sleep(1)
        with service(engine=engine) as api:
            run = api.runs().get_run(run_id=run_id, user_id=user_id)
    serialize.validate_run_handle(run, state=st.STATE_RUNNING)
    with service(engine=engine) as api:
        api.runs().cancel_run(run_id=run_id, user_id=user_id, reason='test')
    # Sleep to ensure that the workflow monitor polls the state and makes an
    # attempt to update the run state. This should raise an error for the
    # monitor. The error is not propagated here or to the run.
    time.sleep(3)
    with service(engine=engine) as api:
        run = api.runs().get_run(run_id=run_id, user_id=user_id)
    serialize.validate_run_handle(run, state=st.STATE_CANCELED)
    assert run['messages'][0] == 'test'


@pytest.mark.parametrize('is_async', [False, True])
def test_run_remote_workflow(tmpdir, is_async):
    """Execute the remote workflow example synchronized and in asynchronous
    mode.
    """
    # -- Setup ----------------------------------------------------------------
    #
    # Start a new run for the workflow template.
    os.environ[FLOWSERV_DB] = 'sqlite:///{}/flowserv.db'.format(str(tmpdir))
    os.environ[FLOWSERV_API_BASEDIR] = str(tmpdir)
    from flowserv.service.database import database
    database.__init__()
    database.init()
    engine = RemoteTestController(
        client=RemoteTestClient(runcount=3, data=['success']),
        poll_interval=1,
        is_async=is_async
    )
    with service(engine=engine) as api:
        workflow_id = create_workflow(api, source=TEMPLATE_DIR)
        user_id = create_user(api)
        group_id = create_group(api, workflow_id, [user_id])
        run_id = start_run(api, group_id, user_id)
    # Poll workflow state every second.
    with service(engine=engine) as api:
        run = api.runs().get_run(run_id=run_id, user_id=user_id)
    count = 0
    while run['state'] in st.ACTIVE_STATES and count < 60:
        time.sleep(1)
        count += 1
        with service(engine=engine) as api:
            run = api.runs().get_run(run_id=run_id, user_id=user_id)
    serialize.validate_run_handle(run, state=st.STATE_SUCCESS)
    files = dict()
    for obj in run['files']:
        files[obj['name']] = obj['id']
    f_id = files['results/data.txt']
    fh = api.runs().get_result_file(
        run_id=run_id,
        file_id=f_id,
        user_id=user_id
    )
    data = fh.open().read().decode('utf-8')
    assert 'success' in data


def test_run_remote_workflow_with_error(tmpdir):
    """Execute the remote workflow example that will end in an error state in
    asynchronous mode.
    """
    # -- Setup ----------------------------------------------------------------
    #
    # Start a new run for the workflow template.
    os.environ[FLOWSERV_DB] = 'sqlite:///{}/flowserv.db'.format(str(tmpdir))
    os.environ[FLOWSERV_API_BASEDIR] = str(tmpdir)
    from flowserv.service.database import database
    database.__init__()
    database.init()
    engine = RemoteTestController(
        client=RemoteTestClient(runcount=3, error='some error'),
        poll_interval=1,
        is_async=True
    )
    with service(engine=engine) as api:
        workflow_id = create_workflow(api, source=TEMPLATE_DIR)
        user_id = create_user(api)
        group_id = create_group(api, workflow_id, [user_id])
        run_id = start_run(api, group_id, user_id)
    # Poll workflow state every second.
    with service(engine=engine) as api:
        run = api.runs().get_run(run_id=run_id, user_id=user_id)
    while run['state'] in st.ACTIVE_STATES:
        time.sleep(1)
        with service(engine=engine) as api:
            run = api.runs().get_run(run_id=run_id, user_id=user_id)
    serialize.validate_run_handle(run, state=st.STATE_ERROR)
    assert run['messages'][0] == 'some error'
