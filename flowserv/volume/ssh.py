# This file is part of the Reproducible and Reusable Data Analysis Workflow
# Server (flowServ).
#
# Copyright (C) 2019-2021 NYU.
#
# flowServ is free software; you can redistribute it and/or modify it under the
# terms of the MIT License; see LICENSE file for more details.

"""Workflow storage manager that uses a SSH client to connect to a remote
server where run files are maintained.
"""

from __future__ import annotations
from typing import Dict, IO, List, Optional, Tuple

import paramiko

from flowserv.volume.base import IOHandle, StorageVolume
from flowserv.util.ssh import SSHClient

import flowserv.util as util


"""Type identifier for storage volume serializations."""
SFTP_STORE = 'sftp'


# -- File handles -------------------------------------------------------------

class SFTPFile(IOHandle):
    """Implementation of the IO object handle interface for files that are
    stored on a remote file system.
    """
    def __init__(self, filename: str, client: SSHClient):
        """Initialize the file name that points to a remote file and the SSH
        client that is used to open the file.

        Parameters
        ----------
        filename: string
            Path to an existing file on disk.
        client: flowserv.util.ssh.SSHClient
            SSH client for accessing the remote server.
        """
        self.filename = filename
        self.client = client

    def open(self) -> IO:
        """Get file contents as a BytesIO buffer.

        Returns
        -------
        io.BytesIO

        Raises
        ------
        flowserv.error.UnknownFileError
        """
        return self.client.sftp().open(self.filename, 'rb')

    def size(self) -> int:
        """Get size of the file in the number of bytes.

        Returns
        -------
        int
        """
        sftp = self.client.sftp()
        try:
            return sftp.stat(self.filename).st_size
        finally:
            sftp.close()


