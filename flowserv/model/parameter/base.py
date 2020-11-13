# This file is part of the Reproducible and Reusable Data Analysis Workflow
# Server (flowServ).
#
# Copyright (C) 2019-2020 NYU.
#
# flowServ is free software; you can redistribute it and/or modify it under the
# terms of the MIT License; see LICENSE file for more details.

"""Base class for workflow template parameters. Each parameter has a set of
properties that are used to (i) identify the parameter, (ii) define a nested
parameter structure, and (iii) render UI forms to collect parameter values.
"""

from __future__ import annotations
from abc import ABCMeta, abstractmethod
from typing import Any, Dict, Optional

import flowserv.util as util


"""Labels for general workflow declaration elements."""

DEFAULT = 'defaultValue'
GROUP = 'group'
HELP = 'help'
INDEX = 'index'
LABEL = 'label'
NAME = 'name'
TYPE = 'dtype'
REQUIRED = 'isRequired'

MANDATORY = [NAME, TYPE, INDEX, REQUIRED]
OPTIONAL = [LABEL, HELP, DEFAULT, GROUP]


"""Unique parameter type identifier."""
PARA_BOOL = 'bool'
PARA_FILE = 'file'
PARA_FLOAT = 'float'
PARA_INT = 'int'
PARA_SELECT = 'select'
PARA_STRING = 'string'


class Parameter(metaclass=ABCMeta):
    """Base class for template parameters. The base class maintains the unique
    parameter name, the data type identifier, the human-readable label and the
    description for display purposes, the is required flag, an optional default
    value, the index position for input form rendering, and the identifier for
    the parameter group.

    Implementing classes have to provide a static .from_dict() method that
    returns an instance of the class from a dictionary serialization. The
    dictionary serializations for each class are generated by the .to_dict()
    method.
    """
    def __init__(
        self, dtype: str, name: str, index: Optional[int] = 0,
        label: Optional[str] = None, help: Optional[str] = None,
        default: Optional[Any] = None, required: Optional[bool] = False,
        group: Optional[str] = None
    ):
        """Initialize the base properties for a template parameter.

        Parameters
        ----------
        dtype: string
            Parameter type identifier.
        name: string
            Unique parameter identifier
        index: int, default=0
            Index position of the parameter (for display purposes).
        label: string, default=None
            Human-readable parameter name.
        help: string, default=None
            Descriptive text for the parameter.
        default: any, default=None
            Optional default value.
        required: bool, default=False
            Is required flag.
        group: string, default=None
            Optional identifier for parameter group that this parameter
            belongs to.
        """
        self.dtype = dtype
        self.name = name
        self.index = index
        self.label = label
        self.help = help
        self.default = default
        self.required = required
        self.group = group

    def display_name(self) -> str:
        """Human-readable display name for the parameter. The default display
        name is the defined label. If no label is defined the parameter name is
        returned.

        Returns
        -------
        str
        """
        return self.label if self.label is not None else self.name

    @staticmethod
    @abstractmethod
    def from_dict(cls, doc: Dict, validate: Optional[bool] = True) -> Parameter:
        """Get instance of implementing class from dictionary serialization.

        Parameters
        ----------
        doc: dict
            Dictionary serialization for a parameter.
        validate: bool, default=True
            Validate the serialized object if True.

        Returns
        -------
        flowserv.model.parameter.base.Parameter

        Raises
        ------
        flowserv.error.InvalidParameterError
        """
        raise NotImplementedError()  # pragma: no cover

    def is_bool(self) -> bool:
        """Test if the parameter is of type Bool.

        Returns
        -------
        bool
        """
        return self.dtype == PARA_BOOL

    def is_file(self) -> bool:
        """Test if the parameter is of type File.

        Returns
        -------
        bool
        """
        return self.dtype == PARA_FILE

    def is_float(self) -> bool:
        """Test if the parameter is of type Float.

        Returns
        -------
        bool
        """
        return self.dtype == PARA_FLOAT

    def is_int(self) -> bool:
        """Test if the parameter is of type Int.

        Returns
        -------
        bool
        """
        return self.dtype == PARA_INT

    def is_numeric(self) -> bool:
        """Test if the parameter is of type Numeric.

        Parameters
        ----------
        para: flowserv.model.parameter.base.Parameter
            Template parameter definition.

        Returns
        -------
        bool
        """
        return self.is_float() or self.is_int()

    def is_select(self) -> bool:
        """Test if the parameter is of type Select.

        Returns
        -------
        bool
        """
        return self.dtype == PARA_SELECT

    def is_string(self) -> bool:
        """Test if the parameter is of type String.

        Returns
        -------
        bool
        """
        return self.dtype == PARA_STRING

    def prompt(self) -> str:
        """Get default input prompt for the parameter declaration. The prompt
        contains an indication of the data type, the parameter name and the
        default value (if defined).

        Returns
        -------
        string
        """
        val = '{} ({})'.format(self.display_name(), self.dtype)
        if self.default is not None:
            val += " [default '{}']".format(self.default)
        return val + ' $> '

    @abstractmethod
    def to_argument(self, value: Any) -> Any:
        """Validate the given argument value for the parameter type. Returns
        the argument representation for the value that is used to replace
        references to the parameter in workflow templates.

        Raises an InvalidArgumentError if the given value is not valid for the
        parameter type.

        Parameters
        ----------
        value: any
            User-provided value for a template parameter.

        Returns
        -------
        sting, float, or int

        Raises
        ------
        flowserv.error.InvalidArgumentError
        """
        raise NotImplementedError()  # pragma: no cover

    def to_dict(self) -> Dict:
        """Get dictionary serialization for the parameter declaration.
        Implementing classes can add elements to the base dictionary.

        Returns
        -------
        dict
        """
        return {
            TYPE: self.dtype,
            NAME: self.name,
            INDEX: self.index,
            LABEL: self.label,
            HELP: self.help,
            DEFAULT: self.default,
            REQUIRED: self.required,
            GROUP: self.group
        }


class ParameterGroup(object):
    """Parameter groups are identifiable sets of parameters. These sets are
    primarily intended for display purposes in the front-end. Therefore, each
    group has a display name and an index position that defines the sort order
    for groups.
    """
    def __init__(self, name: str, title: str, index: int):
        """Initialize the object properties.

        Parameters
        ----------
        name: string
            Unique group identifier
        title: string
            Human-readable group name
        index: int
            Group sort order index
        """
        self.name = name
        self.title = title
        self.index = index

    @classmethod
    def from_dict(cls, doc, validate=True):
        """Create object instance from dictionary serialization.

        Parameters
        ----------
        doc: dict
            Dictionary serialization for parameter group handles
        validate: bool, default=True
            Validate the serialization if True.

        Returns
        -------
        flowserv.model.parameter.base.ParameterGroup

        Raises
        ------
        ValueError
        """
        if validate:
            util.validate_doc(
                doc,
                mandatory=['name', 'title', 'index']
            )
        return cls(
            name=doc['name'],
            title=doc['title'],
            index=doc['index']
        )

    def to_dict(self):
        """Get dictionary serialization for parameter group handle.

        Returns
        -------
        dict
        """
        return {
            'name': self.name,
            'title': self.title,
            'index': self.index
        }
