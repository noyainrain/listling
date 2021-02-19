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
from micro.util import ON
from listling import Listling

async def main():
    app = Listling(redis_url='15')
    app.r.flushdb()
    app.update()

    user = app.login()
    context.user.set(user)
    lst = await app.lists.create_example('todo')
    # Compatibility with synchronous edit (deprecated since 0.34.0)
    await lst.edit(features=['check', 'assign', 'vote'], asynchronous=ON)
    item = lst.items[1]
    # Compatibility for user argument (deprecated since 0.39.1)
    try:
        item.votes.vote()
    except TypeError:
        item.votes.vote(user=user)
    item = await lst.items.create('Sleep')
    # Compatibility for user argument (deprecated since 0.39.1)
    try:
        item.assignees.assign(user)
    except TypeError:
        item.assignees.assign(user, user=user)
    # Compatibility for user argument (deprecated since 0.39.1)
    try:
        item.votes.vote()
    except TypeError:
        item.votes.vote(user=user)
    item.trash()
    item.delete()

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
            # Work around missing pywebpush dependency (see
            # https://github.com/web-push-libs/pywebpush/pull/132)
            run(['.venv/bin/pip3', 'install', '-q', 'six~=1.15'], cwd=d, check=True)
        run(['.venv/bin/python3', '-c', SETUP_DB_SCRIPT], cwd=d, check=True)

    def test_update_db_fresh(self) -> None:
        app = Listling(redis_url='15', files_path=mkdtemp())
        app.r.flushdb()
        app.update()
        self.assertEqual(app.settings.title, 'My Open Listling')

    def test_update_db_version_previous(self) -> None:
        self.setup_db('0.39.1')
        app = Listling(redis_url='15', files_path=mkdtemp())
        app.update()

        # Item.time
        self.assertIsNone(app.lists[0].items[0].time)

    def test_update_db_version_first(self) -> None:
        self.setup_db('0.32.1')
        app = Listling(redis_url='15', files_path=mkdtemp())
        app.update()

        # Item.value
        lst = app.lists[0]
        items = lst.items[:]
        self.assertIsNone(items[0].value)
        # List.value_unit
        self.assertIsNone(lst.value_unit)
        # List.owners
        self.assertEqual(list(lst.owners), [lst.authors[0]])
        # Items
        self.assertEqual({id.decode() for id in app.r.smembers('items')},
                         {item.id for item in items})
        # Item deletion
        user = next(iter(app.users))
        self.assertEqual(items[1].assignees[:], [user])
        self.assertEqual(items[1].votes[:], [user])
        self.assertEqual({key.decode().split('.')[0] for key in app.r.keys('Item:*')},
                         {item.id for item in items})
        # Item.time
        self.assertIsNone(items[0].time)
