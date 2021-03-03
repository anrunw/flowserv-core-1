# This file is part of the Reproducible and Reusable Data Analysis Workflow
# Server (flowServ).
#
# Copyright (C) 2019-2021 NYU.
#
# flowServ is free software; you can redistribute it and/or modify it under the
# terms of the MIT License; see LICENSE file for more details.

"""Abstract class for file stores. The file store provides access to files that
are uploaded for workflow groups or that are generated by successful workflow
runs.

The file store also defines the folder structure of the file system for
workflows and their associated resources.

The folder structure is currently as follows:

.. code-block:: console

    /workflows/                  : Base directory
        {workflow_id}            : Folder for individual workflow
            groups/              : Folder for workflow groups
                {group_id}       : Folder for individual group
                    files/       : Uploaded files for workflow group
                        {file_id}: Folder for uploaded file
            runs/                : Folder for all workflow runs
                {run_id}         : Result files for individual runs
            static/
"""

from abc import ABCMeta, abstractmethod
from io import BytesIO
from typing import IO, List, Tuple

import os


# -- File objects for file stores ---------------------------------------------

class IOHandle(metaclass=ABCMeta):
    """Wrapper around different file objects (i.e., files on disk or files in
    object stores). Provides functionality to load file content as a bytes
    buffer and to write file contents to disk.
    """
    @abstractmethod
    def open(self) -> IO:
        """Get file contents as a BytesIO buffer.

        Returns
        -------
        io.BytesIO

        Raises
        ------
        flowserv.error.UnknownFileError
        """
        raise NotImplementedError()  # pragma: no cover

    @abstractmethod
    def size(self) -> int:
        """Get size of the file in the number of bytes.

        Returns
        -------
        int
        """
        raise NotImplementedError()  # pragma: no cover

    @abstractmethod
    def store(self, filename: str):
        """Write file content to disk.

        Parameters
        ----------
        filename: string
            Name of the file to which the content is written.
        """
        raise NotImplementedError()  # pragma: no cover


class IOBuffer(IOHandle):
    """Implementation of the file object interface for bytes IO buffers."""
    def __init__(self, buf: IO):
        """Initialize the IO buffer.

        Parameters
        ----------
        buf: io.BytesIO
            IO buffer containing the file contents.
        """
        self.buf = buf

    def open(self) -> IO:
        """Get the associated BytesIO buffer.

        Returns
        -------
        io.BytesIO
        """
        self.buf.seek(0)
        return self.buf

    def size(self) -> int:
        """Get size of the file in the number of bytes.

        Returns
        -------
        int
        """
        return self.buf.getbuffer().nbytes

    def store(self, filename: str):
        """Write buffer contents to disk.

        Parameters
        ----------
        filename: string
            Name of the file to which the content is written.
        """
        with open(filename, 'wb') as f:
            f.write(self.open().read())


# -- Wrapper for database files -----------------------------------------------

class FileHandle(IOHandle):
    """Handle for a file that is stored in the database. Extends the file object
    with the base file name and the mime type.

    The implementation is a wrapper around a file object to make the handle
    agnostic to the underlying storage mechanism.
    """
    def __init__(self, name: str, mime_type: str, fileobj: IOHandle):
        """Initialize the file object and file handle.

        Parameters
        ----------
        name: string
            File name (or relative file path)
        mime_type: string
            File content mime type.
        fileobj: flowserv.model.files.base.IOHandle
            File object providing access to the file content.
        """
        self.name = name
        self.mime_type = mime_type
        self.fileobj = fileobj

    def open(self) -> IO:
        """Get an BytesIO buffer containing the file content. If the associated
        file object is a path to a file on disk the file is being read.

        Returns
        -------
        io.BytesIO

        Raises
        ------
        flowserv.error.UnknownFileError
        """
        return self.fileobj.open()

    def size(self) -> int:
        """Get size of the file in the number of bytes.

        Returns
        -------
        int
        """
        return self.fileobj.size()

    def store(self, filename: str):
        """Write file contents to disk.

        Parameters
        ----------
        filename: string
            Name of the file to which the content is written.
        """
        self.fileobj.store(filename)


# -- Wrapper for files that are uploaded as part of a Flask request -----------

