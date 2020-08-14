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
from subprocess import check_call
from tempfile import mkdtemp

import micro
from micro.core import context
from micro.util import ON
from tornado.testing import AsyncTestCase, gen_test

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

class ListlingTestCase(AsyncTestCase):
    def setUp(self):
        super().setUp()
        self.app = Listling(redis_url='15', files_path=mkdtemp())
        self.app.r.flushdb()
        self.app.update()
        self.user = self.app.login()
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
        lst = self.app.lists.create(v=2)
        self.assertEqual(lst.title, 'New list')
        self.assertTrue(self.app.lists[lst.id])
        self.assertIn(lst.id, self.user.lists)

    @gen_test
    async def test_lists_create_example(self):
        lst = await self.app.lists.create_example('shopping')
        self.assertEqual(lst.title, 'Kitchen shopping list')
        self.assertTrue(self.app.lists[lst.id])

class ListlingUpdateTest(AsyncTestCase):
    @staticmethod
    def setup_db(tag):
        d = mkdtemp()
        check_call(['git', '-c', 'advice.detachedHead=false', 'clone', '-q', '--single-branch',
                    '--branch', tag, '.', d])
        check_call(['python3', '-c', SETUP_DB_SCRIPT], cwd=d)

    def test_update_db_fresh(self):
        app = Listling(redis_url='15', files_path=mkdtemp())
        app.r.flushdb()
        app.update()
        self.assertEqual(app.settings.title, 'My Open Listling')

    def test_update_db_version_previous(self):
        self.setup_db('0.26.1')
        app = Listling(redis_url='15', files_path=mkdtemp())
        app.update()

        lists = app.r.omget([id.decode() for id in app.r.lrange('lists', 0, -1)])
        for l in lists:
            self.assertEqual(l.item_template, None)

    def test_update_db_version_first(self):
        self.setup_db('0.13.0')
        app = Listling(redis_url='15', files_path=mkdtemp())
        app.update()

        # Update to version 7
        user = app.settings.staff[0]
        lists = app.r.omget([id.decode() for id in app.r.lrange('lists', 0, -1)])
        self.assertEqual(set(user.lists.values()), set(lists[0:2]))
        # Update to version 8
        self.assertEqual([user.id for user in lists[1].users()],
                         [user.id for user in reversed(app.users[0:2])])
        # Update to version 9
        for l in lists:
            self.assertEqual(l.item_template, None)

class UserListsTest(ListlingTestCase):
    def test_add(self):
        shared_lst = self.app.lists.create(v=2)
        user = self.app.login()
        context.user.set(user)
        lst = self.app.lists.create(v=2)
        user.lists.add(shared_lst)
        self.assertEqual(list(user.lists.values()), [shared_lst, lst])

    def test_remove(self):
        shared_lst = self.app.lists.create(v=2)
        user = self.app.login()
        context.user.set(user)
        lst = self.app.lists.create(v=2)
        user.lists.add(shared_lst)
        user.lists.remove(shared_lst)
        self.assertEqual(list(user.lists.values()), [lst])

    def test_remove_as_list_owner(self):
        lst = self.app.lists.create(v=2)
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

        # TODO test that list is removed from owner
        #self.assertFalse(self.list.users()) - normally there is at least on user, the creator, but after
        # delete there isnt, so this will fail in unpack()
        # item_id = item.id
        # del item
        # gc.collect() # TODO see ItemTest.test_delete

    def test_edit(self):
        self.list = self.app.lists.create(v=2)
        self.list.edit(description='What has to be done!', mode='view', item_template="Details:")
        self.assertEqual(self.list.description, 'What has to be done!')
        self.assertEqual(self.list.mode, 'view')
        self.assertEqual(self.list.item_template, 'Details:')

    def test_edit_as_user(self):
        self.list = self.app.lists.create(v=2)
        self.app.login()
        self.list.edit(description='What has to be done!')
        self.assertEqual(self.list.description, 'What has to be done!')

    def test_edit_view_mode_as_user(self):
        self.list = self.app.lists.create(v=2)
        self.list.edit(mode='view')
        self.app.login()
        with self.assertRaises(micro.PermissionError):
            self.list.edit(description='What has to be done!')

    def test_trash(self):
        lists = [self.app.lists.create(), self.list]
        users = [self.user, self.app.login()]
        token = context.user.set(users[1])
        users[1].lists.add(lists[1])
        users[1].lists.add(lists[0])
        context.user.reset(token)

        lists[0].trash()
        self.assertEqual(list(users[0].lists.values()), lists)
        self.assertEqual(list(users[1].lists.values()), lists[1:])

    def test_restore(self):
        lists = [self.app.lists.create(), self.list]
        users = [self.user, self.app.login()]
        token = context.user.set(users[1])
        users[1].lists.add(lists[1])
        users[1].lists.add(lists[0])
        context.user.reset(token)
        lists[0].trash()

        lists[0].restore()
        self.assertEqual(list(users[0].lists.values()), lists)
        self.assertEqual(list(users[1].lists.values()), lists)

    @gen_test
    async def test_query_users_name(self):
        self.list = self.app.lists.create()
        happy = self.app.login()
        happy.edit(name='Happy')
        await self.list.items.create('Sleep')
        grumpy = self.app.login()
        grumpy.edit(name='Grumpy')
        await self.list.items.create('Feast')
        users = self.list.users('U')
        self.assertEqual([user.id for user in users], [grumpy.id, self.user.id])

    @gen_test
    async def test_items_create(self):
        self.list = self.app.lists.create(v=2)
        item = await self.list.items.create('Sleep')
        self.assertIn(item.id, self.list.items)

