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

# type: ignore
# pylint: disable=missing-docstring; test module

import os
from tempfile import mkdtemp

from tornado.testing import AsyncTestCase, AsyncHTTPTestCase, gen_test
from tornado.web import Application, RequestHandler

from micro.resource import (Analyzer, BrokenResourceError, Files, ForbiddenResourceError, Image,
                            NoResourceError, Resource)
from micro.webapi import CommunicationError

class AnalyzerTestCase(AsyncHTTPTestCase):
    def get_app(self) -> Application:
        return Application([(r'/codes/([^/]+)$', CodeEndpoint)],
                           static_path=os.path.join(os.path.dirname(__file__), 'res'))

    @gen_test
    async def test_analyze_blob(self) -> None:
        analyzer = Analyzer()
        resource = await analyzer.analyze(self.get_url('/static/blob'))
        self.assertIsInstance(resource, Resource)
        self.assertRegex(resource.url, r'/static/blob$')
        self.assertEqual(resource.content_type, 'application/octet-stream')
        self.assertIsNone(resource.description)
        self.assertIsNone(resource.image)

    @gen_test
    async def test_analyze_image(self) -> None:
        analyzer = Analyzer()
        image = await analyzer.analyze(self.get_url('/static/image.svg'))
        self.assertIsInstance(image, Image)
        self.assertEqual(image.content_type, 'image/svg+xml')
        self.assertIsNone(image.description)
        self.assertIsNone(image.image)

    @gen_test
    async def test_analyze_webpage(self) -> None:
        analyzer = Analyzer()
        webpage = await analyzer.analyze(self.get_url('/static/webpage.html'))
        self.assertIsInstance(webpage, Resource)
        self.assertEqual(webpage.content_type, 'text/html')
        self.assertEqual(webpage.description, 'Happy Blog')
        assert isinstance(webpage.image, Image)
        self.assertRegex(webpage.image.url, '/static/image.svg$')

    @gen_test
    async def test_analyze_file(self) -> None:
        files = Files(mkdtemp())
        url = await files.write(b'Meow!', 'text/plain')
        analyzer = Analyzer(files=files)
        resource = await analyzer.analyze(url)
        self.assertEqual(resource.url, url)
        self.assertEqual(resource.content_type, 'text/plain')

    @gen_test
    async def test_analyze_no_resource(self) -> None:
        analyzer = Analyzer()
        with self.assertRaises(NoResourceError):
            await analyzer.analyze(self.get_url('/foo'))

    @gen_test
    async def test_analyze_forbidden_resource(self) -> None:
        analyzer = Analyzer()
        with self.assertRaises(ForbiddenResourceError):
            await analyzer.analyze(self.get_url('/codes/403'))

    @gen_test
    async def test_analyze_resource_loop(self) -> None:
        analyzer = Analyzer()
        with self.assertRaises(BrokenResourceError):
            await analyzer.analyze(self.get_url('/static/loop.html'))

    @gen_test
    async def test_analyze_error_response(self) -> None:
        analyzer = Analyzer()
        with self.assertRaises(CommunicationError):
            await analyzer.analyze(self.get_url('/codes/500'))

    @gen_test
    async def test_analyze_no_host(self) -> None:
        analyzer = Analyzer()
        with self.assertRaises(CommunicationError):
            await analyzer.analyze('https://[::]/')

class FilesTest(AsyncTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.files = Files(mkdtemp())

    @gen_test # type: ignore[misc]
    async def test_read(self) -> None:
        url = await self.files.write(b'Meow!', 'text/plain')
        data, content_type = await self.files.read(url)
        self.assertEqual(data, b'Meow!')
        self.assertEqual(content_type, 'text/plain')

    @gen_test # type: ignore[misc]
    async def test_read_no(self) -> None:
        with self.assertRaises(LookupError):
            await self.files.read('file:/foo.txt')

    @gen_test # type: ignore[misc]
    async def test_garbage_collect(self) -> None:
        urls = [await self.files.write(data, 'application/octet-stream')
                for data in (b'a', b'b', b'c', b'd')]
        n = await self.files.garbage_collect(urls[:2])
        self.assertEqual(n, 2)
        data, _ = await self.files.read(urls[0])
        self.assertEqual(data, b'a')
        data, _ = await self.files.read(urls[1])
        self.assertEqual(data, b'b')
        with self.assertRaises(LookupError):
            await self.files.read(urls[2])
        with self.assertRaises(LookupError):
            await self.files.read(urls[3])

class CodeEndpoint(RequestHandler):
    # pylint: disable=abstract-method; Tornado handlers define a semi-abstract data_received()

    def get(self, code: str) -> None:
        # pylint: disable=arguments-differ; Tornado handler arguments are defined by URLs
        self.set_status(int(code))
