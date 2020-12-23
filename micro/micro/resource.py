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

"""Functionality for handling web resources.

.. data:: HandleResourceFunc

   Function of the form ``handle(url, content_type, data, analyzer)`` which processes a web resource
   and returns a description of it. The resource is given by its *url*, *content_type* and content
   *data*. Additionally, the active *analyzer* is available, useful to :meth:`Analyzer.analyze`
   subresources. If the function cannot handle the resource in question, ``None`` is returned. May
   be ``async``.
"""

from __future__ import annotations

from asyncio import get_event_loop
from collections import OrderedDict
from datetime import datetime, timedelta
from functools import partial
from hashlib import sha256
from html.parser import HTMLParser
from inspect import isawaitable
import mimetypes
from mimetypes import guess_extension, guess_type
from os import listdir
from pathlib import Path
from typing import Awaitable, Callable, Dict, Iterable, List, Optional, Tuple, Union, cast
from urllib.parse import parse_qsl, urljoin, urlsplit

from tornado.httpclient import HTTPClientError

from . import error
from .core import RewriteFunc
from .error import Error
from .util import Expect, expect_type, str_or_none
from .webapi import CommunicationError, WebAPI, fetch

HandleResourceFunc = Callable[[str, str, bytes, 'Analyzer'],
                              Union[Optional['Resource'], Awaitable[Optional['Resource']]]]

# Skip system defaults to make sure convertion from media type to extension is invertible
mimetypes.init(files=())

class Resource:
    """See :ref:`Resource`."""

    @staticmethod
    def parse(data: Dict[str, object], **args: object) -> 'Resource':
        """See :meth:`JSONifiableWithParse.parse`."""
        # pylint: disable=unused-argument; part of API
        return Resource(
            Expect.str(data.get('url')), Expect.str(data.get('content_type')),
            description=Expect.opt(Expect.str)(data.get('description')),
            image=Expect.opt(expect_type(Image))(data.get('image')))

    def __init__(self, url: str, content_type: str, *, description: str = None,
                 image: 'Image' = None) -> None:
        if str_or_none(url) is None:
            raise error.ValueError('Blank url')
        if str_or_none(content_type) is None:
            raise error.ValueError('Blank content_type')
        self.url = url
        self.content_type = content_type
        self.description = str_or_none(description) if description else None
        self.image = image

    def json(self, restricted: bool = False, include: bool = False, *,
             rewrite: RewriteFunc = None) -> Dict[str, object]:
        """See :meth:`JSONifiable.json`."""
        # pylint: disable=unused-argument; part of API
        return {
            '__type__': type(self).__name__,
            'url': rewrite(self.url) if rewrite else self.url,
            'content_type': self.content_type,
            'description': self.description,
            'image': self.image.json(rewrite=rewrite) if self.image else None
        }

class Image(Resource):
    """See :ref:`Image`."""

    @staticmethod
    def parse(data: Dict[str, object], **args: object) -> 'Image':
        resource = Resource.parse(data, **args)
        return Image(resource.url, resource.content_type, description=resource.description)

    def __init__(self, url: str, content_type: str, *, description: str = None) -> None:
        super().__init__(url, content_type, description=description)

class Video(Resource):
    """See :ref:`Video`."""

    @staticmethod
    def parse(data: Dict[str, object], **args: object) -> 'Video':
        resource = Resource.parse(data, **args)
        return Video(resource.url, resource.content_type, description=resource.description,
                     image=resource.image)

