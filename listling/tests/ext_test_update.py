# Open Listling
# Copyright (C) 2021 Open Listling contributors
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

from micro.core import context
from tornado.testing import AsyncTestCase, gen_test

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

    user = app.devices.sign_in().user
    context.user.set(user)
    lst = await app.lists.create_example('todo')
    # Compatibility with synchronous edit (deprecated since 0.34.0)
    await lst.edit(features=['check', 'assign', 'vote', 'value'], asynchronous=ON)
    item = lst.items[1]
    await item.edit(value=60)
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

    @gen_test
    async def test_update_db_fresh(self) -> None:
        app = Listling(redis_url='15', files_path=mkdtemp())
        app.r.flushdb()
        await app.update()
        self.assertEqual(app.settings.title, 'My Open Listling')

    @gen_test
    async def test_update_db_version_previous(self) -> None:
        self.setup_db('0.44.1')
        app = Listling(redis_url='15', files_path=mkdtemp())
        await app.update()

        # List.assign_by_default
        lst = app.lists[0]
        self.assertFalse(lst.assign_by_default)

    @gen_test
    async def test_update_db_version_first(self) -> None:
        self.setup_db('0.38.0')
        app = Listling(redis_url='15', files_path=mkdtemp())
        await app.update()

        # Items
        lst = app.lists[0]
        items = lst.items[:]
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
        # List.order
        context.user.set(user)
        app.user = user
        self.assertIsNone(lst.order)
        await lst.edit(order='title')
        self.assertEqual(lst.items[:], [items[1], items[0], items[2]])
        # List.value_summary_ids with user shares
        self.assertEqual(lst.value_summary, [('total', 60), (user, 60)])
        # List.assign_by_default
        self.assertFalse(lst.assign_by_default)