class ItemTest(ListlingTestCase):
    async def make_item(self, *, use_case='simple', mode=None):
        lst = self.app.lists.create(use_case, v=2)
        if mode:
            lst.edit(mode=mode)
        return await lst.items.create('Sleep')

    #@gen_test
    #async def setUp(self):
    #    super().setUp()
    #    self.list = self.app.lists.create('todo', v=2)
    #    self.item = await self.list.items.create('Sleep')

    @gen_test
    async def test_delete(self):
        lst = self.app.lists.create()
        lst.edit(features=['assign', 'vote'])
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
    async def test_edit(self):
        item = await self.make_item()
        await item.edit(text='Very important!', asynchronous=ON)
        self.assertEqual(item.text, 'Very important!')

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
        self.app.login()
        item.check()
        self.assertTrue(item.checked)

    @gen_test
    async def test_check_view_mode_as_user(self):
        item = await self.make_item(use_case='todo', mode='view')
        self.app.login()
        with self.assertRaises(micro.PermissionError):
            item.check()

    @gen_test
    async def test_uncheck(self):
        item = await self.make_item(use_case='todo')
        item.check()
        item.uncheck()
        self.assertFalse(item.checked)

class ItemAssigneesTest(ListlingTestCase):
    @gen_test
    async def test_assign(self):
        item = await self.app.lists.create('todo').items.create('Sleep')
        user = self.app.login()
        item.assignees.assign(self.user)
        item.assignees.assign(user)
        self.assertEqual(list(item.assignees.values()), [user, self.user])

    @gen_test
    async def test_unassign(self):
        item = await self.app.lists.create('todo').items.create('Sleep')
        user = self.app.login()
        item.assignees.assign(self.user)
        item.assignees.assign(user)
        item.assignees.unassign(user)
        self.assertEqual(list(item.assignees.values()), [self.user])

class ItemVotesTest(ListlingTestCase):
    async def make_item(self):
        lst = self.app.lists.create('poll', v=2)
        item = await lst.items.create('Mouse')
        user = self.app.login()
        token = context.user.set(user)
        item.votes.vote()
        context.user.reset(token)
        return item, user

    @gen_test
    async def test_vote(self):
        item, user = await self.make_item()
        item.votes.vote()
        item.votes.vote()
        self.assertEqual(list(item.votes.values()), [self.user, user])
        self.assertTrue(item.votes.has_user_voted(self.user))

    @gen_test
    async def test_unvote(self):
        item, user = await self.make_item()
        item.votes.vote()
        item.votes.unvote()
        self.assertEqual(list(item.votes.values()), [user])
        self.assertFalse(item.votes.has_user_voted(self.user))