class Analyzer:
    """Web resource analyzer.

    .. attribute:: handlers

       List of web resource handlers to use for analyzing. By default all handlers included with the
       module are enabled.

    .. attribute:: files

       File storage to resolve file URLs.
    """

    _CACHE_SIZE = 128
    _CACHE_TTL = timedelta(hours=1)

    def __init__(
            self, *, handlers: List[HandleResourceFunc] = None, files: Files = None,
            _cache: 'OrderedDict[str, Tuple[Resource, datetime]]' = None,
            _stack: List[str] = None) -> None:
        self.handlers = ([handle_image, handle_webpage] if handlers is None
                         else list(handlers)) # type: List[HandleResourceFunc]
        self.files = files
        self._cache = OrderedDict() if _cache is None else _cache
        self._stack = [] if _stack is None else _stack

    async def analyze(self, url: str) -> Resource:
        """Analyze the web resource at *url* and return a description of it.

        *url* is an absolute HTTP(S) URL. If :attr:`files` is set, file URLs are also valid.

        If there is a problem fetching or analyzing the resource, a :exc:`CommunicationError` or
        :exc:`AnalysisError` is raised respectively.

        Results are cached for about one hour.
        """
        if len(self._stack) == 3:
            raise _LoopError()

        try:
            return self._get_cache(url)
        except KeyError:
            pass

        data, content_type, effective_url = await self.fetch(url)
        resource = None
        analyzer = Analyzer(handlers=self.handlers, files=self.files, _cache=self._cache,
                            _stack=self._stack + [url])
        for handle in self.handlers:
            try:
                result = handle(effective_url, content_type, data, analyzer)
                resource = (await cast(Awaitable[Optional[Resource]], result) if isawaitable(result)
                            else cast(Optional[Resource], result))
            except _LoopError:
                if self._stack:
                    raise
                raise BrokenResourceError('Loop analyzing {}'.format(url)) from None
            if resource:
                break
        if not resource:
            resource = Resource(effective_url, content_type)

        self._set_cache(url, resource)
        self._set_cache(resource.url, resource)
        return resource

    async def fetch(self, url: str) -> Tuple[bytes, str, str]:
        """Fetch the web resource at *url*.

        The data, media type and effective URL (after any redirects) are returned.
        """
        if self.files and urlsplit(url).scheme == 'file':
            try:
                data, content_type = await self.files.read(url)
                return data, content_type, url
            except LookupError as e:
                raise NoResourceError(f'No resource at {url}') from e

        try:
            response = await fetch(url)
            return (response.body, response.headers['Content-Type'].split(';', 1)[0],
                    response.effective_url)
        except ValueError as e:
            raise error.ValueError(f'Bad url scheme {url}') from e
        except HTTPClientError as e:
            if e.code in (404, 410):
                raise NoResourceError(f'No resource at {url}') from e
            if e.code in (401, 402, 403, 405, 451):
                raise ForbiddenResourceError(f'Forbidden resource at {url}') from e
            raise CommunicationError(f'Unexpected response status {e.code} for GET {url}') from e

    def _get_cache(self, url: str) -> Resource:
        resource, expires = self._cache[url]
        if datetime.utcnow() >= expires:
            del self._cache[url]
            raise KeyError(url)
        return resource

    def _set_cache(self, url: str, resource: Resource) -> None:
        try:
            del self._cache[url]
        except KeyError:
            pass
        if len(self._cache) == self._CACHE_SIZE:
            self._cache.popitem(last=False)
        self._cache[url] = (resource, datetime.utcnow() + self._CACHE_TTL)

class Files:
    """Simple file storage.

    Note that any method may raise an :exc:`OSError` if there is an IO related problem.

    .. attribute:: path

       Directory where files are stored. Must be read and writable by the current process.
    """

    def __init__(self, path: str) -> None:
        self.path = path

    async def read(self, url: str) -> Tuple[bytes, str]:
        """Read the file at the given file *url* and return the data and media type.

        If there is no file at *url*, a :exc:`LookupError` is raised.
        """
        components = urlsplit(url)
        if components.scheme and components.scheme != 'file':
            raise ValueError(f'Bad url scheme {url}')
        name = components.path.lstrip('/')
        content_type, _ = guess_type(name)
        if '/' in name or not content_type:
            raise LookupError(url)
        try:
            data = await self._load(str(Path(self.path, name)))
        except FileNotFoundError as e:
            raise LookupError(url) from e
        return data, content_type

    async def write(self, data: bytes, content_type: str) -> str:
        """Write *data* to a file and return its file URL.

        *content_type* is the media type, recognized by :mod:`mimetypes`.
        """
        digest = sha256(data).hexdigest()
        ext = guess_extension(content_type)
        if not ext:
            raise ValueError(f'Unknown content_type {content_type}')
        name = f'{digest}{ext}'
        await self._dump(str(Path(self.path, name)), data)
        return f'file:/{name}'

    async def garbage_collect(self, references: Iterable[str] = ()) -> int:
        """Delete files without entry in *references*.

        If *references* is empty (the default), all files are removed. The number of deleted files
        is returned.
        """
        # We could raise an error for dangling references (the implementation does not care),
        # because they indicate a bug on the caller's side
        files = set(await get_event_loop().run_in_executor(None, partial(listdir, self.path)))
        references = {urlsplit(url).path.lstrip('/') for url in references}
        garbage = {str(Path(self.path, name)) for name in files - references}
        await self._unlink(garbage)
        return len(garbage)

    @staticmethod
    async def _load(path: str) -> bytes:
        def _f() -> bytes:
            with open(path, 'rb') as f:
                return f.read()
        return await get_event_loop().run_in_executor(None, _f)

    @staticmethod
    async def _dump(path: str, data: bytes) -> None:
        def _f() -> None:
            with open(path, 'wb') as f:
                f.write(data)
        return await get_event_loop().run_in_executor(None, _f)

    @staticmethod
    async def _unlink(paths: Iterable[str]) -> None:
        def _f() -> None:
            for path in paths:
                Path(path).unlink()
        return await get_event_loop().run_in_executor(None, _f)

