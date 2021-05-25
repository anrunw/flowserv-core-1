# This file is part of the Reproducible and Reusable Data Analysis Workflow
# Server (flowServ).
#
# Copyright (C) 2019-2021 NYU.
#
# flowServ is free software; you can redistribute it and/or modify it under the
# terms of the MIT License; see LICENSE file for more details.

"""File system workflow storage volume. Maintains workflow run files in
a folder on the local file system.
"""

from __future__ import annotations
from typing import Dict, IO, List, Optional, Tuple

import os
import shutil

from flowserv.volume.base import IOHandle, StorageVolume

import flowserv.error as err
import flowserv.util as util


"""Type identifier for storage volume serializations."""
FS_STORE = 'fs'


# -- File handles -------------------------------------------------------------

class FSFile(IOHandle):
    """Implementation of the IO object handle interface for files that are
    stored on the file system.
    """
    def __init__(self, filename: str, raise_error: Optional[bool] = True):
        """Initialize the file name that points to a file on disk.

        Parameters
        ----------
        filename: string
            Path to an existing file on disk.
        raise_error: bool, default=True
            Raise error if the given file name does not reference an existing
            file.
        """
        if raise_error and not os.path.isfile(filename):
            raise err.UnknownFileError(filename)
        self.filename = filename

    def open(self) -> IO:
        """Get file contents as a BytesIO buffer.

        Returns
        -------
        io.BytesIO

        Raises
        ------
        flowserv.error.UnknownFileError
        """
        return util.read_buffer(self.filename)

    def size(self) -> int:
        """Get size of the file in the number of bytes.

        Returns
        -------
        int
        """
        return os.stat(self.filename).st_size


# -- Storage volumes ----------------------------------------------------------

