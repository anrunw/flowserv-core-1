# This file is part of the Reproducible and Reusable Data Analysis Workflow
# Server (flowServ).
#
# Copyright (C) 2019-2020 NYU.
#
# flowServ is free software; you can redistribute it and/or modify it under the
# terms of the MIT License; see LICENSE file for more details.

"""The workflow repository maintains information about registered workflow
templates. For each template additional basic information is stored in the
underlying database.
"""

import errno
import git
import json
import os
import re
import shutil
import tempfile

from flowserv.model.parameter.base import ParameterGroup
from flowserv.model.run.manager import RunManager
from flowserv.model.template.base import WorkflowTemplate
from flowserv.model.template.schema import ResultSchema
from flowserv.model.workflow.base import WorkflowDescriptor, WorkflowHandle

import flowserv.error as err
import flowserv.util as util
import flowserv.model.constraint as constraint
import flowserv.model.parameter.base as pb


""" "Default values for the max. attempts parameter and the ID generator
function.
"""
DEFAULT_ATTEMPTS = 100
DEFAULT_IDFUNC = util.get_short_identifier

"""Names for files that are used to identify template specification and project
descriptions.
"""
DEFAULT_SPECNAMES = ['benchmark', 'workflow', 'template']
DEFAULT_SPECSUFFIXES = ['.json', '.yaml', '.yml']
DEFAULT_TEMPLATES = list()
for name in DEFAULT_SPECNAMES:
    for suffix in DEFAULT_SPECSUFFIXES:
        DEFAULT_TEMPLATES.append(name + suffix)
# List of default project description files
DESCRIPTION_FILES = list()
for suffix in DEFAULT_SPECSUFFIXES:
    DESCRIPTION_FILES.append('flowserv' + suffix)

"""Labels for the project description file."""
DESCRIPTION = 'description'
FILES = 'files'
INSTRUCTIONS = 'instructions'
NAME = 'name'
SOURCE = 'source'
SPECFILE = 'specfile'
TARGET = 'target'
WORKFLOWSPEC = 'workflowSpec'


