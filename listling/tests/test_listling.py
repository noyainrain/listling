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

from tornado.testing import AsyncTestCase

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

    def test_lists_create_example(self):
        lst = self.app.lists.create_example('shopping')
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
        self.setup_db('0.2.1')
        app = Listling(redis_url='15')
        app.update()

        lst = next(iter(app.lists.values()))
        item = next(iter(lst.items.values()))
        self.assertFalse(lst.features)
        self.assertFalse(item.checked)

    def test_update_db_version_first(self):
        self.setup_db('0.2.1')
        app = Listling(redis_url='15')
        app.update()

        # Update to version 2
        lst = next(iter(app.lists.values()))
        item = next(iter(lst.items.values()))
        self.assertFalse(lst.features)
        self.assertFalse(item.checked)

class ListTest(ListlingTestCase):
    def test_edit(self):
        lst = self.app.lists.create(v=2)
        lst.edit(description='What has to be done!')
        self.assertEqual(lst.description, 'What has to be done!')

    def test_items_create(self):
        lst = self.app.lists.create(v=2)
        item = lst.items.create('Sleep')
        self.assertIn(item.id, lst.items)

class ItemTest(ListlingTestCase):
    def make_item(self, use_case='simple'):
        return self.app.lists.create(use_case, v=2).items.create('Sleep')

    def test_edit(self):
        item = self.make_item()
        item.edit(text='Very important!')
        self.assertEqual(item.text, 'Very important!')

    def test_check(self):
        item = self.make_item('todo')
        item.check()
        self.assertTrue(item.checked)

    def test_check_feature_disabled(self):
        item = self.make_item()
        with self.assertRaisesRegex(ValueError, 'feature_disabled'):
            item.check()
        self.assertFalse(item.checked)

    def test_uncheck(self):
        item = self.make_item('todo')
        item.check()
        item.uncheck()
        self.assertFalse(item.checked)
