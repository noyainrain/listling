# Open Listling
# Copyright (C) 2021 Open Listling contributors
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

from asyncio import get_event_loop
import json
from tempfile import mkdtemp
from typing import cast

from micro.core import context
from micro.test import ServerTestCase
from tornado.testing import gen_test

from listling import Listling
from listling.server import make_server

class ServerTest(ServerTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.server = make_server(port=16160, redis_url='15', files_path=mkdtemp())
        self.app = cast(Listling, self.server.app)
        self.app.r.flushdb()
        get_event_loop().run_until_complete(self.server.start())
        self.client_device = self.app.devices.sign_in()
        self.user = self.client_device.user
        context.user.set(self.user)

    @gen_test
    async def test_availability(self) -> None:
        lst = await self.app.lists.create_example('todo')
        await lst.edit(features=['check', 'assign', 'vote'])
        item = lst.items[0]
        user = self.app.devices.sign_in().user
        context.user.set(user)
        shared_lst = self.app.lists.create()

        # API
        await self.request(f'/api/users/{self.user.id}/lists')
        await self.request(f'/api/users/{self.user.id}/lists', method='POST',
                           body=json.dumps({'list_id': shared_lst.id}))
        await self.request(f'/api/users/{self.user.id}/lists/{shared_lst.id}', method='DELETE')
        await self.request('/api/lists', method='POST', body='')
        await self.request('/api/lists/create-example', method='POST',
                           body='{"use_case": "shopping"}')
        await self.request('/api/lists/{}'.format(lst.id))
        await self.request(
            f'/api/lists/{lst.id}', method='POST',
            body=json.dumps({
                'description': 'What has to be done!',
                'order': 'title',
                'assign_by_default': True,
                'value_unit': 'min'
            }))
        await self.request(f'/api/lists/{lst.id}/owners', method='POST',
                           body=json.dumps({'user_id': user.id}))
        await self.request(f'/api/lists/{lst.id}/owners/{user.id}', method='DELETE')
        await self.request('/api/lists/{}/users'.format(lst.id))
        await self.request('/api/lists/{}/items'.format(lst.id))
        await self.request(
            f'/api/lists/{lst.id}/items', method='POST',
            body=json.dumps({'title': 'Sleep', 'value': 42, 'time': '2015-08-27T00:42:00.000Z'}))
        await self.request(f'/api/lists/{lst.id}/activity')
        await self.request(f'/api/items/{item.id}')
        await self.request(
            f'/api/items/{item.id}', method='POST',
            body=json.dumps({'text': 'Very important!', 'value': None, 'time': '2015-08-27'}))
        await self.request(f'/api/items/{item.id}/check', method='POST', body='')
        await self.request(f'/api/items/{item.id}/uncheck', method='POST', body='')
        await self.request(f'/api/items/{item.id}/assignees')
        await self.request(f'/api/items/{item.id}/assignees', method='POST',
                           body=json.dumps({'assignee_id': self.user.id}))
        await self.request(f'/api/items/{item.id}/assignees/{self.user.id}', method='DELETE')
        await self.request(f'/api/items/{item.id}/votes')
        await self.request(f'/api/items/{item.id}/votes', method='POST', body='')
        await self.request(f'/api/items/{item.id}/votes/user', method='DELETE')

        # UI
        response = await self.request('/s', method='POST', body=f'/lists/{lst.id}')
        short_url = response.headers['Location']
        await self.request(short_url)
        await self.request(f'/lists/{lst.id}')