class WorkflowRepository(object):
    """The workflow repository maintains information that is associated with
    workflow templates in a given repository.
    """
    def __init__(self, con, fs, idfunc=None, attempts=None, tmpl_names=None):
        """Initialize the database connection, and the generator for workflow
        related file names and directory paths. The optional parameters are
        used to configure the identifier function that is used to generate
        unique workflow identifier as well as the list of default file names
        for template specification files.

        By default, short identifiers are used.

        Parameters
        ----------
        con: DB-API 2.0 database connection
            Connection to underlying database
        fs: flowserv.model.workflow.fs.WorkflowFileSystem
            Generattor for file names and directory paths
        idfunc: func, optional
            Function to generate template folder identifier
        attempts: int, optional
            Maximum number of attempts to create a unique folder for a new
            workflow template
        tmpl_names: list(string), optional
            List of default names for template specification files
        """
        self.con = con
        self.fs = fs
        # Initialize the identifier function and the max. number of attempts
        # that are made to generate a unique identifier.
        self.idfunc = idfunc if idfunc is not None else DEFAULT_IDFUNC
        self.attempts = attempts if attempts is not None else DEFAULT_ATTEMPTS
        # Initialize the list of default template specification file names
        if tmpl_names is not None:
            self.default_filenames = tmpl_names
        else:
            self.default_filenames = DEFAULT_TEMPLATES

    def create_workflow(
        self, name=None, description=None, instructions=None, sourcedir=None,
        repourl=None, specfile=None, commit_changes=True
    ):
        """Add new workflow to the repository. The associated workflow template
        is created in the template repository from either the given source
        directory or a Git repository. The template repository will raise an
        error if neither or both arguments are given.

        The method will look for a workflow description file in the template
        base folder with the name flowserv.json, flowserv.yaml, flowserv.yml
        (in this order). The expected structure of the file is:

        name: ''
        description: ''
        instructions: ''
        files:
            - source: ''
              target: ''
        specfile: '' or workflowSpec: ''

        An error is raised if both specfile and workflowSpec are present in the
        description file.

        Raises an error if no workflow name is given or if a given workflow
        name is not unique.

        Parameters
        ----------
        name: string, optional
            Unique workflow name
        description: string, optional
            Optional short description for display in workflow listings
        instructions: string, optional
            File containing instructions for workflow users.
        sourcedir: string, optional
            Directory containing the workflow static files and the workflow
            template specification.
        repourl: string, optional
            Git repository that contains the the workflow files
        specfile: string, optional
            Path to the workflow template specification file (absolute or
            relative to the workflow directory)
        commit_changes: bool, optional
            Commit changes to database only if True

        Returns
        -------
        flowserv.model.workflow.base.WorkflowHandle

        Raises
        ------
        flowserv.error.ConstraintViolationError
        flowserv.error.InvalidTemplateError
        ValueError
        """
        # Exactly one of sourcedir and repourl has to be not None. If both
        # are None (or not None) a ValueError is raised.
        if sourcedir is None and repourl is None:
            raise ValueError('no source folder or repository url given')
        elif sourcedir is not None and repourl is not None:
            raise ValueError('source folder and repository url given')
        # If a repository Url is given we first clone the repository into a
        # temporary directory that is used as the project base directory.
        projectdir = git_clone(repourl) if repourl is not None else sourcedir
        # Read project metadata from description file. Override with given
        # arguments
        try:
            projectmeta = read_description(
                projectdir=projectdir,
                name=name,
                description=description,
                instructions=instructions,
                specfile=specfile
            )
        except (IOError, OSError, ValueError) as ex:
            # Cleanup project directory if it was cloned from a git repository.
            if repourl is not None:
                shutil.rmtree(projectdir)
            raise ex
        # Create identifier and folder for the workflow template. Create a
        # sub-folder for static template files that are copied from the project
        # folder.
        workflow_id, workflowdir = self.create_folder(self.fs.workflow_basedir)
        staticdir = self.fs.workflow_staticdir(workflow_id)
        # Find template specification file in the template workflow folder.
        # If the file is not found, the workflow directory is removed and an
        # error is raised.
        template = read_template(
            projectmeta=projectmeta,
            projectdir=projectdir,
            templatedir=staticdir,
            default_filenames=self.default_filenames
        )
        if template is None:
            shutil.rmtree(workflowdir)
            raise err.InvalidTemplateError('no template file found')
        # Ensure that the workflow name is not empty, not longer than 512
        # character, and unique.
        try:
            get_unique_name(
                con=self.con,
                projectmeta=projectmeta,
                sourcedir=sourcedir,
                repourl=repourl
            )
        except err.ConstraintViolationError as ex:
            cleanup(
                workflowdir=workflowdir,
                projectdir=projectdir if repourl is not None else None
            )
            raise ex
        # Copy files from the project folder to the template's static file
        # folder. By default all files in the project folder are copied.
        try:
            copy_files(
                projectmeta=projectmeta,
                projectdir=projectdir,
                templatedir=staticdir
            )
            # Remove the project folder if it was created from a git repository
            if repourl is not None:
                shutil.rmtree(projectdir)
        except (IOError, OSError, KeyError) as ex:
            cleanup(
                workflowdir=workflowdir,
                projectdir=projectdir if repourl is not None else None
            )
            raise ex
        # Insert workflow into database and return descriptor. Database changes
        # are only commited if the respective flag is True.
        sql = (
            'INSERT INTO workflow_template(workflow_id, name, description, '
            'instructions, workflow_spec, parameters, modules, postproc_spec, '
            'result_schema) '
            'VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)'
        )
        # Serialize values for optional template elements
        parameters = [p.to_dict() for p in template.parameters.values()]
        parameters = json.dumps(parameters) if len(parameters) > 0 else None
        postproc = template.postproc_spec
        postproc = json.dumps(postproc) if postproc is not None else None
        modules = template.modules
        if modules is not None:
            modules = json.dumps([m.to_dict() for m in modules])
        schema = template.result_schema
        schema = json.dumps(schema.to_dict()) if schema is not None else None
        args = (
            workflow_id,
            projectmeta.get(NAME),
            projectmeta.get(DESCRIPTION),
            projectmeta.get(INSTRUCTIONS),
            json.dumps(template.workflow_spec),
            parameters,
            modules,
            postproc,
            schema
        )
        self.con.execute(sql, args)
        if commit_changes:
            self.con.commit()
        return WorkflowHandle(
            con=self.con,
            identifier=workflow_id,
            name=projectmeta.get(NAME),
            description=projectmeta.get(DESCRIPTION),
            instructions=projectmeta.get(INSTRUCTIONS),
            template=template
        )

    def create_folder(self, dirfunc):
        """Create a new unique folder in a base directory using the internal
        identifier function. The path to the created folder is generated using
        the given directory function that takes a unique identifier as the only
        argument.

        Returns a tuple containing the identifier and the directory. Raises
        an error if the maximum number of attempts to create the unique folder
        was reached.

        Parameters
        ----------
        dirfunc: func
            Function to generate the path for the created folder

        Returns
        -------
        (id::string, subfolder::string)

        Raises
        ------
        ValueError
        """
        identifier = None
        attempt = 0
        while identifier is None:
            # Create a new identifier
            identifier = self.idfunc()
            # Try to generate the subfolder. If the folder exists, set
            # identifier to None to signal failure.
            subfolder = dirfunc(identifier)
            if os.path.isdir(subfolder):
                identifier = None
            else:
                try:
                    os.makedirs(subfolder)
                except OSError as e:
                    if e.errno != errno.EEXIST:
                        raise
                    else:
                        # Directory must have been created concurrently
                        identifier = None
            if identifier is None:
                # Increase number of failed attempts. If the maximum number of
                # attempts is reached raise an errir
                attempt += 1
                if attempt > self.attempts:
                    raise RuntimeError('could not create unique folder')
        return identifier, subfolder

    def delete_workflow(self, workflow_id, commit_changes=True):
        """Delete the workflow with the given identifier.

        The changes to the underlying database are only commited if the
        commit_changes flag is True. Note that the deletion of files and
        directories cannot be rolled back.

        Parameters
        ----------
        workflow_id: string
            Unique workflow identifier
        commit_changes: bool, optional
            Commit changes to database only if True

        Raises
        ------
        flowserv.error.UnknownWorkflowError
        """
        # Get the base directory for the workflow. If the directory does not
        # exist we assume that the workflow is unknown and raise an error.
        workflowdir = self.fs.workflow_basedir(workflow_id)
        if not os.path.isdir(workflowdir):
            raise err.UnknownWorkflowError(workflow_id)
        # Create list of SQL statements to delete all records that are
        # associated with the workflow
        stmts = list()
        # -- Workflow Runs ----------------------------------------------------
        stmts.append(
            'DELETE FROM run_result_file WHERE run_id IN ('
            '   SELECT r.run_id FROM workflow_run r WHERE r.workflow_id = ?)'
        )
        stmts.append(
            'DELETE FROM run_error_log WHERE run_id IN ('
            '   SELECT r.run_id FROM workflow_run r WHERE r.workflow_id = ?)'
        )
        stmts.append('DELETE FROM workflow_run WHERE workflow_id = ?')
        # -- Workflow Group ---------------------------------------------------
        stmts.append(
            'DELETE FROM group_member WHERE group_id IN ('
            '   SELECT g.group_id FROM workflow_group g '
            '   WHERE g.workflow_id = ?)'
        )
        stmts.append(
            'DELETE FROM group_upload_file WHERE group_id IN ('
            '   SELECT g.group_id FROM workflow_group g '
            '   WHERE g.workflow_id = ?)'
        )
        stmts.append('DELETE FROM workflow_group WHERE workflow_id = ?')
        # -- Workflow Template ------------------------------------------------
        stmts.append('DELETE FROM workflow_postproc WHERE workflow_id = ?')
        stmts.append('DELETE FROM workflow_template WHERE workflow_id = ?')
        for sql in stmts:
            self.con.execute(sql, (workflow_id,))
        if commit_changes:
            self.con.commit()
        # Delete all files that are associated with the workflow
        if os.path.isdir(workflowdir):
            shutil.rmtree(workflowdir)

    def get_workflow(self, workflow_id):
        """Get handle for the workflow with the given identifier. Raises
        an error if no workflow with the identifier exists.

        Parameters
        ----------
        workflow_id: string
            Unique workflow identifier

        Returns
        -------
        flowserv.model.workflow.base.WorkflowHandle

        Raises
        ------
        flowserv.error.UnknownWorkflowError
        """
        # Get workflow information from database. If the result is empty an
        # error is raised
        sql = (
            'SELECT workflow_id, name, description, instructions, postproc_id,'
            'workflow_spec, parameters, modules, postproc_spec, result_schema '
            'FROM workflow_template '
            'WHERE workflow_id = ?'
        )
        row = self.con.execute(sql, (workflow_id,)).fetchone()
        if row is None:
            raise err.UnknownWorkflowError(workflow_id)
        name = row['name']
        description = row['description']
        instructions = row['instructions']
        postproc_id = row['postproc_id']
        # Get handles for post-processing workflow run
        postproc_run = None
        if postproc_id is not None:
            run_manager = RunManager(con=self.con, fs=self.fs)
            postproc_run = run_manager.get_run(run_id=postproc_id)
        # Create workflow template
        parameters = None
        if row['parameters'] is not None:
            parameters = pb.create_parameter_index(
                json.loads(row['parameters']),
                validate=False
            )
        modules = None
        if row['modules'] is not None:
            modules = list()
            for m in json.loads(row['modules']):
                modules.append(ParameterGroup.from_dict(m))
        postproc_spec = None
        if row['postproc_spec'] is not None:
            postproc_spec = json.loads(row['postproc_spec'])
        result_schema = None
        if row['result_schema'] is not None:
            doc = json.loads(row['result_schema'])
            result_schema = ResultSchema.from_dict(doc)
        template = WorkflowTemplate(
            workflow_spec=json.loads(row['workflow_spec']),
            sourcedir=self.fs.workflow_staticdir(workflow_id),
            parameters=parameters,
            modules=modules,
            postproc_spec=postproc_spec,
            result_schema=result_schema
        )
        # Return workflow handle
        return WorkflowHandle(
            con=self.con,
            identifier=workflow_id,
            name=name,
            description=description,
            instructions=instructions,
            template=template,
            postproc_run=postproc_run
        )

    def list_workflows(self):
        """Get a list of descriptors for all workflows in the repository.

        Returns
        -------
        list(flowserv.model.workflow.base.WorkflowDescriptor)
        """
        sql = 'SELECT workflow_id, name, description, instructions '
        sql += 'FROM workflow_template '
        result = list()
        for row in self.con.execute(sql).fetchall():
            result.append(
                WorkflowDescriptor(
                    identifier=row['workflow_id'],
                    name=row['name'],
                    description=row['description'],
                    instructions=row['instructions']
                )
            )
        return result

    def update_workflow(
        self, workflow_id, name=None, description=None, instructions=None,
        commit_changes=True
    ):
        """Update name, description, and instructions for a given workflow.

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
        commit_changes: bool, optional
            Commit changes to database only if True

        Returns
        -------
        flowserv.model.workflow.base.WorkflowHandle

        Raises
        ------
        flowserv.error.ConstraintViolationError
        flowserv.error.UnknownWorkflowError
        """
        # Create the SQL update statement depending on the given arguments
        args = list()
        sql = 'UPDATE workflow_template SET'
        if name is not None:
            # Ensure that the name is unique
            constraint_sql = 'SELECT name FROM workflow_template '
            constraint_sql += 'WHERE name = ? AND workflow_id <> ?'
            constraint.validate_name(
                name,
                con=self.con,
                sql=constraint_sql,
                args=(name, workflow_id))
            args.append(name)
            sql += ' name = ?'
        if description is not None:
            if len(args) > 0:
                sql += ','
            args.append(description)
            sql += ' description = ?'
        if instructions is not None:
            if len(args) > 0:
                sql += ','
            args.append(instructions)
            sql += ' instructions = ?'
        # If none of the optional arguments was given we do not need to update
        # anything
        if len(args) > 0:
            args.append(workflow_id)
            sql += ' WHERE workflow_id = ?'
            self.con.execute(sql, args)
            if commit_changes:
                self.con.commit()
        # Return the handle for the updated workflow
        return self.get_workflow(workflow_id)


