# This file is part of the Reproducible and Reusable Data Analysis Workflow
# Server (flowServ).
#
# Copyright (C) 2019-2020 NYU.
#
# flowServ is free software; you can redistribute it and/or modify it under the
# terms of the MIT License; see LICENSE file for more details.

"""Serializer for workflow user groups."""

from typing import Dict, List, Optional

from flowserv.model.base import GroupHandle
from flowserv.view.files import UploadFileSerializer


"""Serialization labels."""
GROUP_ID = 'id'
GROUP_LIST = 'groups'
GROUP_MEMBERS = 'members'
GROUP_NAME = 'name'
GROUP_PARAMETERS = 'parameters'
GROUP_UPLOADS = 'files'
USER_ID = 'id'
USER_NAME = 'username'
WORKFLOW_ID = 'workflow'


class WorkflowGroupSerializer(object):
    """Default serializer for workflow user groups."""
    def __init__(self, files: Optional[UploadFileSerializer] = None):
        """Initialize the serializer for uploaded files.

        Parameters
        ----------
        files: flowserv.view.files.UploadFileSerializer, default=None
            Serializer for handles of uploaded files
        """
        self.files = files if files is not None else UploadFileSerializer()

    def group_descriptor(self, group: GroupHandle) -> Dict:
        """Get serialization for a workflow group descriptor. The descriptor
        contains the group identifier, name, and the base list of HATEOAS
        references.

        Parameters
        ----------
        group: flowserv.model.base.GroupHandle
            Workflow group handle

        Returns
        -------
        dict
        """
        return {
            GROUP_ID: group.group_id,
            GROUP_NAME: group.name,
            WORKFLOW_ID: group.workflow_id
        }

    def group_handle(self, group: GroupHandle) -> Dict:
        """Get serialization for a workflow group handle.

        Parameters
        ----------
        group: flowserv.model.base.GroupHandle
            Workflow group handle

        Returns
        -------
        dict
        """
        doc = self.group_descriptor(group)
        members = list()
        for u in group.members:
            members.append({
                USER_ID: u.user_id,
                USER_NAME: u.name
            })
        doc[GROUP_MEMBERS] = members
        parameters = group.parameters.values()
        # Include group specific list of workflow template parameters
        doc[GROUP_PARAMETERS] = [p.to_dict() for p in parameters]
        # Include handles for all uploaded files
        files = list()
        for file in group.uploads:
            f = self.files.file_handle(
                group_id=group.group_id,
                fh=file
            )
            files.append(f)
        doc[GROUP_UPLOADS] = files

        return doc

    def group_listing(self, groups: List[GroupHandle]) -> Dict:
        """Get serialization of a workflow group descriptor list.

        Parameters
        ----------
        groups: list(flowserv.model.base.GroupHandle)
            List of descriptors for workflow groups

        Returns
        -------
        dict
        """
        return {GROUP_LIST: [self.group_descriptor(g) for g in groups]}
