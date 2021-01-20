# This file is part of the Reproducible and Reusable Data Analysis Workflow
# Server (flowServ).
#
# Copyright (C) 2019-2020 NYU.
#
# flowServ is free software; you can redistribute it and/or modify it under the
# terms of the MIT License; see LICENSE file for more details.

"""Implementation of a workflow controller for serial workflows that uses the
local Docker daemon to execute workflow steps.
"""

from typing import Optional

import logging
import os

from flowserv.controller.serial.engine import SerialWorkflowEngine
from flowserv.service.api import APIFactory

import flowserv.model.workflow.state as serialize
import flowserv.util as util


class DockerWorkflowEngine(SerialWorkflowEngine):
    """The docker workflow engine is used to execute workflow templates for a
    given set of arguments using docker containers.

    the engine extends the multi-process controller for asynchronous execution.
    Workflow runs are executed by the docker_run() function.
    """
    def __init__(self, service: Optional[APIFactory] = None):
        """Initialize the super class using the docker_run execution function.

        Parameters
        ----------
        service: flowserv.service.api.APIFactory, default=None
            API factory for service callbach during asynchronous workflow
            execution.
        """
        super(DockerWorkflowEngine, self).__init__(
            service=service,
            exec_func=docker_run
        )


# -- Workflow execution function ----------------------------------------------


def docker_run(run_id, rundir, state, output_files, steps):  # pragma: no cover
    """Execute a list of workflow steps synchronously using the Docker engine.

    Returns a tuple containing the run identifier, the folder with the run
    files, and a serialization of the workflow state.

    Parameters
    ----------
    run_id: string
        Unique run identifier
    rundir: string
        Path to the working directory of the workflow run
    state: flowserv.model.workflow.state.WorkflowState
        Current workflow state (to access the timestamps)
    output_files: list(string)
        Relative path of output files that are generated by the workflow run
    steps: list(flowserv.model.template.step.Step)
        List of expanded workflow steps from a template workflow specification

    Returns
    -------
    (string, string, dict)
    """
    logging.debug('start docker run {}'.format(run_id))
    # Setup the workflow environment by obtaining volume information for all
    # directories in the run folder.
    volumes = dict()
    for filename in os.listdir(rundir):
        abs_file = os.path.abspath(os.path.join(rundir, filename))
        if os.path.isdir(abs_file):
            volumes[abs_file] = {'bind': '/{}'.format(filename), 'mode': 'rw'}
    # Run the individual workflow steps using the local Docker deamon. Import
    # docker package here to avoid errors for installations that do not intend
    # to use Docker and therefore did not install the package.
    import docker
    from docker.errors import ContainerError, ImageNotFound, APIError
    client = docker.from_env()
    try:
        for step in steps:
            for cmd in step.commands:
                logging.info('{}'.format(cmd))
                client.containers.run(
                    image=step.env,
                    command=cmd,
                    volumes=volumes
                )
    except (ContainerError, ImageNotFound, APIError) as ex:
        logging.error(ex)
        strace = util.stacktrace(ex)
        logging.debug('\n'.join(strace))
        result_state = state.error(messages=strace)
        return run_id, rundir, serialize.serialize_state(result_state)
    # Create list of output files that were generated.
    files = list()
    for relative_path in output_files:
        if os.path.exists(os.path.join(rundir, relative_path)):
            files.append(relative_path)
    # Workflow executed successfully
    result_state = state.success(files=files)
    logging.debug('finished run {} = {}'.format(run_id, result_state.type_id))
    return run_id, rundir, serialize.serialize_state(result_state)
