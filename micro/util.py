# micro
# Copyright (C) 2020 micro contributors
#
# This program is free software: you can redistribute it and/or modify it under the terms of the GNU
# Lesser General Public License as published by the Free Software Foundation, either version 3 of
# the License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without
# even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public License along with this program.
# If not, see <http://www.gnu.org/licenses/>.

"""Various utilities.

.. data:: ON

   Indicates that something is enabled. Useful for feature flags in connection with overloading.
"""

import argparse
from argparse import ArgumentParser
from asyncio import CancelledError, Task # pylint: disable=unused-import; typing
import builtins
from collections import OrderedDict
from datetime import datetime, timezone
import logging
from logging import StreamHandler, getLogger
from numbers import Real
from os import walk
from pathlib import Path
import random
import re
import string
import sys
from typing import Coroutine, List, Optional, Sequence, Type, TypeVar, Union, cast

from tornado.log import LogFormatter

from .jsonredis import ExpectFunc, expect_type # pylint: disable=unused-import; export

class OnType:
    """Type of :data:`ON`."""

ON = OnType()

_T = TypeVar('_T')
_U = TypeVar('_U')

def str_or_none(str: str) -> Optional[str]:
    """Return *str* unmodified if it has content, otherwise return ``None``.

    A string is considered to have content if it contains at least one non-whitespace character.
    """
    return str if str and str.strip() else None

def randstr(length: int = 16, charset: str = string.ascii_lowercase) -> str:
    """Generate a random string.

    The string will have the given *length* and consist of characters from *charset*.
    """
    return ''.join(random.choice(charset) for i in range(length))

def parse_isotime(isotime: str) -> datetime:
    """Parse an ISO 8601 time string into a :class:`datetime.datetime`.

    Note that this rudimentary parser makes bold assumptions about the format: The first six
    components are always interpreted as year, month, day and optionally hour, minute and second.
    Everything else, i.e. microsecond and time zone information, is ignored.
    """
    try:
        values = [int(t) for t in re.split(r'\D', isotime)[:6]]
        year, month, day = values[:3]
        hour, minute, second = (values[3:] + [0, 0, 0])[:3]
        return datetime(year, month, day, hour, minute, second, tzinfo=timezone.utc)
    except (TypeError, ValueError) as e:
        raise ValueError('isotime_bad_format') from e

def parse_slice(str: str, limit: int = None) -> slice:
    """Parse a slice string into a :class:`slice`.

    The slice string *str* has the format ``start:stop``. Negative values are not supported. The
    maximum size of the slice may be given by *limit*, which caps the maximum value of *stop* at
    ``start + limit``."""
    match = re.fullmatch(r'(\d*):(\d*)', str)
    if not match:
        raise ValueError('str_bad_format')

    start = int(match.group(1)) if match.group(1) else None
    stop = int(match.group(2)) if match.group(2) else None
    if limit:
        if stop is None:
            stop = sys.maxsize
        stop = min(stop, (start or 0) + limit)
    return slice(start, stop)

def check_polyglot(polyglot):
    """Check the *polyglot* string."""
    if not all(re.fullmatch('[a-z]{2}', l) for l in polyglot):
        raise ValueError('polyglot_language_bad_format')
    if not all(str_or_none(v) for v in polyglot.values()):
        raise ValueError('polyglot_value_empty')
    return polyglot

def check_email(email: str) -> None:
    """Check the *email* address."""
    if not str_or_none(email):
        raise ValueError('email_empty')
    if len(email.splitlines()) > 1:
        raise ValueError('email_newline')

def look_up_files(paths: Sequence[str], *, top: Union[str, Path] = Path()) -> List[Path]:
    """Compile a list of files at the given *paths*.

    Glob patterns are expanded. For directories, files are included recursively. A leading `!`
    excludes previously included entries. *top* is the top-level directory for the lookup and
    defaults to the current directory.
    """
    if isinstance(top, str):
        top = Path(top)
    # Use like ordered set
    files = OrderedDict() # type: OrderedDict[Path, None]
    for pattern in paths:
        if pattern.startswith('!'):
            for path in top.glob(pattern[1:]):
                if path.is_dir():
                    for included in list(files):
                        if path in included.parents:
                            files.pop(included)
                else:
                    files.pop(path, None)
        else:
            expanded = sorted(top.glob(pattern))
            if not expanded:
                raise ValueError('No file matching paths entry {}'.format(pattern))
            for path in expanded:
                if path.is_dir():
                    for dirpath, _, filenames in walk(str(path)):
                        files.update((Path(dirpath) / name, None) for name in filenames)
                else:
                    files[path] = None
    return list(files)