class FileSystemStorage(StorageVolume):
    """The file system storage volume provides access to workflow run
    files that are maintained in a run directory on the local file system.
    """
    def __init__(self, basedir: str, identifier: Optional[str] = None):
        """Initialize the run base directory and the unique volume
        identifier.

        The base directory is created if it does not exist. If no identifier is
        provided a unique identifier is generated by the super class constructor.

        Parameters
        ----------
        basedir: string
            Base directory for all run files on the local file system.
        identifier: string, default=None
            Unique volume identifier.
        """
        super(FileSystemStorage, self).__init__(identifier=identifier)
        self.basedir = basedir
        os.makedirs(self.basedir, exist_ok=True)

    def close(self):
        """The file system runtime manager has no connections to close or
        resources to release.
        """
        pass

    def delete(self, key: str):
        """Delete file or folder with the given key.

        Parameters
        ----------
        key: str
            Path to a file object in the storage volume.
        """
        filename = os.path.join(self.basedir, key)
        if os.path.isfile(filename):
            os.remove(filename)
        elif os.path.isdir(filename):
            shutil.rmtree(filename)

    def describe(self) -> str:
        """Get short descriptive string about the storage volume for display
        purposes.

        Returns
        -------
        str
        """
        return "local file system at {}".format(os.path.abspath(self.basedir))

    def erase(self):
        """Erase the storage volume base directory and all its contents."""
        shutil.rmtree(self.basedir)

    @staticmethod
    def from_dict(doc) -> FileSystemStorage:
        """Get file system storage volume instance from dictionary serialization.

        Parameters
        ----------
        doc: dict
            Dictionary serialization as returned by the ``to_dict()`` method.

        Returns
        -------
        flowserv.volume.fs.FileSystemStorage
        """
        return FileSystemStorage(
            identifier=doc.get('identifier'),
            basedir=util.to_dict(doc.get('args', [])).get('basedir')
        )

    def get_store_for_folder(self, key: str, identifier: Optional[str] = None) -> StorageVolume:
        """Get storage volume for a sob-folder of the given volume.

        Parameters
        ----------
        key: string
            Relative path to sub-folder. The concatenation of the base folder
            for this storage volume and the given key will form te new base
            folder for the returned storage volume.
        identifier: string, default=None
            Unique volume identifier.

        Returns
        -------
        flowserv.volume.base.StorageVolume
        """
        return FileSystemStorage(
            basedir=os.path.join(self.basedir, util.filepath(key=key)),
            identifier=identifier
        )

    def load(self, key: str) -> IOHandle:
        """Load a file object at the source path of this volume store.

        Returns a file handle that can be used to open and read the file.

        Parameters
        ----------
        key: str
            Path to a file object in the storage volume.

        Returns
        --------
        flowserv.volume.base.IOHandle
        """
        # The file key is a path expression that uses '/' as the path separator.
        # If the local OS uses a different separator we need to replace it.
        filename = os.path.join(self.basedir, util.filepath(key=key))
        if not os.path.isfile(filename):
            raise err.UnknownFileError(filename)
        return FSFile(filename=filename)

    def store(self, file: IOHandle, dst: str):
        """Store a given file object at the destination path of this volume
        store.

        Parameters
        ----------
        file: flowserv.volume.base.IOHandle
            File-like object that is being stored.
        dst: str
            Destination path for the stored object.
        """
        # The file key is a path expression that uses '/' as the path separator.
        # If the local OS uses a different separator we need to replace it.
        filename = os.path.join(self.basedir, util.filepath(key=dst))
        os.makedirs(os.path.dirname(filename), exist_ok=True)
        with open(filename, 'wb') as fout:
            with file.open() as fin:
                fout.write(fin.read())

    def to_dict(self) -> Dict:
        """Get dictionary serialization for the storage volume.

        The returned serialization can be used by the volume factory to generate
        a new instance of this volume store.

        Returns
        -------
        dict
        """
        return FStore(basedir=self.basedir, identifier=self.identifier)

    def walk(self, src: str) -> List[Tuple[str, IOHandle]]:
        """Get list of all files at the given source path.

        If the source path references a single file the returned list will
        contain a single entry. If the source specifies a folder the result
        contains a list of all files in that folder and the subfolders.

        Parameters
        ----------
        src: str
            Source path specifying a file or folder.

        Returns
        -------
        list of tuples (str, flowserv.volume.base.IOHandle)
        """
        # The file key is a path expression that uses '/' as the path separator.
        # If the local OS uses a different separator we need to replace it.
        filename = os.path.join(self.basedir, util.filepath(key=src)) if src else self.basedir
        # The result is a list of file keys.
        result = list()
        if os.path.isfile(filename):
            # If the source key references a file return a list with the key as
            # the only element.
            result.append((src, FSFile(filename=filename)))
        elif os.path.isdir(filename):
            # Recursively append all files in the referenced directory to the
            # result list.
            walkdir(filename, src, result)
        return result


# -- Helper functions ---------------------------------------------------------

def FStore(basedir: str, identifier: Optional[str] = None) -> Dict:
    """Get configuration object for a file system storage volume.

    Parameters
    ----------
    basedir: string
        Google Cloud Storage bucket identifier.
    identifier: string, default=None
        Optional storage volume identifier.

    Returns
    -------
    dict
    """
    return {
        'type': FS_STORE,
        'identifier': identifier,
        'args': [util.to_kvp(key='basedir', value=basedir)]
    }


def walkdir(dirname: str, prefix: str, files: List[Tuple[str, IOHandle]]) -> List[Tuple[str, IOHandle]]:
    """Recursively add all files in a given source folder to a file upload list.
    The elements in the list are tuples of file object and relative target
    path.

    Parameters
    ----------
    dirname: string
        Path to folder of the local file system.
    prefix: string
        Relative destination path for all files in the folder.
    files: list of (flowserv.model.files.fs.FSFile, string)
        Pairs of file objects and their relative target path for upload to a
        file store.
    """
    for filename in os.listdir(dirname):
        file = os.path.join(dirname, filename)
        key = util.join(prefix, filename) if prefix else filename
        if os.path.isdir(file):
            walkdir(dirname=file, prefix=key, files=files)
        else:
            files.append((key, FSFile(filename=file)))
    return files
