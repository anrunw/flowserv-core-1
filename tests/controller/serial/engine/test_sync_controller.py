# This file is part of the Reproducible and Reusable Data Analysis Workflow
# Server (flowServ).
#
# Copyright (C) 2019-2021 NYU.
#
# flowServ is free software; you can redistribute it and/or modify it under the
# terms of the MIT License; see LICENSE file for more details.

"""Unit tests for the synchronous mode of the serial workflow controller."""

import os

from flowserv.model.files import io_file
from flowserv.service.run.argument import serialize_arg, serialize_fh
from flowserv.tests.service import create_group, create_user, create_workflow, start_run, upload_file


import flowserv.model.workflow.state as st
import flowserv.tests.serialize as serialize


DIR = os.path.dirname(os.path.realpath(__file__))
BENCHMARK_DIR = os.path.join(DIR, '..', '..', '..', '.files', 'benchmark', 'helloworld')
# Workflow templates
TEMPLATE_WITH_INVALID_CMD = os.path.join(BENCHMARK_DIR, 'benchmark-invalid-cmd.yaml')


def test_run_helloworld_sync_error(sync_service):
    """Execute the helloworld example with erroneous command."""
    # -- Setup ----------------------------------------------------------------
    #
    # Start a new run for the workflow template.
    with sync_service() as api:
        workflow_id = create_workflow(
            api,
            source=BENCHMARK_DIR,
            specfile=TEMPLATE_WITH_INVALID_CMD
        )
        user_id = create_user(api)
    with sync_service(user_id=user_id) as api:
        group_id = create_group(api, workflow_id)
        names = io_file(data=['Alice', 'Bob'], format='plain/text')
        file_id = upload_file(api, group_id, names)
        args = [
            serialize_arg('names', serialize_fh(file_id, 'data/names.txt')),
            serialize_arg('sleeptime', 3)
        ]
        run_id = start_run(api, group_id, arguments=args)
    # -- Validate the run handle against the expected state -------------------
    with sync_service(user_id=user_id) as api:
        r = api.runs().get_run(run_id)
        serialize.validate_run_handle(r, state=st.STATE_ERROR)
        assert len(r['messages']) > 0


def test_run_helloworld_sync_success(sync_service):
    """Successfully execute the helloworld example."""
    # -- Setup ----------------------------------------------------------------
    #
    # Start a new run for the workflow template.
    with sync_service() as api:
        workflow_id = create_workflow(
            api,
            source=BENCHMARK_DIR
        )
        user_id = create_user(api)
    with sync_service(user_id=user_id) as api:
        group_id = create_group(api, workflow_id)
        names = io_file(data=['Alice', 'Bob'], format='plain/text')
        file_id = upload_file(api, group_id, names)
        args = [
            serialize_arg('names', serialize_fh(file_id, 'data/names.txt')),
            serialize_arg('sleeptime', 3)
        ]
        run_id = start_run(api, group_id, arguments=args)
    # -- Validate the run handle against the expected state -------------------
    with sync_service(user_id=user_id) as api:
        r = api.runs().get_run(run_id)
        serialize.validate_run_handle(r, state=st.STATE_SUCCESS)
        # The run should have the greetings.txt file as a result.
        files = dict()
        for obj in r['files']:
            files[obj['name']] = obj['id']
        assert len(files) == 2
        fh = api.runs().get_result_file(
            run_id=run_id,
            file_id=files['results/greetings.txt']
        )
        value = fh.open().read().decode('utf-8').strip()
        assert 'Hello Alice!' in value
        assert 'Hello Bob!' in value