def make_command_line_parser() -> ArgumentParser:
    """Create a :class:`argparse.ArgumentParser` handy for micro apps.

    The parser is preconfigured to handle common command line arguments.
    """
    parser = ArgumentParser(argument_default=argparse.SUPPRESS)
    parser.add_argument(
        '--port',
        help='Port number the server listens on for incoming connections. Defaults to 8080.')
    parser.add_argument(
        '--url',
        help='Public URL of the server. Defaults to http://localhost with the port option value.')
    parser.add_argument('--debug', action='store_true', help='Debug mode.')
    parser.add_argument(
        '--redis-url',
        help='URL of the Redis database, where path represents the database index. May be relative to redis://localhost/. Defaults to redis://localhost/0.')
    parser.add_argument(
        '--files-path',
        help='Directory where files are stored. Must be read and writable by the application. Defaults to data.')
    parser.add_argument(
        '--smtp-url',
        help='URL of the SMTP server to use for outgoing email. Only host and port are considered, which default to localhost and 25 respectively.')
    parser.add_argument(
        '--video-service-keys', nargs='*', metavar='ID KEY',
        help='Map of video service keys, required for video content from streaming platforms. Available services are "youtube". Keys can be retrieved from https://console.developers.google.com/apis/credentials (YouTube).')
    parser.add_argument(
        '--client-map-service-key',
        help='Public Mapbox access token, required for location related features. Can be retrieved from https://www.mapbox.com/account/access-tokens.')
    return parser

def setup_logging(debug=False):
    """Configure logging handy for micro apps.

    By default, all :attr:`logging.INFO` messages are logged, along with only :attr:`loggin.ERROR`
    messages for the access log. In *debug* mode, the access log is not filtered.
    """
    logger = getLogger()
    handler = StreamHandler()
    handler.setFormatter(LogFormatter())
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    if not debug:
        getLogger('tornado.access').setLevel(logging.ERROR)

async def cancel(task: 'Task[_T]') -> None:
    """Cancel the *task*."""
    try:
        task.cancel()
        await task
    except CancelledError:
        pass

def run_instant(coro: Coroutine[object, object, _T]) -> _T:
    """Run the coroutine *coro* at once and return the result.

    If *coro* does not return instantly, i.e. awaits something, a :exc:`ValueError` is raised.
    """
    try:
        coro.send(None)
        raise ValueError('Awaiting coro')
    except StopIteration as e:
        return cast(_T, e.value)

def expect_opt_type(cls: Type[_T]) -> ExpectFunc[Optional[_T]]:
    """Return a function that asserts a given *obj* is an instance of *cls* or ``None``."""
    def _f(obj: Optional[object]) -> Optional[_T]:
        if obj is not None and not isinstance(obj, cls):
            raise TypeError()
        return obj
    return _f

def version(v):
    """Decorator for creating a versioned function.

    When a versioned function is called, the implementation for the version given by an additional
    keyword argument *v* is executed. If *v* is not specified, the default implementation is used.

    *v* is the version of the decorated function, which also serves as default implementation.

    The returned object provides a decorator `version(v)`, which can be used to define additional
    versions.
    """
    versions = {}

    def _wrapper(*args, v=v, **kwargs):
        try:
            func = versions[v]
        except KeyError as e:
            raise NotImplementedError() from e
        return func(*args, **kwargs)

    def _version(v):
        def _decorator(func):
            versions[v] = func
            return _wrapper
        return _decorator
    _wrapper.version = _version

    def _decorator(func):
        versions[v] = func
        return _wrapper
    return _decorator

class Expect:
    """Compilation of type assertions.

    .. attribute:: str

       Assert that *obj* is a :class:`str`.

    .. attribute:: float

       Assert that *obj* is a :class:`float`.
    """

    str = expect_type(builtins.str)
    float = expect_type(Real) # type: ignore

    @staticmethod
    def list(expect_item: ExpectFunc[_T]) -> ExpectFunc[List[_T]]:
        """Return a function that asserts *obj* is a :class:`list`.

        The type of each item is asserted with *expect_item*.
        """
        def _f(obj: object) -> List[_T]:
            if not isinstance(obj, builtins.list):
                raise TypeError()
            for item in obj:
                expect_item(item)
            return obj
        return _f

    @staticmethod
    def opt(expect: ExpectFunc[_T]) -> ExpectFunc[Optional[_T]]:
        """Return a function that asserts *obj* is ``None`` or meets *expect*."""
        def _f(obj: object) -> Optional[_T]:
            return None if obj is None else expect(obj)
        return _f
