# This file is part of the Reproducible and Reusable Data Analysis Workflow
# Server (flowServ).
#
# Copyright (C) 2019-2020 NYU.
#
# flowServ is free software; you can redistribute it and/or modify it under the
# terms of the MIT License; see LICENSE file for more details.

"""Definition of schema components for benchmark results. The schema definition
is part of the extended workflow template specification that is used to define
benchmarks.
"""

import flowserv.error as err
import flowserv.util as util
import flowserv.model.parameter.declaration as pd


"""Supported data types for result values."""
DATA_TYPES = [pd.DT_DECIMAL, pd.DT_INTEGER, pd.DT_STRING]


"""Labels for serialization."""
# Column specification
COLUMN_ID = 'id'
COLUMN_NAME = 'name'
COLUMN_PATH = 'path'
COLUMN_REQUIRED = 'required'
COLUMN_TYPE = 'type'
# Leader board default sort order
SORT_ID = COLUMN_ID
SORT_DESC = 'sortDesc'
# Schema specification
SCHEMA_RESULTFILE = 'file'
SCHEMA_COLUMNS = 'schema'
SCHEMA_ORDERBY = 'orderBy'


class ResultColumn(object):
    """Column in the result schema of a benchmark. Each column has a unique
    identifier and unique name. The identifier is used as column name in the
    database schema. The name is for display purposes in a user interface.
    The optional path element is used to extract the column value from nested
    result files.
    """
    def __init__(self, identifier, name, data_type, path=None, required=None):
        """Initialize the unique column identifier, name, and the data type. If
        the value of data_type is not in the list of supported data types an
        error is raised.

        The optional path element references the column value in nested result
        files. If no path is given the column identifier is used instead.

        Parameters
        ----------
        identifier: string
            Unique column identifier
        name: string
            Unique column name
        data_type: string
            Data type identifier
        path: string, optional
            Path to column value in nested result files.
        required: bool, optional
            Indicates whether a value is expected for this column in every
            benchmark run result

        Raises
        ------
        flowserv.error.InvalidTemplateError
        """
        # Raise error if the data type value is not in the list of supported
        # data types
        if data_type not in DATA_TYPES:
            msg = "unknown data type '{}'"
            raise err.InvalidTemplateError(msg.format(data_type))
        self.identifier = identifier
        self.name = name
        self.data_type = data_type
        self.path = path
        self.required = required if required is not None else True

    @classmethod
    def from_dict(cls, doc):
        """Get an instance of the column from the dictionary serialization.
        Raises an error if the given dictionary does not contain the expected
        elements as generated by the to_dict() method of the class.

        Parameters
        ----------
        doc: dict
            Dictionary serialization of a column object

        Returns
        -------
        flowserv.model.template.schema.ResultColumn

        Raises
        ------
        flowserv.error.InvalidTemplateError
        """
        # Validate the serialization dictionary
        try:
            util.validate_doc(
                doc,
                mandatory=[COLUMN_ID, COLUMN_NAME, COLUMN_TYPE],
                optional=[COLUMN_PATH, COLUMN_REQUIRED]
            )
        except ValueError as ex:
            raise err.InvalidTemplateError(str(ex))
        # Return instance of the column object
        return cls(
            identifier=doc[COLUMN_ID],
            name=doc[COLUMN_NAME],
            data_type=doc[COLUMN_TYPE],
            path=doc.get(COLUMN_PATH),
            required=doc.get(COLUMN_REQUIRED)
        )

    def jpath(self):
        """The Json path for a result column is a list of element keys that
        reference the column value in a nested document. If the internal path
        variable is not set the column identifier is returned as the only
        element in the path.

        Returns
        -------
        list(string)
        """
        if self.path is not None:
            return self.path.split('/')
        else:
            return list([self.identifier])

    def to_dict(self):
        """Get dictionary serialization for the column object.

        Returns
        -------
        dict
        """
        doc = {
            COLUMN_ID: self.identifier,
            COLUMN_NAME: self.name,
            COLUMN_TYPE: self.data_type,
            COLUMN_REQUIRED: self.required
        }
        # Add the path expression if it is given
        if self.path is not None:
            doc[COLUMN_PATH] = self.path
        return doc


