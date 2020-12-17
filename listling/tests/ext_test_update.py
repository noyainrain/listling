# Open Listling
# Copyright (C) 2019 Open Listling contributors
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
from listling import Listling

async def main():
    app = Listling(redis_url='15')
    app.r.flushdb()
    app.update()

    app.login()
    # Compatibility with synchronous execution (deprecated since 0.22.0)
    try:
        await app.lists.create_example('todo')
    except TypeError:
        pass
    lst = app.lists.create(v=2)
    app.login()
    app.lists.create(v=2)
    # Compatibility with synchronous execution (deprecated since 0.22.0)
    try:
        await lst.items.create('Sleep')
    except TypeError:
        pass
    app.login()

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
        self.setup_db('0.35.3')
        app = Listling(redis_url='15', files_path=mkdtemp())
        app.update()

        lst = app.lists[0]
        self.assertFalse(lst.trashed)

    def test_update_db_version_first(self) -> None:
        self.setup_db('0.13.0')
        app = Listling(redis_url='15', files_path=mkdtemp())
        app.update()

        # Update to version 7
        user = app.settings.staff[0]
        self.assertEqual(set(user.lists), set(app.lists[0:2]))
        # Update to version 8
        users = sorted(app.users, key=lambda user: user.create_time)
        self.assertEqual([user.id for user in app.lists[1].users()],
                         [user.id for user in reversed(users[0:2])])
        # Update to version 9
        for l in app.lists[:]:
            self.assertEqual(l.item_template, None)
        # Item.value
        lst = app.lists[0]
        self.assertIsNone(lst.items[0].value)
        # List.value_unit
        self.assertIsNone(lst.value_unit)
        # List.owners
        self.assertEqual(list(lst.owners), [lst.authors[0]])
        # List.trashed
        self.assertFalse(lst.trashed)
