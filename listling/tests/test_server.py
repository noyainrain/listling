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

import json
from tempfile import mkdtemp

from micro.test import ServerTestCase
from tornado.testing import gen_test

from listling.server import make_server

class ServerTest(ServerTestCase):
    def setUp(self):
        super().setUp()
        self.server = make_server(port=16160, redis_url='15', files_path=mkdtemp())
        self.app = self.server.app
        self.app.r.flushdb()
        self.server.start()
        self.client_user = self.app.login()

    @gen_test
    async def test_availability(self) -> None:
        lst = await self.app.lists.create_example('todo')
        await lst.edit(features=['check', 'assign', 'vote'])
        item = lst.items[0]
        self.app.login()
        shared_lst = self.app.lists.create(v=2)

        # API
        await self.request('/api/users/{}/lists'.format(self.client_user.id))
        await self.request('/api/users/{}/lists'.format(self.client_user.id), method='POST',
                           body=json.dumps({'list_id': shared_lst.id}))
        await self.request('/api/users/{}/lists/{}'.format(self.client_user.id, shared_lst.id),
                           method='DELETE')
        await self.request('/api/lists', method='POST', body='{"v": 2}')
        await self.request('/api/lists/create-example', method='POST',
                           body='{"use_case": "shopping"}')
        await self.request('/api/lists/{}'.format(lst.id))
        await self.request('/api/lists/{}'.format(lst.id), method='POST',
                           body='{"description": "What has to be done!"}')
        await self.request('/api/lists/{}/users'.format(lst.id))
        await self.request('/api/lists/{}/items'.format(lst.id))
        await self.request('/api/lists/{}/items'.format(lst.id), method='POST',
                           body='{"title": "Sleep", "value": 42}')
        await self.request(f'/api/lists/{lst.id}/activity')
        await self.request('/api/lists/{}/items/{}'.format(lst.id, item.id))
        await self.request(f'/api/lists/{lst.id}/items/{item.id}', method='POST',
                           body='{"text": "Very important!", "value": null}')
        await self.request('/api/lists/{}/items/{}/check'.format(lst.id, item.id), method='POST',
                           body='')
        await self.request('/api/lists/{}/items/{}/uncheck'.format(lst.id, item.id), method='POST',
                           body='')
        await self.request('/api/lists/{}/items/{}/assignees'.format(lst.id, item.id))
        await self.request('/api/lists/{}/items/{}/assignees'.format(lst.id, item.id),
                           method='POST', body=json.dumps({'assignee_id': self.client_user.id}))
        await self.request(
            '/api/lists/{}/items/{}/assignees/{}'.format(lst.id, item.id, self.client_user.id),
            method='DELETE')
        await self.request('/api/lists/{}/items/{}/votes'.format(lst.id, item.id))
        await self.request('/api/lists/{}/items/{}/votes'.format(lst.id, item.id), method='POST',
                           body='')
        await self.request('/api/lists/{}/items/{}/votes/user'.format(lst.id, item.id),
                           method='DELETE')

        # UI
        await self.request('/lists/{}'.format(lst.id))
