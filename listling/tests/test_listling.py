# TODO
from subprocess import check_call
from tempfile import mkdtemp

from tornado.testing import AsyncTestCase

from listling import Item, List, Listling

SETUP_DB_SCRIPT = """\
from listling import Listling
app = Listling(redis_url='15')
app.r.flushdb()
app.update()
app.login()
app.lists.create_example('simple')
"""

class ListlingTestCase(AsyncTestCase):
    def setUp(self):
        super().setUp()
        self.app = Listling(redis_url='15')
        self.app.r.flushdb()
        self.app.update()
        self.staff_member = self.app.login()
        self.user = self.app.login()

class ListlingTest(ListlingTestCase):
    def test_lists_create(self):
        lst = self.app.lists.create('Colony tasks')
        self.assertIn(lst.id, self.app.lists)

    def test_lists_create_example(self):
        lst = self.app.lists.create_example('simple')
        self.assertEqual(lst.title, 'Some list')
        self.assertTrue(lst.items)
        self.assertIn(lst.id, self.app.lists)

class ListlingUpdateTest(AsyncTestCase):
    # copypasta from micro
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

    #def test_update_db_version_previous(self):
    #    self.setup_db('simple-list')
    #    app = Listling(redis_url='15')
    #    app.update()

    #    lst = next(app.lists)
    #    item = next(lst.items)
    #    self.assertFalse(item.checked)

    def test_update_db_version_first(self):
        self.setup_db('simple-list')
        app = Listling(redis_url='15')
        app.update()

        # Update to version 1
        lst = list(app.lists.values())[0]
        item = list(lst.items.values())[0]
        self.assertFalse(lst.features)
        self.assertFalse(item.checked)
        self.assertEqual(item.lst, lst)

class ListTest(ListlingTestCase):
    def setUp(self):
        super().setUp()
        self.lst = self.app.lists.create('Colony tasks')

    def test_edit(self):
        self.lst.edit(description='What has to be done!')
        self.assertEqual(self.lst.title, 'Colony tasks')
        self.assertEqual(self.lst.description, 'What has to be done!')

    def test_items_create(self):
        item = self.lst.items.create('Sleep')
        self.assertIn(item.id, self.lst.items)

class ItemTest(ListlingTestCase):
    def make_item(self, features={}):
        return self.app.lists.create('Colony tasks', features=features).items.create('Sleep')

    def test_edit(self):
        item = self.make_item()
        item.edit(description='FOOTODO')
        self.assertEqual(item.title, 'Sleep')
        self.assertEqual(item.description, 'FOOTODO')

    def test_check(self):
        item = self.make_item(features={'check': 'user'})
        item.check()
        self.assertTrue(item.checked)

    def test_check_disabled(self):
        item = self.make_item()
        with self.assertRaisesRegex(ValueError, 'check_disabled'):
            item.check()
        self.assertFalse(item.checked)

    def test_uncheck(self):
        item = self.make_item(features={'check': 'user'})
        item.check()
        item.uncheck()
        self.assertFalse(item.checked)
