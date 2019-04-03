# Open Listling
# Copyright (C) 2018 Open Listling contributors
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

from subprocess import check_call
from tempfile import mkdtemp

from micro.util import ON
from tornado.testing import AsyncTestCase, gen_test

from listling import Listling

SETUP_DB_SCRIPT = """\
from listling import Listling
app = Listling(redis_url='15')
app.r.flushdb()
app.update()
app.login()
# Compatibility for missing todo use case (deprecated since 0.3.0)
app.lists.create_example('shopping')
"""

class ListlingTestCase(AsyncTestCase):
    def setUp(self):
        super().setUp()
        self.app = Listling(redis_url='15')
        self.app.r.flushdb()
        self.app.update()
        self.user = self.app.login()

class ListlingTest(ListlingTestCase):
    def test_lists_create(self):
        lst = self.app.lists.create(v=2)
        self.assertEqual(lst.title, 'New list')
        self.assertIn(lst.id, self.app.lists)

    @gen_test
    async def test_lists_create_example(self):
        lst = await self.app.lists.create_example('shopping', asynchronous=ON)
        self.assertEqual(lst.title, 'Kitchen shopping list')
        self.assertTrue(lst.items)
        self.assertIn(lst.id, self.app.lists)

class ListlingUpdateTest(AsyncTestCase):
    @staticmethod
    def setup_db(tag):
        d = mkdtemp()
        check_call(['git', '-c', 'advice.detachedHead=false', 'clone', '-q', '--single-branch',
                    '--branch', tag, '.', d])
        check_call(['python3', '-c', SETUP_DB_SCRIPT], cwd=d)

    def test_update_db_fresh(self):
        app = Listling(redis_url='15')
        app.r.flushdb()
        app.update()
        self.assertEqual(app.settings.title, 'My Open Listling')

    def test_update_db_version_previous(self):
        self.setup_db('0.6.0')
        app = Listling(redis_url='15')
        app.update()

        lst = app.lists[0]
        self.assertEqual(lst.mode, 'collaborate')

    def test_update_db_version_first(self):
        self.setup_db('0.2.1')
        app = Listling(redis_url='15')
        app.update()

        # Update to version 2
        lst = app.lists[0]
        item = lst.items[0]
        self.assertFalse(lst.features)
        self.assertFalse(item.checked)
        # Update to version 3
        self.assertIsNotNone(lst.activity)
        # Update to version 4
        self.assertIsNone(item.location)
        # Update to version 5
        self.assertIsNone(item.resource)
        # Update to version 6
        self.assertEqual(lst.mode, 'collaborate')

class ListTest(ListlingTestCase):
    def test_edit(self):
        lst = self.app.lists.create(v=2)
        lst.edit(description='What has to be done!', mode='view')
        self.assertEqual(lst.description, 'What has to be done!')
        self.assertEqual(lst.mode, 'view')

    def test_edit_as_user(self):
        lst = self.app.lists.create(v=2)
        self.app.login()
        lst.edit(description='What has to be done!')
        self.assertEqual(lst.description, 'What has to be done!')

    def test_edit_view_mode_as_user(self):
        lst = self.app.lists.create(v=2)
        lst.edit(mode='view')
        self.app.login()
        with self.assertRaises(PermissionError):
            lst.edit(description='What has to be done!')

    @gen_test
    async def test_items_create(self):
        lst = self.app.lists.create(v=2)
        item = await lst.items.create('Sleep', asynchronous=ON)
        self.assertIn(item.id, lst.items)

class ItemTest(ListlingTestCase):
    def make_item(self, *, use_case='simple', mode=None):
        lst = self.app.lists.create(use_case, v=2)
        if mode:
            lst.edit(mode=mode)
        return lst.items.create('Sleep')

    @gen_test
    async def test_edit(self):
        item = self.make_item()
        await item.edit(text='Very important!', asynchronous=ON)
        self.assertEqual(item.text, 'Very important!')

    def test_check(self):
        item = self.make_item(use_case='todo')
        item.check()
        self.assertTrue(item.checked)

    def test_check_feature_disabled(self):
        item = self.make_item()
        with self.assertRaisesRegex(ValueError, 'feature_disabled'):
            item.check()
        self.assertFalse(item.checked)

    def test_check_as_user(self):
        item = self.make_item(use_case='todo')
        self.app.login()
        item.check()
        self.assertTrue(item.checked)

    def test_check_view_mode_as_user(self):
        item = self.make_item(use_case='todo', mode='view')
        self.app.login()
        with self.assertRaises(PermissionError):
            item.check()

    def test_uncheck(self):
        item = self.make_item(use_case='todo')
        item.check()
        item.uncheck()
        self.assertFalse(item.checked)