# -- Helper Methods -----------------------------------------------------------

def cleanup(workflowdir, projectdir):
    """Remove created workflow directory in case of an error. If the project
    directory is given it contains a cloned git repository. In that case, the
    project directory will also be deleted.

    Parameters
    ----------
    workflowdir: string
        Path to created workflow template directory.
    projectdir: string
        Path to cloned git repository directory. Will be None if the project
        was not cloned.
    """
    shutil.rmtree(workflowdir)
    if projectdir is not None:
        shutil.rmtree(projectdir)


def copy_files(projectmeta, projectdir, templatedir):
    """Copy all template files from the project base folder to the template
    target folder in the repository. If the 'files' element in the project
    metadata is given, only the files referenced in the listing will be copied.
    By default, the whole project folder is copied.

    Parameters
    ----------
    projectmeta: dict
        Project metadata information from the project description file.
    projectdir: string
        Path to the base directory containing the project resource files.
    templatedir: string

    Raises
    ------
    IOError, KeyError, OSError
    """
    # Create a list of (source, target) pairs for the file copy statement.
    files = list()
    if FILES not in projectmeta:
        # If no files listing is present in the project metadata dictionary
        # copy the whole project directory to the source.
        for filename in os.listdir(projectdir):
            files.append((os.path.join(projectdir, filename), filename))
    else:
        for fspec in projectmeta.get(FILES, [{SOURCE: ''}]):
            source = os.path.join(projectdir, fspec[SOURCE])
            target = fspec.get(TARGET, '')
            if not os.path.isdir(source):
                if os.path.isdir(os.path.join(templatedir, target)):
                    # Esure that the target is a file and not a directory if
                    # the source is a file. If the target element in fspec is
                    # not set, the copy target would be a directory instead of
                    # a file.
                    target = os.path.join(target, os.path.basename(source))
            files.append((source, target))
    util.copy_files(files, templatedir)


