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

import gc
from tempfile import mkdtemp

from micro import error
from micro.core import context
from micro.util import ON
from tornado.testing import AsyncTestCase, gen_test

from listling import Item, Listling

class ListlingTestCase(AsyncTestCase):
    def setUp(self):
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
        references = set(self.app.file_references())
        self.assertEqual(references, set(urls))

class ListsTest(ListlingTestCase):
    def test_getitem_trashed_list(self):
        lst = self.app.lists.create()
        lst.trash()
        context.user.set(self.app.login())
        with self.assertRaises(KeyError):
            self.app.lists[lst.id]

    def test_getitem_trashed_list_as_owner(self):
        lst = self.app.lists.create()
        lst.trash()
        self.assertTrue(self.app.lists[lst.id])

    def test_lists_create(self):
        lst = self.app.lists.create()
        print('LIST', lst, lst.id)
        self.assertEqual(lst.title, 'New list')
        self.assertEqual(list(lst.owners), [self.user])
        # self.assertIn(lst.id, self.app.lists)
        self.assertTrue(self.app.lists[lst.id])
        self.assertIn(lst.id, self.user.lists)

    @gen_test
    async def test_lists_create_example(self):
        lst = await self.app.lists.create_example('shopping')
        self.assertEqual(lst.title, 'Kitchen shopping list')
        self.assertTrue(self.app.lists[lst.id])

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
    def setUp(self):
        super().setUp()
        self.list = self.app.lists.create()

    def make_lists(self):
        return lists, users

    @gen_test
    async def test_delete(self):
        # item = await self.list.items.create('Sleep')
        item = await self.list.items.create('Sleep')

        self.list.delete()
        with self.assertRaises(KeyError):
            self.app.items[item.id]
        self.assertFalse(self.list.items)
        self.assertFalse(self.list.activity)
        with self.assertRaises(KeyError):
            self.app.lists[self.list.id]

        # TODO grant ownership to second user and test that list is removed from that owner

        #self.assertFalse(self.list.users()) - normally there is at least on user, the creator, but after
        # delete there isnt, so this will fail in unpack()
        # item_id = item.id
        # del item
        # gc.collect() # TODO see ItemTest.test_delete

    @gen_test
    async def test_edit(self) -> None:
        lst = self.app.lists.create(v=2)
        await lst.edit(description='What has to be done!', value_unit='min', features=['value'],
                       mode='view', item_template="Details:")
        self.assertEqual(lst.description, 'What has to be done!')
        self.assertEqual(lst.value_unit, 'min')
        self.assertEqual(lst.features, ['value'])
        self.assertEqual(lst.mode, 'view')
        self.assertEqual(lst.item_template, 'Details:')

    @gen_test
    async def test_edit_as_user(self) -> None:
        lst = self.app.lists.create(v=2)
        context.user.set(self.app.devices.sign_in().user)
        await lst.edit(description='What has to be done!')
        self.assertEqual(lst.description, 'What has to be done!')

    @gen_test
    async def test_edit_view_mode_as_user(self) -> None:
        lst = self.app.lists.create(v=2)
        await lst.edit(mode='view')
        context.user.set(self.app.devices.sign_in().user)
        with self.assertRaises(error.PermissionError):
            await lst.edit(description='What has to be done!')

    def test_trash(self):
        lists = [self.app.lists.create(), self.list]
        users = [self.user, self.app.login()]
        token = context.user.set(users[1])
        users[1].lists.add(lists[1])
        users[1].lists.add(lists[0])
        context.user.reset(token)

        lists[0].trash()
        self.assertEqual(users[0].lists[:], lists)
        self.assertEqual(users[1].lists[:], lists[1:])

    def test_restore(self):
        lists = [self.app.lists.create(), self.list]
        users = [self.user, self.app.login()]
        token = context.user.set(users[1])
        users[1].lists.add(lists[1])
        users[1].lists.add(lists[0])
        context.user.reset(token)
        lists[0].trash()

        lists[0].restore()
        self.assertEqual(users[0].lists[:], lists)
        self.assertEqual(users[1].lists[:], lists)

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
        lst = self.app.lists.create(v=2)
        item = await lst.items.create('Sleep', value=42)
        self.assertIn(item.id, lst.items)
        self.assertEqual(item.value, 42)

class ItemTest(ListlingTestCase):
    async def make_item(self, *, use_case: str = 'simple', mode: str = None) -> Item:
        lst = self.app.lists.create(use_case, v=2)
        if mode:
            await lst.edit(mode=mode)
        return await lst.items.create('Sleep')

    #@gen_test
    #async def setUp(self):
    #    super().setUp()
    #    self.list = self.app.lists.create('todo', v=2)
    #    self.item = await self.list.items.create('Sleep')

    @gen_test
    async def test_delete(self):
        lst = self.app.lists.create()
        await lst.edit(features=['assign', 'vote'])
        item = await lst.items.create('Sleep')
        item.votes.vote()
        item.assignees.assign(context.user.get())

        item.delete()
        self.assertFalse(item.assignees)
        self.assertFalse(item.votes)
        item_id = item.id
        # del item.assignees
        # del item.votes
        del item
        gc.collect() # TODO why needed and collected on ref = 0?
        with self.assertRaises(KeyError):
            self.app.items[item_id]
        self.assertNotIn(item_id, lst.items)

    @gen_test
    async def test_edit(self) -> None:
        item = await self.make_item()
        await item.edit(text='Very important!', value=42, asynchronous=ON)
        self.assertEqual(item.text, 'Very important!')
        self.assertEqual(item.value, 42)

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
    async def make_item(self):
        lst = self.app.lists.create('poll', v=2)
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
