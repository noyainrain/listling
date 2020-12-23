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

from configparser import ConfigParser

from tornado.testing import AsyncTestCase, gen_test

from micro.resource import Analyzer, Video, handle_image, handle_youtube

class AnalyzeServiceTest(AsyncTestCase):
    @gen_test(timeout=20)
    async def test_analyze_youtube(self) -> None:
        config = ConfigParser()
        config.read('test.cfg')
        if 'resource' not in config:
            self.skipTest('No resource test configuration')
        values = iter(config['resource']['video_service_keys'].split())
        video_service_keys = dict(zip(values, values))

        analyzer = Analyzer(handlers=[handle_youtube(video_service_keys['youtube']), handle_image])
        video = await analyzer.analyze('https://www.youtube.com/watch?v=QH2-TGUlwu4')
        self.assertIsInstance(video, Video)
        self.assertEqual(video.content_type, 'text/html')
        self.assertTrue(video.description)
        self.assertTrue(video.image)
