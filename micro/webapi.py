# webapi
# Released into the public domain
# https://github.com/noyainrain/micro/blob/master/micro/webapi.py

"""Simple JSON REST API client."""

import errno
import json
from json import JSONDecodeError
from os import strerror
from typing import Dict, Union, cast
from urllib.parse import SplitResult, urlencode, urlsplit
from warnings import catch_warnings

from tornado.httpclient import AsyncHTTPClient, HTTPRequest, HTTPResponse
from tornado.simple_httpclient import HTTPStreamClosedError, HTTPTimeoutError

class WebAPIError(Exception):
    """Raised for JSON REST API errors."""

    @property
    def error(self) -> Dict[str, object]:
        """Error object."""
        return self.args[1] # type: ignore

    @property
    def status(self) -> int:
        """Associated HTTP status code."""
        return self.args[2] # type: ignore

    def __str__(self) -> str:
        return self.args[0] # type: ignore

class CommunicationError(Exception):
    """Raised if communication with the web API fails."""

async def fetch(request: Union[HTTPRequest, str], raise_error: bool = True,
                **kwargs: object) -> HTTPResponse:
    """Execute a *request*.

    Utility wrapper around :meth:`AsyncHTTPClient.fetch` which encapsulates any IO related error as
    :class:`CommunicationError`.
    """
    url, method = (
        (request, kwargs.get('method', 'GET')) if isinstance(request, str) else
        (request.url, request.method))
    try:
        # raise_error=False triggers a deprecation warning in Tornado 5. Reraise suppressed
        # IO errors to match the future behavior.
        with catch_warnings(record=True):
            response = await AsyncHTTPClient().fetch(request, raise_error=raise_error, **kwargs)
            if response.code == 599:
                assert response.error is not None
                raise response.error
            return response
    except HTTPStreamClosedError:
        raise CommunicationError('{} for {} {}'.format(strerror(errno.ESHUTDOWN), method, url))
    except HTTPTimeoutError:
        raise CommunicationError('{} for {} {}'.format(strerror(errno.ETIMEDOUT), method, url))
    except OSError as e:
        raise CommunicationError('{} for {} {}'.format(e, method, url))

class WebAPI:
    """Simple JSON REST API client.

    .. attribute:: url

       Base URL of the web API. Must be an HTTP/S URL and may not contain anything after path.

    .. attribute:: query

       Default query parameters for web API calls.

    .. attribute:: headers

       Supplied HTTP headers for web API calls.
    """

    def __init__(self, url: str, *, query: Dict[str, str] = {},
                 headers: Dict[str, str] = {}) -> None:
        urlparts = urlsplit(url)
        if not (urlparts.scheme in {'http', 'https'} and urlparts.netloc and
                not any([urlparts.query, urlparts.fragment])):
            raise ValueError('Bad url {!r}'.format(url))
        self.url = url
        self.query = query
        self.headers = headers
        self._urlparts = urlparts

    async def call(self, method: str, url: str, *, args: Dict[str, object] = None,
                   query: Dict[str, str] = {}) -> Dict[str, object]:
        """Call a *method* on the endpoint at *url* and return the result.

        *method* is an HTTP method (e.g. ``GET`` or ``POST``). The endpoint *url* is relative to
        :attr:`url` and may not contain anything after path. *args* are supplied as JSON payload.
        *query* are the supplied query parameters.

        If an error occurs, a :exc:`WebAPIError` is raised. For any IO related errors, a
        :exc:`CommunicationError` is raised.
        """
        if not method.strip():
            raise ValueError('Blank method')
        urlparts = urlsplit(url)
        if any([urlparts.scheme, urlparts.netloc, urlparts.query, urlparts.fragment]):
            raise ValueError('Bad url {!r}'.format(url))

        query = dict(list(self.query.items()) + list(query.items()))
        url = SplitResult(
            self._urlparts.scheme, self._urlparts.netloc, self._urlparts.path + urlparts.path,
            urlencode(query), ''
        ).geturl()
        body = None if args is None else json.dumps(args)

        response = await fetch(url, raise_error=False, method=method, headers=self.headers,
                               body=body)
        try:
            result = cast(object, json.loads(response.body.decode()))
            if not isinstance(result, dict):
                raise TypeError()
        except (UnicodeDecodeError, JSONDecodeError, TypeError):
            raise CommunicationError('Bad response format for {} {}'.format(method, url))

        if not 200 <= response.code < 300:
            raise WebAPIError('Error {} for {} {}'.format(response.code, method, url), result,
                              response.code)
        return result
