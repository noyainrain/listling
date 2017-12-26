# TODO

from micro.test import ServerTestCase
from tornado.testing import gen_test

from listling.server import make_server

class ServerTest(ServerTestCase):
    def setUp(self):
        super().setUp()
        self.server = make_server(port=16160, redis_url='15')
        self.app = self.server.app
        self.app.r.flushdb()
        self.server.start()
        self.client_user = self.app.login()

    @gen_test
    def test_availibility(self):
        lst = self.app.lists.create('Colony tasks', features={'check': 'user'})
        item = lst.items.create('Sleep')

        yield self.request('/api/lists', method='POST', body='{"title": "Colony tasks"}')
        yield self.request('/api/lists/create-example', method='POST', body='{"kind": "simple"}')
        yield self.request('/api/lists/{}'.format(lst.id))
        yield self.request('/api/lists/{}'.format(lst.id), method='POST',
                           body='{"description": "What has to be done!"}')
        yield self.request('/api/lists/{}/items'.format(lst.id))
        yield self.request('/api/lists/{}/items'.format(lst.id), method='POST',
                           body='{"title": "Sleep"}')
        yield self.request('/api/lists/{}/items/{}'.format(lst.id, item.id))
        yield self.request('/api/lists/{}/items/{}'.format(lst.id, item.id), method='POST',
                           body='{"description": "FOOTODO"}')
        yield self.request('/api/lists/{}/items/{}/check'.format(lst.id, item.id), method='POST',
                           body='')
        yield self.request('/api/lists/{}/items/{}/uncheck'.format(lst.id, item.id), method='POST',
                           body='')