def get_unique_name(con, projectmeta, sourcedir, repourl):
    """Ensure that the workflow name in the project metadata is not empty, not
    longer than 512 character, and unique.

    Parameters
    ----------
    con: DB-API 2.0 database connection, optional
        Connection to underlying database
    projectmeta: dict
        Project metadata information from the project description file.
    sourcedir: string
        Directory containing the workflow static files and the workflow
        template specification.
    repourl: string
        Git repository that contains the the workflow files

    Raises
    ------
    flowserv.error.ConstraintViolationError
    """
    name = projectmeta.get(NAME)
    # Ensure that the name is not None.
    if name is None:
        if sourcedir is not None:
            name = os.path.basename(sourcedir)
        else:
            name = repourl.split('/')[-1]
        if '.' in name:
            name = name[:name.find('.')]
        if '_' in name or '-' in name:
            name = ' '.join([t.capitalize() for t in re.split('[_-]', name)])
        else:
            name = name.capitalize()
    # Validate that the name is not empty and not too long.
    constraint.validate_name(name)
    # Ensure that the name is unique
    sql = 'SELECT name FROM workflow_template WHERE name = ?'
    if not con.execute(sql, (name,)).fetchone() is None:
        # Find a a unique name that matches the template name (int)
        name_templ = name + ' ({})'
        sql = 'SELECT name FROM workflow_template WHERE name LIKE ?'
        existing_names = set()
        for row in con.execute(sql, (name_templ.format('%'),)).fetchall():
            existing_names.add(row[0])
        count = 1
        while name_templ.format(count) in existing_names:
            count += 1
        name = name_templ.format(count)
        # Re-validate that the name is not too long.
        constraint.validate_name(name)
    # constraint.validate_name(, con=self.con, sql=sql)
    projectmeta[NAME] = name


