# This file is part of the Reproducible and Reusable Data Analysis Workflow
# Server (flowServ).
#
# Copyright (C) 2019-2021 NYU.
#
# flowServ is free software; you can redistribute it and/or modify it under the
# terms of the MIT License; see LICENSE file for more details.

"""Unit tests for the abstract container engine class."""

from typing import Dict

from flowserv.controller.serial.workflow.result import ExecResult
from flowserv.controller.worker.base import ContainerEngine
from flowserv.model.workflow.step import ContainerStep


class ContainerTestEngine(ContainerEngine):
    def __init__(self, variables: Dict):
        super(ContainerTestEngine, self).__init__(variables=variables)
        self.commands = None

    def run(self, step: ContainerStep, env: Dict, rundir: str) -> ExecResult:
        self.commands = step.commands


def test_fixed_variables():
    """Test proper behavior for setting fixed variables in the worker environment."""
    step = ContainerStep(image='test', commands=['${python} $run $me'])
    arguments = {'run': 'my_model.py', 'me': 1}
    engine = ContainerTestEngine(variables=dict())
    engine.exec(step=step, arguments=arguments, rundir='/dev/null')
    assert engine.commands == ['python my_model.py 1']
    engine = ContainerTestEngine(variables={'run': 'static.py'})
    engine.exec(step=step, arguments=arguments, rundir='/dev/null')
    assert engine.commands == ['python static.py 1']
