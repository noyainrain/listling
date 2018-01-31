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

from tornado.testing import AsyncTestCase

from listling import Listling

class ListlingTestCase(AsyncTestCase):
    def setUp(self):
        super().setUp()
        self.app = Listling(redis_url='15')
        self.app.r.flushdb()
        self.app.update()
        self.user = self.app.login()

class ListlingTest(ListlingTestCase):
    def test_lists_create(self):
        lst = self.app.lists.create('Cat colony tasks')
        self.assertIn(lst.id, self.app.lists)

    def test_lists_create_example(self):
        lst = self.app.lists.create_example('shopping')
        self.assertEqual(lst.title, 'Kitchen shopping list')
        self.assertTrue(lst.items)
        self.assertIn(lst.id, self.app.lists)

class ListlingUpdateTest(AsyncTestCase):
    def test_update_db_fresh(self):
        app = Listling(redis_url='15')
        app.r.flushdb()
        app.update()
        self.assertEqual(app.settings.title, 'My Open Listling')

class ListTest(ListlingTestCase):
    def test_edit(self):
        lst = self.app.lists.create('Cat colony tasks')
        lst.edit(description='What has to be done!')
        self.assertEqual(lst.description, 'What has to be done!')

    def test_items_create(self):
        lst = self.app.lists.create('Cat colony tasks')
        item = lst.items.create('Sleep')
        self.assertIn(item.id, lst.items)

class ItemTest(ListlingTestCase):
    def test_edit(self):
        item = self.app.lists.create('Cat colony tasks').items.create('Sleep')
        item.edit(text='Very important!')
        self.assertEqual(item.text, 'Very important!')