class ResultSchema(object):
    """The result schema of a benchmark run is a collection of columns. The
    result schema is used to generate leader boards for benchmarks.

    The schema also contains the identifier of the output file that contains
    the result object. The result object that is generated by each benchmark
    run is expected to contain a value for each required columns in the schema.
    """
    def __init__(self, result_file=None, columns=None, order_by=None):
        """Initialize the result file identifier, schema columns, and the
        default sort order.

        Parameters
        ----------
        result_file: string, optional
            Identifier of the benchmark run result file that contains the
            analytics results.
        columns: list(flowserv.model.template.schema.ResultColumn), optional
            List of columns in the result object
        order_by: list(flowserv.model.template.schema.SortColumn), optional
            List of columns that define the default sort order for entries in
            the leader board.
        """
        self.result_file = result_file
        self.columns = columns if columns is not None else list()
        self.order_by = order_by if order_by is not None else list()

    @classmethod
    def from_dict(cls, doc):
        """Get an instance of the schema from a dictionary serialization.
        Raises an error if the given dictionary does not contain the expected
        elements as generated by the to_dict() method of the class or if the
        names or identifier of columns are not unique.

        Returns None if the given document is None.

        Parameters
        ----------
        doc: dict
            Dictionary serialization of a benchmark result schema object

        Returns
        -------
        flowserv.model.template.schema.ResultSchema

        Raises
        ------
        flowserv.error.InvalidTemplateError
        """
        # Return None if no document is given
        if doc is None:
            return None
        # Validate the serialization dictionary
        try:
            util.validate_doc(
                doc,
                mandatory=[SCHEMA_RESULTFILE, SCHEMA_COLUMNS],
                optional=[SCHEMA_ORDERBY]
            )
        except ValueError as ex:
            raise err.InvalidTemplateError(str(ex))
        # Identifier of the output file that contains the result object
        file_id = doc[SCHEMA_RESULTFILE]
        # Get column list. Ensure that all column names and identifier are
        # unique
        columns = [ResultColumn.from_dict(c) for c in doc[SCHEMA_COLUMNS]]
        ids = set()
        names = set()
        for col in columns:
            if col.identifier in ids:
                msg = 'duplicate column identifier \'{}\''
                raise err.InvalidTemplateError(msg.format(col.identifier))
            ids.add(col.identifier)
            if col.name in names:
                msg = 'not unique column name \'{}\''
                raise err.InvalidTemplateError(msg.format(col.name))
            names.add(col.name)
        # Get optional default sort statement for the ranking
        order_by = list()
        if SCHEMA_ORDERBY in doc:
            # Ensure that the column identifier reference columns in the schema
            for c in doc[SCHEMA_ORDERBY]:
                col = SortColumn.from_dict(c)
                if col.identifier not in ids:
                    msg = 'unknown column \'{}\''
                    raise err.InvalidTemplateError(msg.format(col.identifier))
                order_by.append(col)
        # Return benchmark schema object
        return cls(
            result_file=file_id,
            columns=columns,
            order_by=order_by
        )

    def is_empty(self):
        """Test of the schema contains any columns or if it is empty.

        Returns
        -------
        bool
        """
        return len(self.columns) == 0

    def get_default_order(self):
        """By default the first column in the schema is used as the sort column.
        Values in the column are sorted in descending order.

        Returns
        -------
        list(flowserv.model.template.schema.SortColumn)
        """
        if len(self.order_by) > 0:
            return self.order_by
        col = self.columns[0]
        return [SortColumn(identifier=col.identifier, sort_desc=True)]

    def rename(self, prefix=None):
        """Create a mapping of column names in the schema to a fixed naming
        patttern where each column is identified by a given prefix and a unique
        counter values. The result is a dictionary that maps the original column
        names to the renamed ones. This dictionary can for example be used to
        generate SQL SELECT clauses when querying workflow results from the
        respective results table.

        Parameters
        ----------
        prefix: string, optional
            Optional column name prefix. If not given the default prefix 'col'
            is used

        Returns
        -------
        dict
        """
        # Use the default prefix if none is given
        prefix = prefix if prefix is not None else 'col'
        # Mapping of original column names to their query name.
        mapping = dict()
        for col in self.columns:
            cid = '{}{}'.format(prefix, len(mapping))
            mapping[col.identifier] = cid
        return mapping

    def to_dict(self):
        """Get dictionary serialization for the result schema object.

        Returns
        -------
        dict
        """
        return {
            SCHEMA_RESULTFILE: self.result_file,
            SCHEMA_COLUMNS: [col.to_dict() for col in self.columns],
            SCHEMA_ORDERBY: [col.to_dict() for col in self.order_by]
        }


class SortColumn(object):
    """The sort column defines part of an ORDER BY statement that is used to
    sort benchmark results when creating the benchmark leader board. Each object
    contains a reference to a result column and a flag indicating the sort
    order for values in the column.
    """
    def __init__(self, identifier, sort_desc=None):
        """Initialize the object properties.

        Parameters
        ----------
        identifier: string
            Unique column identifier
        sort_desc: bool, optional
            Sort values in descending order if True or in ascending order
            otherwise
        """
        self.identifier = identifier
        self.sort_desc = sort_desc if sort_desc is not None else True

    @classmethod
    def from_dict(cls, doc):
        """Get an instance of the sort column from the dictionary serialization.
        Raises an error if the given dictionary does not contain the expected
        elements as generated by the to_dict() method of the class.

        Parameters
        ----------
        doc: dict
            Dictionary serialization of a column object

        Returns
        -------
        flowserv.model.template.schema.SortColumn

        Raises
        ------
        flowserv.error.InvalidTemplateError
        """
        # Validate the serialization dictionary
        try:
            util.validate_doc(
                doc,
                mandatory=[SORT_ID],
                optional=[SORT_DESC]
            )
        except ValueError as ex:
            raise err.InvalidTemplateError(str(ex))
        sort_desc = None
        if SORT_DESC in doc:
            sort_desc = doc[SORT_DESC]
        # Return instance of the column object
        return cls(identifier=doc[SORT_ID], sort_desc=sort_desc)

    def to_dict(self):
        """Get dictionary serialization for the sort column object.

        Returns
        -------
        dict
        """
        return {SORT_ID: self.identifier, SORT_DESC: self.sort_desc}
