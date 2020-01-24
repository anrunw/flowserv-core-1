# This file is part of the Reproducible Open Benchmarks for Data Analysis
# Platform (ROB).
#
# Copyright (C) 2019 NYU.
#
# ROB is free software; you can redistribute it and/or modify it under the
# terms of the MIT License; see LICENSE file for more details.

"""Basic information about workflow runs."""

from flowserv.model.workflow.resource import ResourceSet


class RunHandle(object):
    """The run handle provides access to the run state, error messages, and any
    resource files that have been generated by successful workflow runs.
    """
    def __init__(self, identifier, group_id, state, arguments, rundir):
        """Initialize the object properties.

        Parameters
        ----------
        identifier: string
            Unique run identifier
        group_id: string
            Unique identifier of the workflow group
        state: flowserv.model.workflow.state.WorkflowState
            Current workflow run state
        arguments: dict()
            Dictionary of user-provided argument values for the run
        rundir: string
            Path to the directory that contains run-related files
        """
        self.identifier = identifier
        self.group_id = group_id
        self.state = state
        self.arguments = arguments
        self.rundir = rundir

    def is_active(self):
        """A run is in active state if it is either pending or running.

        Returns
        --------
        bool
        """
        return self.state.is_active()

    def is_canceled(self):
        """Returns True if the workflow state is of type CANCELED.

        Returns
        -------
        bool
        """
        return self.state.is_canceled()

    def is_error(self):
        """Returns True if the workflow state is of type ERROR.

        Returns
        -------
        bool
        """
        return self.state.is_error()

    def is_pending(self):
        """Returns True if the workflow state is of type PENDING.

        Returns
        -------
        bool
        """
        return self.state.is_pending()

    def is_running(self):
        """Returns True if the workflow state is of type RUNNING.

        Returns
        -------
        bool
        """
        return self.state.is_running()

    def is_success(self):
        """Returns True if the workflow state is of type SUCCESS.

        Returns
        -------
        bool
        """
        return self.state.is_success()

    @property
    def messages(self):
        """Shortcut to access the list of error messages that are associated
        with a workflow run that is in canceled or error state.

        Returns
        -------
        flowserv.model.workflow.resource.ResourceSet
        """
        if not self.is_canceled() and not self.is_error():
            return list()
        else:
            return self.state.messages

    @property
    def resources(self):
        """Shortcut to access the set of resources that were generated by a
        successful workflow run.

        Returns
        -------
        flowserv.model.workflow.resource.ResourceSet
        """
        if not self.is_success():
            return ResourceSet()
        else:
            return self.state.resources

    def update_state(self, state):
        """Get a copy of the run handle with an update state.

        Parameters
        ----------
        state: flowserv.model.workflow.state.WorkflowState
            New run state object

        Returns
        -------
        flowserv.model.run.base.RunHandle
        """
        return RunHandle(
            identifier=self.identifier,
            group_id=self.group_id,
            state=state,
            arguments=self.arguments,
            rundir=self.rundir
        )
