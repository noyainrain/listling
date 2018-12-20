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
    async def test_availibility(self):
        lst = self.app.lists.create_example('todo')
        item = next(iter(lst.items.values()))
        await self.request('/api/lists', method='POST', body='{"v": 2}')
        await self.request('/api/lists/create-example', method='POST',
                           body='{"use_case": "shopping"}')
        await self.request('/api/lists/shorts', method='POST',
                           body='{{"list_id": "{}"}}'.format(lst.id))
        await self.request('/api/lists/{}'.format(lst.id))
        await self.request('/api/lists/{}'.format(lst.id), method='POST',
                           body='{"description": "What has to be done!"}')
        await self.request('/api/lists/{}/items'.format(lst.id))
        await self.request('/api/lists/{}/items'.format(lst.id), method='POST',
                           body='{"title": "Sleep"}')
        await self.request('/api/lists/{}/items/{}'.format(lst.id, item.id))
        await self.request('/api/lists/{}/items/{}'.format(lst.id, item.id), method='POST',
                           body='{"text": "Very important!"}')
        await self.request('/api/lists/{}/items/{}/check'.format(lst.id, item.id), method='POST',
                           body='')
        await self.request('/api/lists/{}/items/{}/uncheck'.format(lst.id, item.id), method='POST',
                           body='')