class FlaskFile(IOHandle):
    """File object implementation for files that are uploaded via Flask
    requests as werkzeug.FileStorage objects.
    """
    def __init__(self, file):
        """Initialize the reference to the uploaded file object.

        Parameters
        ----------
        file: werkzeug.FileStorage
            File object that was uploaded as part of a Flask request.
        """
        self.file = file

    def open(self) -> IO:
        """Get file contents as a BytesIO buffer.

        Returns
        -------
        io.BytesIO

        Raises
        ------
        flowserv.error.UnknownFileError
        """
        buf = BytesIO()
        self.file.save(buf)
        buf.seek(0)
        return buf

    def size(self) -> int:
        """Get size of the file in the number of bytes.

        Returns
        -------
        int
        """
        return self.file.content_length

    def store(self, filename: str):
        """Write file content to disk.

        Parameters
        ----------
        filename: string
            Name of the file to which the content is written.
        """
        self.file.save(filename)


# -- Abstract file store ------------------------------------------------------

class FileStore(metaclass=ABCMeta):
    """Interface for the file store. Files are identified by unique keys (e.g.,
    relative paths). The key structure is implementation-dependent.
    """
    @abstractmethod
    def copy_folder(self, key: str, dst: str):
        """Copy all files in the folder with the given key to a target folder
        on the local file system. Ensures that the target folder exists.

        Parameters
        ----------
        key: string
            Unique folder key.
        dst: string
            Path on the file system to the target folder.
        """
        raise NotImplementedError()  # pragma: no cover

    @abstractmethod
    def delete_file(self, key: str):
        """Delete the file with the given key.

        Parameters
        ----------
        key: string
            Unique file key.
        """
        raise NotImplementedError()  # pragma: no cover

    @abstractmethod
    def delete_folder(self, key: str):
        """Delete all files in the folder with the given key.

        Parameters
        ----------
        key: string
            Unique folder key.
        """
        raise NotImplementedError()  # pragma: no cover

    def group_uploaddir(self, workflow_id: str, group_id: str) -> str:
        """Get base directory for files that are uploaded to a workflow group.

        Parameters
        ----------
        workflow_id: string
            Unique workflow identifier
        group_id: string
            Unique workflow group identifier

        Returns
        -------
        string
        """
        groupdir = self.workflow_groupdir(workflow_id, group_id)
        return os.path.join(groupdir, 'files')

    @abstractmethod
    def load_file(self, key: str) -> IOHandle:
        """Get a file object for the file with the given key. The key should
        reference a single file only and not a folder.

        Parameters
        ----------
        key: string
            Unique file key.

        Returns
        -------
        flowserv.model.files.base.IOHandle
        """
        raise NotImplementedError()  # pragma: no cover

    def run_basedir(self, workflow_id: str, run_id: str) -> str:
        """Get path to the base directory for all files that are maintained for
        a workflow run.

        Parameters
        ----------
        workflow_id: string
            Unique workflow identifier
        run_id: string
            Unique run identifier

        Returns
        -------
        string
        """
        workflowdir = self.workflow_basedir(workflow_id)
        return os.path.join(workflowdir, 'runs', run_id)

    @abstractmethod
    def store_files(self, files: List[Tuple[IOHandle, str]], dst: str):
        """Store a given list of file objects in the file store. The file
        destination key is a relative path name. This is used as the base path
        for all files. The file list contains tuples of file object and target
        path. The target is relative to the base destination path.

        Parameters
        ----------
        file: list of (flowserv.model.files.base.IOHandle, string)
            The input file objects.
        dst: string
            Relative target path for the stored file.
        """
        raise NotImplementedError()  # pragma: no cover

    def workflow_basedir(self, workflow_id: str) -> str:
        """Get base directory containing associated files for the workflow with
        the given identifier.

        Parameters
        ----------
        workflow_id: string
            Unique workflow identifier

        Returns
        -------
        string
        """
        return workflow_id

    def workflow_groupdir(self, workflow_id: str, group_id: str) -> str:
        """Get base directory containing files that are associated with a
        workflow group.

        Parameters
        ----------
        workflow_id: string
            Unique workflow identifier
        group_id: string
            Unique workflow group identifier

        Returns
        -------
        string
        """
        workflowdir = self.workflow_basedir(workflow_id)
        return os.path.join(workflowdir, 'groups', group_id)

    def workflow_staticdir(self, workflow_id: str) -> str:
        """Get base directory containing static files that are associated with
        a workflow template.

        Parameters
        ----------
        workflow_id: string
            Unique workflow identifier

        Returns
        -------
        string
        """
        return os.path.join(self.workflow_basedir(workflow_id), 'static')
