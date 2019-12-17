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

# pylint: disable=missing-docstring; test module

import os

from tornado.testing import AsyncHTTPTestCase, gen_test
from tornado.web import Application, RequestHandler

from micro.error import CommunicationError
from micro.resource import (Analyzer, BrokenResourceError, ForbiddenResourceError, Image,
                            NoResourceError, Resource)

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
            await analyzer.analyze('https://example.invalid/')

class CodeEndpoint(RequestHandler):
    # pylint: disable=abstract-method; Tornado handlers define a semi-abstract data_received()

    def get(self, code: str) -> None:
        # pylint: disable=arguments-differ; Tornado handler arguments are defined by URLs
        self.set_status(int(code))
