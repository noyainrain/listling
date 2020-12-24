# Open Listling
# Copyright (C) 2020 Open Listling contributors
#
# This program is free software: you can redistribute it and/or modify it under the terms of the GNU
# Affero General Public License as published by the Free Software Foundation, either version 3 of
# the License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without
# even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU
# Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License along with this program.
# If not, see <https://www.gnu.org/licenses/>.

# pylint: disable=missing-docstring; test module

from pathlib import Path
from subprocess import run
import sys
from tempfile import gettempdir, mkdtemp

from tornado.testing import AsyncTestCase

from listling import Listling

SETUP_DB_SCRIPT = """\
from asyncio import get_event_loop
from micro.core import context
from listling import Listling

async def main():
    app = Listling(redis_url='15')
    app.r.flushdb()
    app.update()

    context.user.set(app.login())
    await app.lists.create_example('todo')

get_event_loop().run_until_complete(main())
"""

class UpdateTest(AsyncTestCase):
    @staticmethod
    def setup_db(tag: str) -> None:
        d = Path(gettempdir(), f'listling_{tag}')
        if not d.exists():
            run(
                ['git', 'clone', '-c', 'advice.detachedHead=false', '-q', '--single-branch',
                 '--branch', tag, '.', str(d)],
                check=True)
            # venv and virtualenv 16, which might be active, are incompatible
            python = Path(getattr(sys, 'real_prefix', sys.base_prefix), 'bin/python3')
            run([str(python), '-m', 'venv', '.venv'], cwd=d, check=True)
            run(['.venv/bin/pip3', 'install', '-q', '-r', 'requirements.txt'], cwd=d, check=True)
        run(['.venv/bin/python3', '-c', SETUP_DB_SCRIPT], cwd=d, check=True)

    def test_update_db_fresh(self) -> None:
        app = Listling(redis_url='15', files_path=mkdtemp())
        app.r.flushdb()
        app.update()
        self.assertEqual(app.settings.title, 'My Open Listling')

    def test_update_db_version_previous(self) -> None:
        self.setup_db('0.38.0')
        app = Listling(redis_url='15', files_path=mkdtemp())
        app.update()

        self.assertEqual({id.decode() for id in app.r.smembers('items')},
                         {item.id for item in app.lists[0].items[:]})

    def test_update_db_version_first(self) -> None:
        self.setup_db('0.32.1')
        app = Listling(redis_url='15', files_path=mkdtemp())
        app.update()

        # Item.value
        lst = app.lists[0]
        self.assertIsNone(lst.items[0].value)
        # List.value_unit
        self.assertIsNone(lst.value_unit)
        # List.owners
        self.assertEqual(list(lst.owners), [lst.authors[0]])
        # Items
        self.assertEqual({id.decode() for id in app.r.smembers('items')},
                         {item.id for item in lst.items[:]})