def git_clone(repourl):
    """Clone a git repository from a given Url into a temporary folder on the
    local disk.

    Parameters
    ----------
    repourl: string
        Url to git repository.

    Returns
    -------
    string
    """
    # Create a temporary folder for the git repository
    projectdir = tempfile.mkdtemp()
    try:
        git.Repo.clone_from(repourl, projectdir)
    except (IOError, OSError, git.exc.GitCommandError) as ex:
        # Make sure to cleanup by removing the created project folder
        shutil.rmtree(projectdir)
        raise ex
    return projectdir


def read_description(projectdir, name, description, instructions, specfile):
    """Read the project description file from the project folder. Looks for a
    file with the following names: flowserv.json, flowserv.yaml, flowserv.yml.

    Replaces properties with the given arguments. Raises a ValueError if no
    name or no workflow specification is present in the resulting metadata
    dictionary.

    Parameters
    ----------
    projectdir: string
        Path to the base directory containing the project resource files.
    name: string
        Unique workflow name
    description: string
        Optional short description for display in workflow listings
    instructions: string
        File containing instructions for workflow users.
    specfile: string
        Path to the workflow template specification file (absolute or
        relative to the workflow directory)

    Returns
    -------
    dict

    Raises
    ------
    IOError, OSError, ValueError
    """
    doc = dict()
    for filename in DESCRIPTION_FILES:
        filename = os.path.join(projectdir, filename)
        if os.path.isfile(filename):
            doc = util.read_object(filename)
            break
    # Raise an error if both the specification file and workflow specification
    # are present in the project description.
    if SPECFILE in doc and WORKFLOWSPEC in doc:
        msg = 'invalid project description: {} and {} given'
        raise ValueError(msg.format(SPECFILE, WORKFLOWSPEC))
    # Override metadata with given arguments
    if name is not None:
        doc[NAME] = name
    if description is not None:
        doc[DESCRIPTION] = description
    if instructions is not None:
        doc[INSTRUCTIONS] = instructions
    if specfile is not None:
        # Set the specification file if given. Remove a workflow specification
        # in the project description if it exists.
        doc[SPECFILE] = specfile
        if WORKFLOWSPEC in doc:
            del doc[WORKFLOWSPEC]
    # Read the instructions file if specified
    if INSTRUCTIONS in doc:
        with open(os.path.join(projectdir, doc[INSTRUCTIONS]), 'r') as f:
            doc[INSTRUCTIONS] = f.read().strip()
    return doc


