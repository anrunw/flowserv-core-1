# This file is part of the Reproducible and Reusable Data Analysis Workflow
# Server (flowServ).
#
# Copyright (C) 2019-2020 NYU.
#
# flowServ is free software; you can redistribute it and/or modify it under the
# terms of the MIT License; see LICENSE file for more details.

"""Helper functions for the remote service client."""

from typing import Dict, Optional

import requests

import flowserv.config.client as config


"""Name of the header element that contains the access token."""
HEADER_TOKEN = 'api_key'


def delete(url: str):
    """Send DELETE request to given URL.

    Parameters
    ----------
    url: string
        Request URL.
    """
    r = requests.delete(url, headers=headers())
    r.raise_for_status()


def get(url: str) -> Dict:
    """Send GET request to given URL and return the JSON body.

    Parameters
    ----------
    url: string
        Request URL.

    Returns
    -------
    dict
    """
    r = requests.get(url, headers=headers())
    r.raise_for_status()
    return r.json()


def headers() -> Dict:
    """Get dictionary of header elements for HTTP requests to a remote API.

    Returns
    -------
    dict
    """
    return {HEADER_TOKEN: config.ACCESS_TOKEN()}


def post(url: str, data: Optional[Dict] = None) -> Dict:
    """Send POST request with given (optional) body to a URL. Returns the
    JSON body from the response.

    Parameters
    ----------
    url: string
        Request URL.
    data: dict, default=None
        Optional request body.

    Returns
    -------
    dict
    """
    r = requests.post(url, json=data, headers=headers())
    r.raise_for_status()
    return r.json()
