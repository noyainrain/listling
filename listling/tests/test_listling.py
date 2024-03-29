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

import asyncio
from asyncio import get_event_loop
from datetime import date, datetime, timezone
from pathlib import Path
from tempfile import mkdtemp
from typing import Tuple, cast
from urllib.parse import urlsplit

from micro import error
from micro.core import context
from tornado.testing import AsyncTestCase, gen_test

from listling import Item, Listling, User

class ListlingTestCase(AsyncTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.app = Listling(redis_url='15', files_path=mkdtemp())
        self.app.r.flushdb()
        get_event_loop().run_until_complete(self.app.update())
        self.user = cast(User, self.app.devices.sign_in().user)
        context.user.set(self.user)

class ListlingTest(ListlingTestCase):
    @gen_test
    async def test_file_references(self):
        # importlib.resources.files is only available in Python >= 3.9
        with (Path(__file__).parent / 'res/image.png').open('rb') as f:
            image_url = await self.app.files.write(f.read(), 'image/png')
        text_url = await self.app.files.write(b'Meow!', 'text/plain')
        lst = self.app.lists.create()
        await lst.items.create('Sleep', resource=image_url)
        await lst.items.create('Feast', resource=text_url)
        await lst.items.create('Cuddle')
        references = list(self.app.file_references())
        self.assertEqual(len(references), 3)
        self.assertEqual(references[0], image_url)
        self.assertEqual(urlsplit(references[1]).scheme, 'file')
        self.assertEqual(references[2], text_url)

    @gen_test
    async def test_lists_create_example(self):
        lst = await self.app.lists.create_example('shopping')
        self.assertEqual(lst.title, 'Kitchen shopping list')
        self.assertTrue(lst.items)
        self.assertIn(lst.id, self.app.lists)

class ListlingListsTest(ListlingTestCase):
    def test_create(self) -> None:
        lst = self.app.lists.create()
        self.assertEqual(lst.title, 'New list')
        self.assertEqual(list(lst.owners), [self.user])
        self.assertIn(lst.id, self.app.lists)
        self.assertIn(lst.id, self.user.lists)

class UserListsTest(ListlingTestCase):
    def test_add(self) -> None:
        shared_lst = self.app.lists.create()
        user = self.app.devices.sign_in().user
        context.user.set(user)
        lst = self.app.lists.create()
        user.lists.add(shared_lst)
        self.assertEqual(list(user.lists), [shared_lst, lst])

    def test_remove(self) -> None:
        shared_lst = self.app.lists.create()
        user = self.app.devices.sign_in().user
        context.user.set(user)
        lst = self.app.lists.create()
        user.lists.add(shared_lst)
        user.lists.remove(shared_lst)
        self.assertEqual(list(user.lists), [lst])

    def test_remove_as_list_owner(self):
        lst = self.app.lists.create()
        with self.assertRaisesRegex(ValueError, 'owner'):
            self.user.lists.remove(lst)

class ListTest(ListlingTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.list = self.app.lists.create()

    @gen_test
    async def test_edit(self) -> None:
        await self.list.edit(description='What has to be done!', features=['time'],
                             assign_by_default=True, mode='view', item_template="Details:")
        self.assertEqual(self.list.description, 'What has to be done!')
        self.assertEqual(self.list.features, ['time'])
        self.assertTrue(self.list.assign_by_default)
        self.assertEqual(self.list.mode, 'view')
        self.assertEqual(self.list.item_template, 'Details:')
        self.assertEqual(self.list.value_summary, [])

    @gen_test
    async def test_edit_assign_value_features(self) -> None:
        grumpy = cast(User, self.app.devices.sign_in().user)
        await self.list.edit(features=['assign'])
        item = await self.list.items.create('Sleep', value=60)
        item.assignees.assign(self.user)
        item.assignees.assign(grumpy)
        item = await self.list.items.create('Feast', value=42.5)
        item.assignees.assign(self.user)
        item = await self.list.items.create('Cuddle')
        item.assignees.assign(self.user)
        await self.list.items.create('Stroll', value=20)
        item = await self.list.items.create('Play', value=10)
        item.assignees.assign(self.user)
        item.trash()

        await self.list.edit(features=['assign', 'value'])
        self.assertEqual(self.list.value_summary,
                         [('total', 122.5), (self.user, 72.5), (grumpy, 30)])

    @gen_test
    async def test_edit_value_features(self) -> None:
        await self.list.edit(features=['assign'])
        item = await self.list.items.create('Sleep', value=60)
        item.assignees.assign(self.user)

        await self.list.edit(value_unit='min', features=['value'])
        self.assertEqual(self.list.value_unit, 'min')
        self.assertEqual(self.list.value_summary, [('total', 60)])

    @gen_test
    async def test_edit_no_features(self) -> None:
        self.app.r.caching = False
        await self.list.edit()
        lst = self.app.lists[self.list.id]
        self.assertEqual(lst.features, [])

    @gen_test
    async def test_edit_as_user(self) -> None:
        lst = self.app.lists.create()
        context.user.set(self.app.devices.sign_in().user)
        await lst.edit(description='What has to be done!')
        self.assertEqual(lst.description, 'What has to be done!')

    @gen_test
    async def test_edit_view_mode_as_user(self) -> None:
        lst = self.app.lists.create()
        await lst.edit(mode='view')
        context.user.set(self.app.devices.sign_in().user)
        with self.assertRaises(error.PermissionError):
            await lst.edit(description='What has to be done!')

    @gen_test
    async def test_query_users_name(self) -> None:
        lst = self.app.lists.create()
        happy = self.app.devices.sign_in().user
        context.user.set(happy)
        await happy.edit(name='Happy')
        await lst.items.create('Sleep')
        grumpy = self.app.devices.sign_in().user
        context.user.set(grumpy)
        await grumpy.edit(name='Grumpy')
        await lst.items.create('Feast')
        users = lst.users('U')
        self.assertEqual([user.id for user in users], [grumpy.id, self.user.id])

class ListItemsTest(ListlingTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.list = self.app.lists.create()
        asyncio.run(self.list.edit(features=['assign', 'value']))
        asyncio.run(self.list.items.create('Sleep'))
        asyncio.run(self.list.items.create('Cuddle'))
        asyncio.run(self.list.items.create('Stroll'))

    @gen_test
    async def test_create(self) -> None:
        items = self.list.items[:]
        item = await self.list.items.create('Feast', value=42,
                                            time=datetime(2015, 8, 27, 0, 42, tzinfo=timezone.utc))
        self.assertEqual(item.title, 'Feast')
        self.assertEqual(item.value, 42)
        self.assertEqual(item.time, datetime(2015, 8, 27, 0, 42, tzinfo=timezone.utc))
        self.assertEqual(self.app.items[item.id], item)
        self.assertEqual(self.list.value_summary, [('total', 42)])
        self.assertFalse(item.assignees)
        self.assertEqual(self.list.items[:], [*items, item])
        await self.list.edit(order='title')
        self.assertEqual(self.list.items[:], [items[1], item, items[0], items[2]])

    @gen_test
    async def test_create_for_assign_by_default(self) -> None:
        await self.list.edit(assign_by_default=True)
        item = await self.list.items.create('Feast')
        self.assertEqual(item.assignees[:], [self.user])

    @gen_test
    async def test_move(self) -> None:
        items = self.list.items[:]
        await self.list.edit(order='title')
        self.list.items.move(items[1], items[2])
        self.assertEqual(self.list.items[:], [items[1], items[0], items[2]])
        await self.list.edit(order=None)
        self.assertEqual(self.list.items[:], [items[0], items[2], items[1]])

class ItemTest(ListlingTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.list = self.app.lists.create()
        asyncio.run(self.list.edit(features=['value']))
        asyncio.run(self.list.items.create('Sleep'))
        asyncio.run(self.list.items.create('Feast'))
        self.item = asyncio.run(self.list.items.create('Cuddle', value=5))

    async def make_item(self, *, use_case: str = 'simple', mode: str = None) -> Item:
        lst = self.app.lists.create(use_case)
        if mode:
            await lst.edit(mode=mode)
        return await lst.items.create('Sleep')

    @gen_test
    async def test_edit(self) -> None:
        items = self.list.items[:]
        await self.item.edit(title='Hug', text='Meow!', value=2, time=date(2015, 8, 27))
        self.assertEqual(self.item.title, 'Hug')
        self.assertEqual(self.item.text, 'Meow!')
        self.assertEqual(self.item.value, 2)
        self.assertEqual(self.item.time, date(2015, 8, 27))
        self.assertEqual(self.list.value_summary, [('total', 2)])
        self.assertEqual(self.list.items[:], items)
        await self.list.edit(order='title')
        self.assertEqual(self.list.items[:], [items[1], self.item, items[0]])

    @gen_test
    async def test_delete(self) -> None:
        self.app.r.caching = False
        items = self.list.items[:]
        await self.list.edit(features=['assign', 'vote'])
        self.item.assignees.assign(self.user)
        self.item.votes.vote()
        self.item.delete()
        with self.assertRaises(KeyError):
            # pylint: disable=pointless-statement; error raised on access
            self.app.items[self.item.id]
        self.assertFalse(self.item.assignees)
        self.assertFalse(self.item.votes)
        self.assertEqual(self.list.items[:], items[:2])
        await self.list.edit(order='title')
        self.assertEqual(self.list.items[:], [items[1], items[0]])

    def test_trash(self) -> None:
        self.item.trash()
        self.assertEqual(self.list.value_summary, [('total', 0)])

    def test_restore(self) -> None:
        self.item.trash()
        self.item.restore()
        self.assertEqual(self.list.value_summary, [('total', 5)])

    @gen_test
    async def test_check(self):
        item = await self.make_item(use_case='todo')
        item.check()
        self.assertTrue(item.checked)

    @gen_test
    async def test_check_feature_disabled(self):
        item = await self.make_item()
        with self.assertRaisesRegex(ValueError, 'feature_disabled'):
            item.check()
        self.assertFalse(item.checked)

    @gen_test
    async def test_check_as_user(self):
        item = await self.make_item(use_case='todo')
        context.user.set(self.app.devices.sign_in().user)
        item.check()
        self.assertTrue(item.checked)

    @gen_test
    async def test_check_view_mode_as_user(self):
        item = await self.make_item(use_case='todo', mode='view')
        context.user.set(self.app.devices.sign_in().user)
        with self.assertRaises(error.PermissionError):
            item.check()

    @gen_test
    async def test_uncheck(self):
        item = await self.make_item(use_case='todo')
        item.check()
        item.uncheck()
        self.assertFalse(item.checked)

class ItemAssigneesTest(ListlingTestCase):
    def setUp(self) -> None:
        super().setUp()
        lst = self.app.lists.create()
        asyncio.run(lst.edit(features=['assign', 'value']))
        self.item = asyncio.run(lst.items.create('Sleep', value=60))
        self.grumpy = cast(User, self.app.devices.sign_in().user)

    @gen_test
    async def test_assign(self) -> None:
        self.item.assignees.assign(self.user)
        self.item.assignees.assign(self.grumpy)
        self.assertEqual(list(self.item.assignees), [self.grumpy, self.user])
        self.assertEqual(self.item.list.value_summary,
                         [('total', 60), (self.grumpy, 30), (self.user, 30)])

    @gen_test
    async def test_unassign(self) -> None:
        self.item.assignees.assign(self.user)
        self.item.assignees.assign(self.grumpy)
        self.item.assignees.unassign(self.grumpy)
        self.assertEqual(list(self.item.assignees), [self.user])
        self.assertEqual(self.item.list.value_summary, [('total', 60), (self.user, 60)])

class ItemVotesTest(ListlingTestCase):
    async def make_item(self) -> Tuple[Item, User]:
        lst = self.app.lists.create('poll')
        item = await lst.items.create('Mouse')
        user = self.app.devices.sign_in().user
        token = context.user.set(user)
        item.votes.vote()
        context.user.reset(token)
        return item, user

    @gen_test
    async def test_vote(self) -> None:
        item, user = await self.make_item()
        item.votes.vote()
        item.votes.vote()
        self.assertEqual(list(item.votes), [self.user, user])
        self.assertTrue(item.votes.has_user_voted(self.user))

    @gen_test
    async def test_unvote(self) -> None:
        item, user = await self.make_item()
        item.votes.vote()
        item.votes.unvote()
        self.assertEqual(list(item.votes), [user])
        self.assertFalse(item.votes.has_user_voted(self.user))
