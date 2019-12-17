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

from unittest import TestCase

from micro.tests import RES_PATH
from micro.util import look_up_files, version

class LookUpFilesTest(TestCase):
    def test_call(self) -> None:
        files = look_up_files(['*.html', 'in', '!in/b.txt', '!in/out'], top=RES_PATH)
        result = [RES_PATH / 'loop.html', RES_PATH / 'webpage.html', RES_PATH / 'in/a.txt']
        self.assertEqual(files, result)

    def test_call_no_file(self) -> None:
        with self.assertRaisesRegex(ValueError, 'paths'):
            look_up_files(['foo'], top=RES_PATH)

class VersionTest(TestCase):
    @version(1)
    def echo(self, a):
        return (1, self, a)

    @echo.version(2)
    def echo(self, b, a):
        # pylint: disable=function-redefined; decorated
        return (2, self, b, a)

    def test_call(self):
        result = self.echo('a')
        self.assertEqual(result, (1, self, 'a'))

    def test_call_v_1(self):
        result = self.echo('a', v=1)
        self.assertEqual(result, (1, self, 'a'))

    def test_call_v_2(self):
        result = self.echo('b', 'a', v=2)
        self.assertEqual(result, (2, self, 'b', 'a'))

    def test_call_v_unknown(self):
        with self.assertRaises(NotImplementedError):
            self.echo('a', v=3)