def read_template(projectmeta, projectdir, templatedir, default_filenames):
    """Read the template specification file in the template workflow folder.
    If the file is not found None is returned.

    Parameters
    ----------
    projectmeta: dict
        Project metadata information from the project description file.
    projectdir: string
        Path to the base directory containing the project resource files.
    templatedir: string
        Path to the target directory for template resource files.
    default_filenames: list(string)
        List of default file names for workflow templates.

    Returns
    -------
    flowserv.model.template.base.WorkflowTemplate
    """
    if WORKFLOWSPEC in projectmeta:
        # If the project metadata contains the workflow specification we can
        # return immediately
        return WorkflowTemplate.from_dict(
            doc=projectmeta.get(WORKFLOWSPEC),
            sourcedir=templatedir,
            validate=True
        )
    # The list of candidate file names depends on whether the project metadata
    # contains a reference to the specification file or if we are looking for
    # a default file.
    if SPECFILE in projectmeta:
        candidates = [projectmeta[SPECFILE]]
    else:
        candidates = list()
        for filename in default_filenames:
            candidates.append(filename)
    for filename in candidates:
        filename = os.path.join(projectdir, filename)
        if os.path.isfile(filename):
            # Read template from file. If no error occurs the folder
            # contains a valid template.
            return WorkflowTemplate.from_dict(
                doc=util.read_object(filename),
                sourcedir=templatedir,
                validate=True
            )
