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

# pylint: disable=abstract-method; Tornado handlers define a semi-abstract data_received()
# pylint: disable=arguments-differ; Tornado handler arguments are defined by URLs

"""Open Listling server."""

import json

import micro
from micro import Location
from micro.server import (Endpoint, Server, make_activity_endpoint, make_orderable_endpoints,
                          make_trashable_endpoints, ActivityStreamEndpoint)
from micro.util import ON

from . import Listling

def make_server(*, port=8080, url=None, debug=False, redis_url='', smtp_url='',
                client_map_service_key=None):
    """Create an Open Listling server."""
    app = Listling(redis_url, smtp_url=smtp_url)
    handlers = [
        (r'/api/lists$', _ListsEndpoint),
        (r'/api/lists/create-example$', _ListsCreateExampleEndpoint),
        (r'/api/lists/([^/]+)$', _ListEndpoint),
        (r'/api/lists/([^/]+)/activity/stream$', ActivityStreamEndpoint,
         {'get_activity': lambda id, *a: app.lists[id].activity}),
        (r'/api/lists/([^/]+)/items$', _ListItemsEndpoint),
        *make_orderable_endpoints(r'/api/lists/([^/]+)/items', lambda id: app.lists[id].items),
        make_activity_endpoint(r'/api/lists/([^/]+)/activity',
                               lambda id, *a: app.lists[id].activity),
        (r'/api/lists/([^/]+)/items/([^/]+)$', _ItemEndpoint),
        *make_trashable_endpoints(r'/api/lists/([^/]+)/items/([^/]+)',
                                  lambda list_id, id: app.lists[list_id].items[id]),
        (r'/api/lists/([^/]+)/items/([^/]+)/check$', _ItemCheckEndpoint),
        (r'/api/lists/([^/]+)/items/([^/]+)/uncheck$', _ItemUncheckEndpoint)
    ]
    return Server(
        app, handlers, port=port, url=url, client_modules_path='node_modules',
        client_service_path='listling/service.js', debug=debug,
        client_map_service_key=client_map_service_key)

class _ListsEndpoint(Endpoint):
    def post(self):
        args = self.check_args({
            'use_case': (str, 'opt'),
            'title': (str, 'opt'),
            'description': (str, None, 'opt'),
            'v': (int, 'opt')
        })
        if args.get('v', 1) == 1 and 'title' not in args:
            raise micro.ValueError('title_missing')
        lst = self.app.lists.create(**args)
        self.write(lst.json(restricted=True, include=True))

class _ListsCreateExampleEndpoint(Endpoint):
    def post(self):
        args = self.check_args({'use_case': str})
        lst = self.app.lists.create_example(**args)
        self.write(lst.json(restricted=True, include=True))

class _ListEndpoint(Endpoint):
    def get(self, id):
        lst = self.app.lists[id]
        self.write(lst.json(restricted=True, include=True))

    def post(self, id):
        lst = self.app.lists[id]
        args = self.check_args({
            'title': (str, 'opt'),
            'description': (str, None, 'opt'),
            'features': (list, 'opt')
        })
        lst.edit(**args)
        self.write(lst.json(restricted=True, include=True))

class _ListItemsEndpoint(Endpoint):
    def get(self, id):
        lst = self.app.lists[id]
        self.write(json.dumps([i.json(True, True) for i in lst.items.values()]))

    async def post(self, id):
        lst = self.app.lists[id]
        args = self.check_args({
            'text': (str, None, 'opt'),
            'resource': (str, None, 'opt'),
            'title': str,
            'location': (dict, None, 'opt')
        })
        if args.get('location') is not None:
            try:
                args['location'] = Location.parse(args['location'])
            except TypeError:
                raise micro.ValueError('bad_location_type')
        item = await lst.items.create(asynchronous=ON, **args)
        self.write(item.json(restricted=True, include=True))

class _ItemEndpoint(Endpoint):
    def get(self, list_id, id):
        item = self.app.lists[list_id].items[id]
        self.write(item.json(restricted=True, include=True))

    async def post(self, list_id, id):
        item = self.app.lists[list_id].items[id]
        args = self.check_args({
            'text': (str, None, 'opt'),
            'resource': (str, None, 'opt'),
            'title': (str, 'opt'),
            'location': (dict, None, 'opt')
        })
        if args.get('location') is not None:
            try:
                args['location'] = Location.parse(args['location'])
            except TypeError:
                raise micro.ValueError('bad_location_type')
        await item.edit(asynchronous=ON, **args)
        self.write(item.json(restricted=True, include=True))

class _ItemCheckEndpoint(Endpoint):
    def post(self, lst_id, id):
        item = self.app.lists[lst_id].items[id]
        item.check()
        self.write(item.json(restricted=True, include=True))

class _ItemUncheckEndpoint(Endpoint):
    def post(self, lst_id, id):
        item = self.app.lists[lst_id].items[id]
        item.uncheck()
        self.write(item.json(restricted=True, include=True))