class RemoteStorage(StorageVolume):
    """File storage volume that connects to a remote server via sftp."""
    def __init__(self, client: SSHClient, remotedir: str, identifier: Optional[str] = None):
        """Initialize the storage base directory on the remote server and the
        SSH connection client.

        The remote base directory is created if it does not exist. If no
        identifier is provided a unique identifier is generated by the super
        class constructor.

        Parameters
        ----------
        client: flowserv.util.ssh.SSHClient
            SSH client for accessing the remote server.
        remotedir: string
            Base directory for all run files on the remote file system.
        identifier: string, default=None
            Unique volume identifier.
        """
        super(RemoteStorage, self).__init__(identifier=identifier)
        self.client = client
        self.remotedir = remotedir
        # Create the remote directory if it does not exists.
        sftp_mkdir(client=client.sftp(), dirpath=self.remotedir)

    def close(self):
        """Close the SSH connection when workflow execution is done."""
        self.client.close()

    def delete(self, key: str):
        """Delete file or folder with the given key.

        Parameters
        ----------
        key: str
            Path to a file object in the storage volume.
        """
        sftp = self.client.sftp()
        # Get recursive list of all files in the base folder and delete them.
        dirpath = util.filepath(key=key, sep=self.client.sep)
        dirpath = self.client.sep.join([self.remotedir, dirpath]) if dirpath else self.remotedir
        files = self.client.walk(dirpath=dirpath)
        if files is None:
            filename = util.filepath(key=key, sep=self.client.sep)
            filename = self.client.sep.join([self.remotedir, filename])
            sftp.remove(filename)
        else:
            # Collect sub-directories that need to be removed separately after
            # the directories are empty.
            directories = set()
            for src in files:
                filename = util.filepath(key=src, sep=self.client.sep)
                filename = self.client.sep.join([self.remotedir, filename])
                dirname = util.dirname(src)
                if dirname:
                    directories.add(dirname)
                sftp.remove(filename)
            for dirpath in sorted(directories, reverse=True):
                dirname = util.filepath(key=dirpath, sep=self.client.sep)
                dirname = self.client.sep.join([self.remotedir, dirname]) if dirname else self.remotedir
                sftp.rmdir(dirname)

    def describe(self) -> str:
        """Get short descriptive string about the storage volume for display
        purposes.

        Returns
        -------
        str
        """
        return "remote server {}:{}".format(self.client.hostname, self.remotedir)

    def erase(self):
        """Erase the storage volume base directory and all its contents."""
        # Delete all files and folders that are reachable from the remote base
        # directory.
        self.delete(key=None)
        # Delete the remote base directory itself.
        self.client.sftp().rmdir(self.remotedir)

    @staticmethod
    def from_dict(doc) -> RemoteStorage:
        """Get remote storage volume instance from dictionary serialization.

        Parameters
        ----------
        doc: dict
            Dictionary serialization as returned by the ``to_dict()`` method.

        Returns
        -------
        flowserv.volume.ssh.RemoteStorage
        """
        args = util.to_dict(doc.get('args', []))
        return RemoteStorage(
            identifier=doc.get('id'),
            client=SSHClient(
                hostname=args.get('hostname'),
                port=args.get('port'),
                timeout=args.get('timeout'),
                look_for_keys=args.get('look_for_keys'),
                sep=args.get('sep')
            ),
            remotedir=args.get('basedir')
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
        dirpath = util.filepath(key=key, sep=self.client.sep)
        return RemoteStorage(
            client=self.client,
            remotedir=self.client.sep.join([self.remotedir, dirpath]),
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
        filename = util.filepath(key=key, sep=self.client.sep)
        filename = self.client.sep.join([self.remotedir, filename])
        return SFTPFile(filename=filename, client=self.client)

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
        filename = util.filepath(key=dst, sep=self.client.sep)
        filename = self.client.sep.join([self.remotedir, filename])
        dirname = self.client.sep.join(filename.split(self.client.sep)[:-1])
        sftp = self.client.sftp()
        try:
            sftp_mkdir(client=sftp, dirpath=dirname)
            with sftp.open(filename, 'wb') as fout:
                with file.open() as fin:
                    fout.write(fin.read())
        finally:
            sftp.close()

    def to_dict(self) -> Dict:
        """Get dictionary serialization for the storage volume.

        The returned serialization can be used by the volume factory to generate
        a new instance of this volume store.

        Returns
        -------
        dict
        """
        return Sftp(
            identifier=self.identifier,
            remotedir=self.remotedir,
            hostname=self.client.hostname,
            port=self.client.port,
            timeout=self.client.timeout,
            look_for_keys=self.client.look_for_keys,
            sep=self.client.sep
        )

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
        dirpath = util.filepath(key=src, sep=self.client.sep)
        dirpath = self.client.sep.join([self.remotedir, dirpath]) if dirpath else self.remotedir
        files = self.client.walk(dirpath=dirpath)
        if files is None:
            # The source path references a single file.
            filename = util.filepath(key=src, sep=self.client.sep)
            filename = self.client.sep.join([self.remotedir, filename])
            return [(src, SFTPFile(filename=filename, client=self.client))]
        else:
            # The source path references a directory.
            result = list()
            for key in files:
                key = util.join(src, key) if src else key
                filename = util.filepath(key=key, sep=self.client.sep)
                filename = self.client.sep.join([self.remotedir, filename])
                result.append((key, SFTPFile(filename=filename, client=self.client)))
            return result


# -- Helper functions ---------------------------------------------------------

def Sftp(
    remotedir: str, hostname: str, port: Optional[int] = None,
    timeout: Optional[float] = None, look_for_keys: Optional[bool] = False,
    sep: Optional[str] = '/', identifier: Optional[str] = None
) -> Dict:
    """Get configuration object for a remote server storage volume that is
    accessed via sftp.

    Parameters
    ----------
    remotedir: string
        Base directory for stored files on the remote server.
    hostname: string
        Server to connect to.
    port: int, default=None
        Server port to connect to.
    timeout: float, default=None
        Optional timeout (in seconds) for the TCP connect.
    look_for_keys: bool, default=False
        Set to True to enable searching for discoverable private key files
        in ``~/.ssh/``.
    sep: string, default='/'
        Path separator used by the remote file system.
    identifier: string, default=None
        Unique storage volume identifier.

    Returns
    -------
    dict
    """
    return {
        'type': SFTP_STORE,
        'id': identifier,
        'args': [
            util.to_kvp(key='basedir', value=remotedir),
            util.to_kvp(key='hostname', value=hostname),
            util.to_kvp(key='port', value=port),
            util.to_kvp(key='timeout', value=timeout),
            util.to_kvp(key='look_for_keys', value=look_for_keys),
            util.to_kvp(key='sep', value=sep)
        ]
    }


def sftp_mkdir(client: paramiko.SFTPClient, dirpath: str):
    """Create a directory on the remote server.

    ----------
    client: paramiko.SFTPClient
        SFTP client.
    dirpath: string
        Path to the created directory on the remote server.
    """
    try:
        # Attempt to change into the directory. This will raise an error
        # if the directory does not exist.
        client.chdir(dirpath)
    except IOError:
        # Create directory if it does not exist.
        client.mkdir(dirpath)
