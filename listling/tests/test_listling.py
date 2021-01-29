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

import asyncio
from datetime import date, datetime, timezone
from tempfile import mkdtemp
from typing import Tuple

from micro import User, error
from micro.core import context
from micro.util import ON
from tornado.testing import AsyncTestCase, gen_test

from listling import Item, Listling

class ListlingTestCase(AsyncTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.app = Listling(redis_url='15', files_path=mkdtemp())
        self.app.r.flushdb()
        self.app.update()
        self.user = self.app.devices.sign_in().user
        context.user.set(self.user)

class ListlingTest(ListlingTestCase):
    @gen_test
    async def test_file_references(self):
        urls = [
            await self.app.files.write(b'<svg />', 'image/svg+xml'),
            await self.app.files.write(b'<svg  />', 'image/svg+xml')
        ]
        lst = self.app.lists.create()
        await lst.items.create('Sleep', resource=urls[0])
        await lst.items.create('Feast', resource=urls[1])
        await lst.items.create('Cuddle')
        references = list(self.app.file_references())
        self.assertEqual(references, urls)

    def test_lists_create(self) -> None:
        lst = self.app.lists.create()
        self.assertEqual(lst.title, 'New list')
        self.assertEqual(list(lst.owners), [self.user])
        self.assertIn(lst.id, self.app.lists)
        self.assertIn(lst.id, self.user.lists)

    @gen_test
    async def test_lists_create_example(self):
        lst = await self.app.lists.create_example('shopping')
        self.assertEqual(lst.title, 'Kitchen shopping list')
        self.assertTrue(lst.items)
        self.assertIn(lst.id, self.app.lists)

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
    @gen_test
    async def test_edit(self) -> None:
        lst = self.app.lists.create()
        await lst.edit(description='What has to be done!', value_unit='min',
                       features=['value', 'time'], mode='view', item_template="Details:")
        self.assertEqual(lst.description, 'What has to be done!')
        self.assertEqual(lst.value_unit, 'min')
        self.assertEqual(lst.features, ['value', 'time'])
        self.assertEqual(lst.mode, 'view')
        self.assertEqual(lst.item_template, 'Details:')

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
    @gen_test
    async def test_create(self) -> None:
        lst = self.app.lists.create()
        item = await lst.items.create('Sleep', value=42,
                                      time=datetime(2015, 8, 27, 0, 42, tzinfo=timezone.utc))
        self.assertEqual(item.value, 42)
        self.assertEqual(item.time, datetime(2015, 8, 27, 0, 42, tzinfo=timezone.utc))
        self.assertEqual(self.app.items[item.id], item)
        self.assertEqual(lst.items[:], [item])

class ItemTest(ListlingTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.list = self.app.lists.create()
        self.item = asyncio.run(self.list.items.create('Sleep'))

    async def make_item(self, *, use_case: str = 'simple', mode: str = None) -> Item:
        lst = self.app.lists.create(use_case)
        if mode:
            await lst.edit(mode=mode)
        return await lst.items.create('Sleep')

    @gen_test
    async def test_edit(self) -> None:
        item = await self.make_item()
        await item.edit(text='Very important!', value=42, time=date(2015, 8, 27), asynchronous=ON)
        self.assertEqual(item.text, 'Very important!')
        self.assertEqual(item.value, 42)
        self.assertEqual(item.time, date(2015, 8, 27))

    @gen_test
    async def test_delete(self) -> None:
        await self.list.edit(features=['assign', 'vote'])
        self.item.assignees.assign(self.user)
        self.item.votes.vote()
        self.item.delete()
        with self.assertRaises(KeyError):
            # pylint: disable=pointless-statement; error raised on access
            self.app.items[self.item.id]
        self.assertFalse(self.item.assignees)
        self.assertFalse(self.item.votes)
        self.assertFalse(self.list.items)

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
    @gen_test
    async def test_assign(self) -> None:
        item = await self.app.lists.create('todo').items.create('Sleep')
        user = self.app.devices.sign_in().user
        item.assignees.assign(self.user)
        item.assignees.assign(user)
        self.assertEqual(list(item.assignees), [user, self.user])

    @gen_test
    async def test_unassign(self) -> None:
        item = await self.app.lists.create('todo').items.create('Sleep')
        user = self.app.devices.sign_in().user
        item.assignees.assign(self.user)
        item.assignees.assign(user)
        item.assignees.unassign(user)
        self.assertEqual(list(item.assignees), [self.user])

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
