# micro
# Copyright (C) 2018 micro contributors
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

from collections import OrderedDict
from datetime import datetime, timedelta
from html.parser import HTMLParser
from inspect import isawaitable
from typing import Awaitable, Callable, Dict, List, Optional, Tuple, Union, cast
from urllib.parse import parse_qsl, urljoin, urlsplit

from tornado.httpclient import HTTPClientError, HTTPResponse

from . import error
from .error import CommunicationError, Error
from .util import Expect, expect_type, str_or_none
from .webapi import WebAPI, fetch

HandleResourceFunc = Callable[[str, str, bytes, 'Analyzer'],
                              Union[Optional['Resource'], Awaitable[Optional['Resource']]]]

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

    def json(self, restricted: bool = False, include: bool = False) -> Dict[str, object]:
        """See :meth:`JSONifiable.json`."""
        # pylint: disable=unused-argument; part of API
        return {
            '__type__': type(self).__name__,
            'url': self.url,
            'content_type': self.content_type,
            'description': self.description,
            'image': self.image.json() if self.image else None
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
    """

    _CACHE_SIZE = 128
    _CACHE_TTL = timedelta(hours=1)

    def __init__(
            self, *, handlers: List[HandleResourceFunc] = None,
            _cache: 'OrderedDict[str, Tuple[Resource, datetime]]' = None,
            _stack: List[str] = None) -> None:
        self.handlers = ([handle_image, handle_webpage] if handlers is None
                         else list(handlers)) # type: List[HandleResourceFunc]
        self._cache = OrderedDict() if _cache is None else _cache
        self._stack = [] if _stack is None else _stack

    async def analyze(self, url: str) -> Resource:
        """Analyze the web resource at *url* and return a description of it.

        *url* is an absolute HTTP(S) URL. If there is a problem fetching or analyzing the resource,
        a :exc:`CommunicationError` or :exc:`AnalysisError` is raised respectively.

        Results are cached for about one hour.
        """
        if len(self._stack) == 3:
            raise _LoopError()

        try:
            return self._get_cache(url)
        except KeyError:
            pass

        response = await self.fetch(url)
        content_type = response.headers['Content-Type'].split(';', 1)[0]

        resource = None
        analyzer = Analyzer(handlers=self.handlers, _cache=self._cache, _stack=self._stack + [url])
        for handle in self.handlers:
            try:
                result = handle(response.effective_url, content_type, response.body, analyzer)
                resource = (await cast(Awaitable[Optional[Resource]], result) if isawaitable(result)
                            else cast(Optional[Resource], result))
            except _LoopError:
                if self._stack:
                    raise
                raise BrokenResourceError('Loop analyzing {}'.format(url)) from None
            if resource:
                break
        if not resource:
            resource = Resource(response.effective_url, content_type)

        self._set_cache(url, resource)
        self._set_cache(resource.url, resource)
        return resource

    async def fetch(self, request: str) -> HTTPResponse:
        """Execute a *request*.

        Utility wrapper around :meth:`AsyncHTTPClient.fetch` with error handling suitable for
        :meth:`analyze`.
        """
        try:
            return await fetch(request)
        except ValueError:
            raise error.ValueError('Bad url scheme {!r}'.format(request))
        except HTTPClientError as e:
            if e.code in (404, 410):
                raise NoResourceError('No resource at {}'.format(request))
            if e.code in (401, 402, 403, 405, 451):
                raise ForbiddenResourceError('Forbidden resource at {}'.format(request))
            raise CommunicationError(
                'Unexpected response status {} for GET {}'.format(e.code, request))

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
    except UnicodeDecodeError:
        raise BrokenResourceError('Bad data encoding analyzing {}'.format(url))
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
        except error.ValueError:
            raise BrokenResourceError(
                'Bad data image URL scheme {!r} analyzing {}'.format(image_url, url))
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
        except (TypeError, LookupError, AnalysisError):
            raise CommunicationError(
                'Bad result for GET {}videos?id={}'.format(youtube.url, video_id))
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

    def handle_starttag(self, tag: str, attrs: List[Tuple[str, str]]) -> None:
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
