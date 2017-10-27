# TODO

from tornado.testing import AsyncTestCase

from listling import Item, List, Listling

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
    def test_edit(self):
        item = self.app.lists.create('Colony tasks').items.create('Sleep')
        item.edit(description='FOOTODO')
        self.assertEqual(item.title, 'Sleep')
        self.assertEqual(item.description, 'FOOTODO')