def handle_image(url: str, content_type: str, data: bytes, analyzer: Analyzer) -> Optional[Image]:
    """Process an image resource."""
    # pylint: disable=unused-argument; part of API
    # https://en.wikipedia.org/wiki/Comparison_of_web_browsers#Image_format_support
    if content_type in {'image/bmp', 'image/gif', 'image/jpeg', 'image/png', 'image/svg+xml'}:
        return Image(url, content_type)
    return None

async def handle_webpage(url: str, content_type: str, data: bytes,
                         analyzer: Analyzer) -> Optional[Resource]:
    """Process a webpage resource."""
    if content_type not in {'text/html', 'application/xhtml+xml'}:
        return None

    try:
        html = data.decode()
    except UnicodeDecodeError as e:
        raise BrokenResourceError('Bad data encoding analyzing {}'.format(url)) from e
    parser = _MetaParser()
    parser.feed(html)
    parser.close()

    description = str_or_none(parser.meta.get('og:title') or parser.meta.get('title') or '')
    image = None
    image_url = (parser.meta.get('og:image') or parser.meta.get('og:image:url') or
                 parser.meta.get('og:image:secure_url'))
    if image_url:
        image_url = urljoin(url, image_url)
        try:
            resource = await analyzer.analyze(image_url)
        except error.ValueError as e:
            broken_resource_e = BrokenResourceError(
                f'Bad data image URL scheme {image_url!r} analyzing {url}')
            raise broken_resource_e from e
        if not isinstance(resource, Image):
            raise BrokenResourceError(
                'Bad image type {!r} analyzing {}'.format(type(resource).__name__, url))
        image = resource

    return Resource(url, content_type, description=description, image=image)

def handle_youtube(key: str) -> HandleResourceFunc:
    """Return a function which processes a YouTube video.

    *key* is a YouTube API key. Can be retrieved from
    https://console.developers.google.com/apis/credentials.
    """
    youtube = WebAPI('https://www.googleapis.com/youtube/v3/', query={'key': key})

    async def _f(url: str, content_type: str, data: bytes,
                 analyzer: Analyzer) -> Optional[Resource]:
        # pylint: disable=unused-argument; part of API
        if not url.startswith('https://www.youtube.com/watch'):
            return None

        video_id = dict(parse_qsl(urlsplit(url).query)).get('v', '')
        result = await youtube.call('GET', 'videos', query={'id': video_id, 'part': 'snippet'})
        try:
            items = expect_type(list)(result['items'])
            if not items:
                return None
            description = expect_type(str)(items[0]['snippet']['title']) # type: ignore
            image_url = expect_type(str)(
                items[0]['snippet']['thumbnails']['high']['url']) # type: ignore
            image = expect_type(Image)(await analyzer.analyze(image_url))
        except (TypeError, LookupError, AnalysisError) as e:
            raise CommunicationError(f'Bad result for GET {youtube.url}videos?id={video_id}') from e
        return Video(url, content_type, description=description, image=image)
    return _f

class AnalysisError(Error):
    """See :ref:`AnalysisError`."""

class NoResourceError(AnalysisError):
    """See :ref:`NoResourceError`."""

class ForbiddenResourceError(AnalysisError):
    """See :ref:`ForbiddenResourceError`."""

class BrokenResourceError(AnalysisError):
    """See :ref:`BrokenResourceError`."""

class _LoopError(Exception):
    pass

class _MetaParser(HTMLParser):
    # pylint: disable=abstract-method; https://bugs.python.org/issue31844

    def __init__(self) -> None:
        super().__init__()
        self.meta = {} # type: Dict[str, str]
        self._read_tag_data = None # type: Optional[str]

    def handle_starttag(self, tag: str, attrs: List[Tuple[str, Optional[str]]]) -> None:
        if not self._read_tag_data:
            if tag == 'title':
                self.meta['title'] = ''
                self._read_tag_data = 'title'
            elif tag == 'meta':
                # Consider standard HTML (name) and Open Graph / RDFa (property) tags
                key = next((v for k, v in attrs if k in {'name', 'property'}), None)
                value = next((v for k, v in attrs if k == 'content'), None)
                if key is not None and value is not None:
                    self.meta[key] = value

    def handle_endtag(self, tag: str) -> None:
        if self._read_tag_data == tag:
            self._read_tag_data = None

    def handle_data(self, data: str) -> None:
        if self._read_tag_data:
            self.meta[self._read_tag_data] += data
