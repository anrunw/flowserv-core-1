# This file is part of the Reproducible and Reusable Data Analysis Workflow
# Server (flowServ).
#
# Copyright (C) 2019-2020 NYU.
#
# flowServ is free software; you can redistribute it and/or modify it under the
# terms of the MIT License; see LICENSE file for more details.

"""The workflow API component provides methods to create and access workflows
and workflow result rankings.
"""

import flowserv.error as err


class WorkflowService(object):
    """API component that provides methods to access workflows and workflow
    evaluation rankings (benchmark leader boards).
    """
    def __init__(
        self, workflow_repo, ranking_manager, run_manager, serializer=None
    ):
        """Initialize the internal reference to the workflow repository, the
        ranking manager, and the resource serializer.

        Parameters
        ----------
        con: DB-API 2.0 database connection
            Connection to underlying database
        workflow_repo: flowserv.model.workflow.manager.WorkflowManager
            Repository to access registered workflows
        ranking_manager: flowserv.model.ranking.RankingManager
            Manager for workflow evaluation rankings
        run_manager: flowserv.model.run.RunManager
            Manager for workflow runs. The run manager is used to access
            prost-processing runs.
        serializer: flowserv.view.workflow.WorkflowSerializer, default=None
            Override the default serializer
        """
        self.workflow_repo = workflow_repo
        self.ranking_manager = ranking_manager
        self.run_manager = run_manager
        self.serialize = serializer

    def create_workflow(
        self, name, description=None, instructions=None, sourcedir=None,
        repourl=None, specfile=None
    ):
        """Create a new workflow in the repository. If the workflow template
        includes a result schema the workflow is also registered with the
        ranking manager.

        Raises an error if the given workflow name is not unique.

        Parameters
        ----------
        name: string
            Unique workflow name
        description: string, optional
            Optional short description for display in workflow listings
        instructions: string, optional
            Text containing detailed instructions for running the workflow
        sourcedir: string, optional
            Directory containing the workflow static files and the workflow
            template specification.
        repourl: string, optional
            Git repository that contains the the workflow files
        specfile: string, optional
            Path to the workflow template specification file (absolute or
            relative to the workflow directory)

        Returns
        -------
        flowserv.model.base.WorkflowHandle

        Raises
        ------
        flowserv.error.ConstraintViolationError
        flowserv.error.InvalidTemplateError
        ValueError
        """
        # Create workflow in the repository to get the workflow handle. Do not
        # commit changes in the database yet since we may need to add the
        # ranking result table.
        workflow = self.workflow_repo.create_workflow(
            name=name,
            description=description,
            instructions=instructions,
            sourcedir=sourcedir,
            repourl=repourl,
            specfile=specfile
        )
        # Return serialization og the workflow handle
        return self.serialize.workflow_handle(workflow)

    def delete_workflow(self, workflow_id):
        """Delete the workflow with the given identifier.

        Parameters
        ----------
        workflow_id: string
            Unique workflow identifier

        Raises
        ------
        flowserv.error.UnknownWorkflowError
        """
        self.workflow_repo.delete_workflow(workflow_id)

    def get_ranking(self, workflow_id, order_by=None, include_all=False):
        """Get serialization of the evaluation ranking for the given workflow.

        Parameters
        ----------
        workflow_id: string
            Unique workflow identifier
        order_by: list(flowserv.model.template.schema.SortColumn), optional
            Use the given attribute to sort run results. If not given, the
            schema default sort order is used
        include_all: bool, optional
            Include all entries (True) or at most one entry (False) per user
            group in the returned ranking

        Returns
        -------
        dict

        Raises
        ------
        flowserv.error.UnknownWorkflowError
        """
        # Get the workflow handle to ensure that the workflow exists
        workflow = self.workflow_repo.get_workflow(workflow_id)
        # Only ifthe workflow has a defined result schema we get theranking of
        # run results. Otherwise, the ranking is empty.
        if workflow.result_schema is not None:
            ranking = self.ranking_manager.get_ranking(
                workflow=workflow,
                order_by=order_by,
                include_all=include_all
            )
        else:
            ranking = list()
        postproc = None
        if workflow.postproc_run_id is not None:
            postproc = self.run_manager.get_run(workflow.postproc_run_id)
        return self.serialize.workflow_leaderboard(
            workflow=workflow,
            ranking=ranking,
            postproc=postproc
        )

    def get_result_archive(self, workflow_id):
        """Get compressed tar-archive containing all result files that were
        generated by the most recent post-processing workflow. If the workflow
        does not have a post-processing step or if the post-processing workflow
        run is not in SUCCESS state, a unknown resource error is raised.

        Parameters
        ----------
        workflow_id: string
            Unique workflow identifier

        Returns
        -------
        io.BytesIO

        Raises
        ------
        flowserv.error.UnknownWorkflowError
        flowserv.error.UnknownFileError
        """
        # Get the workflow handle. This will raise an error if the workflow
        # does not exist.
        workflow = self.workflow_repo.get_workflow(workflow_id)
        # Ensure that the post-processing run exists and that it is in SUCCESS
        # state
        if workflow.postproc_run_id is None:
            raise err.UnknownFileError('no post-processing workflow')
        run = self.run_manager.get_run(workflow.postproc_run_id)
        if not run.is_success():
            print(run.state().messages)
            raise err.UnknownFileError('post-porcessing failed')
        # Return the resource archive for the run handle
        return run.archive()

    def get_result_file(self, workflow_id, file_id):
        """Get file handle for a file that was generated as the result of a
        successful post-processing workflow run.

        Parameters
        ----------
        workflow_id: string
            Unique workflow identifier
        file_id: string
            Unique resource file identifier

        Returns
        -------
        flowserv.model.base.FileHandle

        Raises
        ------
        flowserv.error.UnknownWorkflowError
        flowserv.error.UnknownFileError
        """
        # Get the workflow handle. This will raise an error if the workflow
        # does not exist.
        workflow = self.workflow_repo.get_workflow(workflow_id)
        # Ensure that the post-processing run exists and that it is in SUCCESS
        # state.
        if workflow.postproc_run_id is None:
            raise err.UnknownFileError(file_id)
        run = self.run_manager.get_run(workflow.postproc_run_id)
        if not run.is_success():
            raise err.UnknownFileError(file_id)
        # Retrieve the resource. Raise error if the resource does not exist.
        resource = run.get_file(by_id=file_id)
        if resource is None:
            raise err.UnknownFileError(file_id)
        # Return file handle for resource file
        return resource

    def get_workflow(self, workflow_id):
        """Get serialization of the handle for the given workflow.

        Parameters
        ----------
        workflow_id: string
            Unique workflow identifier

        Returns
        -------
        dict

        Raises
        ------
        flowserv.error.UnknownWorkflowError
        """
        # Get the workflow handle. This will ensure that the workflow exists.
        workflow = self.workflow_repo.get_workflow(workflow_id)
        postproc = None
        if workflow.postproc_run_id is not None:
            postproc = self.run_manager.get_run(workflow.postproc_run_id)
        return self.serialize.workflow_handle(workflow, postproc=postproc)

    def list_workflows(self):
        """Get serialized listing of descriptors for all workflows in the
        repository.

        Returns
        -------
        dict
        """
        workflows = self.workflow_repo.list_workflows()
        return self.serialize.workflow_listing(workflows)

    def update_workflow(
        self, workflow_id, name=None, description=None, instructions=None
    ):
        """Update name, description, and instructions for a given workflow.
        Returns the serialized handle for the updated workflow.

        Raises an error if the given workflow does not exist or if the name is
        not unique.

        Parameters
        ----------
        workflow_id: string
            Unique workflow identifier
        name: string, optional
            Unique workflow name
        description: string, optional
            Optional short description for display in workflow listings
        instructions: string, optional
            Text containing detailed instructions for workflow execution

        Returns
        -------
        dict

        Raises
        ------
        flowserv.error.ConstraintViolationError
        flowserv.error.UnknownWorkflowError
        """
        workflow = self.workflow_repo.update_workflow(
            workflow_id=workflow_id,
            name=name,
            description=description,
            instructions=instructions
        )
        postproc = None
        if workflow.postproc_run_id is not None:
            postproc = self.run_manager.get_run(workflow.postproc_run_id)
        return self.serialize.workflow_handle(workflow, postproc=postproc)
