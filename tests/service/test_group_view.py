# This file is part of the Reproducible and Reusable Data Analysis Workflow
# Server (flowServ).
#
# Copyright (C) 2019-2020 NYU.
#
# flowServ is free software; you can redistribute it and/or modify it under the
# terms of the MIT License; see LICENSE file for more details.

"""Unit tests for the workflow group service API."""

import pytest

from flowserv.tests.parameter import StringParameter
from flowserv.tests.service import create_user

import flowserv.error as err
import flowserv.tests.serialize as serialize


def test_create_group_view(service, hello_world):
    """Test serialization for created workflows."""
    # -- Setup ----------------------------------------------------------------
    #
    # Create one user and one instance of the 'Hello World' workflow.
    with service() as api:
        user_1 = create_user(api)
        r = hello_world(api, name='W1')
        workflow_id = r['id']
    # Create a new workflow group with single user ----------------------------
    with service() as api:
        r = api.groups().create_group(
            workflow_id=workflow_id,
            name='G1',
            user_id=user_1
        )
        serialize.validate_group_handle(r)
        assert len(r['parameters']) == 3
        assert len(r['members']) == 1


def test_delete_group_view(service, hello_world):
    """Test deleting workflow groups via the API service."""
    # -- Setup ----------------------------------------------------------------
    #
    # Create two groups for the 'Hello World' workflow.
    with service() as api:
        user_1 = create_user(api)
        user_2 = create_user(api)
        r = hello_world(api, name='W1')
        workflow_id = r['id']
        r = api.groups().create_group(
            workflow_id=workflow_id,
            name='G1',
            user_id=user_1
        )
        group_id = r['id']
        api.groups().create_group(
            workflow_id=workflow_id,
            name='G2',
            user_id=user_1
        )
    # -- User 2 cannot delete the first group ---------------------------------
    with service() as api:
        with pytest.raises(err.UnauthorizedAccessError):
            api.groups().delete_group(group_id=group_id, user_id=user_2)
    # -- Delete the first group -----------------------------------------------
    with service() as api:
        api.groups().delete_group(group_id=group_id, user_id=user_1)
        # After deleting one group the other group is still there.
        r = api.groups().list_groups(workflow_id=workflow_id)
        assert len(r['groups']) == 1
    # -- Error when deleting an unknown group ---------------------------------
    with service() as api:
        with pytest.raises(err.UnknownWorkflowGroupError):
            api.groups().delete_group(group_id=group_id, user_id=user_1)


def test_get_group_view(service, hello_world):
    """Create workflow group and validate the returned handle when retrieving
    the group view the service. In addition to the create_group test, this test
    creates a group with more than one member and additional workflow
    parameters.
    """
    # -- Setup ----------------------------------------------------------------
    #
    # Create two users and one instance of the 'Hello World' workflow.
    with service() as api:
        user_1 = create_user(api)
        user_2 = create_user(api)
        r = hello_world(api, name='W1')
        workflow_id = r['id']
    # -- Create group with two members ----------------------------------------
    with service() as api:
        r = api.groups().create_group(
            workflow_id=workflow_id,
            name='G2',
            user_id=user_1,
            members=[user_2],
            parameters={
                'A': StringParameter('A'),
                'B': StringParameter('B')
            }
        )
        serialize.validate_group_handle(r)
        assert len(r['parameters']) == 5
        assert len(r['members']) == 2
    with service() as api:
        r = api.groups().get_group(r['id'])
        serialize.validate_group_handle(r)
        assert len(r['parameters']) == 5
        assert len(r['members']) == 2


def test_list_groups_view(service, hello_world):
    """Test serialization for group listings."""
    # -- Setup ----------------------------------------------------------------
    #
    # Create two groups for the 'Hello World' workflow. The first group has one
    # member and the second group has two memebers.
    with service() as api:
        user_1 = create_user(api)
        user_2 = create_user(api)
        r = hello_world(api, name='W1')
        workflow_id = r['id']
        api.groups().create_group(
            workflow_id=workflow_id,
            name='G1',
            user_id=user_1
        )
        api.groups().create_group(
            workflow_id=workflow_id,
            name='G2',
            user_id=user_1,
            members=[user_1, user_2]
        )
    # -- Get group listing listing for workflow -------------------------------
    with service() as api:
        r = api.groups().list_groups(workflow_id=workflow_id)
        serialize.validate_group_listing(r)
        assert len(r['groups']) == 2
    # -- Get groups for user 1 and 2 separately -------------------------------
    with service() as api:
        r = api.groups().list_groups(user_id=user_1)
        assert len(r['groups']) == 2
        r = api.groups().list_groups(user_id=user_2)
        assert len(r['groups']) == 1


def test_update_group_view(service, hello_world):
    """Test updating group properties via the API service."""
    # -- Setup ----------------------------------------------------------------
    #
    # Create one group with minimal metadata for the 'Hello World' workflow.
    with service() as api:
        user_id = create_user(api)
        r = hello_world(api, name='W1')
        workflow_id = r['id']
        r = api.groups().create_group(
            workflow_id=workflow_id,
            name='G1',
            user_id=user_id
        )
        group_id = r['id']
    # -- Update group name ----------------------------------------------------
    with service() as api:
        r = api.groups().update_group(
            group_id=group_id,
            user_id=user_id,
            name='ABC'
        )
        assert r['name'] == 'ABC'
    with service() as api:
        # Update persists when retrieving the group handle.
        r = api.groups().get_group(group_id)
        assert r['name'] == 'ABC'
