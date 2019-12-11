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

# pylint: disable=abstract-method; Tornado handlers define a semi-abstract data_received()
# pylint: disable=arguments-differ; Tornado handler arguments are defined by URLs
# pylint: disable=missing-docstring; Tornado handlers are documented globally

"""Open Listling server."""

from http import HTTPStatus
import json

import micro
from micro import Location
from micro.server import (Endpoint, CollectionEndpoint, Server, UI, make_activity_endpoint,
                          make_orderable_endpoints, make_trashable_endpoints)
from micro.util import ON

from . import Listling

def make_server(*, port=8080, url=None, debug=False, redis_url='', smtp_url='',
                video_service_keys={}, client_map_service_key=None):
    """Create an Open Listling server."""
    app = Listling(redis_url, smtp_url=smtp_url, video_service_keys=video_service_keys)
    handlers = [
        # API
        (r'/api/users/([^/]+)/lists$', _UserListsEndpoint),
        (r'/api/users/([^/]+)/lists/([^/]+)$', _UserListEndpoint),
        (r'/api/lists$', _ListsEndpoint),
        (r'/api/lists/create-example$', _ListsCreateExampleEndpoint),
        (r'/api/lists/([^/]+)$', _ListEndpoint),
        (r'/api/lists/([^/]+)/users$', _ListUsersEndpoint),
        (r'/api/lists/([^/]+)/items$', _ListItemsEndpoint),
        *make_orderable_endpoints(r'/api/lists/([^/]+)/items', lambda id: app.lists[id].items),
        make_activity_endpoint(r'/api/lists/([^/]+)/activity',
                               lambda id, *a: app.lists[id].activity),
        (r'/api/lists/([^/]+)/items/([^/]+)$', _ItemEndpoint),
        *make_trashable_endpoints(r'/api/lists/([^/]+)/items/([^/]+)',
                                  lambda list_id, id: app.lists[list_id].items[id]),
        (r'/api/lists/([^/]+)/items/([^/]+)/check$', _ItemCheckEndpoint),
        (r'/api/lists/([^/]+)/items/([^/]+)/uncheck$', _ItemUncheckEndpoint),
        (r'/api/lists/([^/]+)/items/([^/]+)/votes', _ItemVotesEndpoint),
        (r'/api/lists/([^/]+)/items/([^/]+)/votes/user', _ItemVoteEndpoint),
        # UI
        (r'/lists/([^/]+)(?:/[^/]+)?$', _ListPage)
    ]
    return Server(app, handlers, port=port, url=url, debug=debug, client_config={
        'modules_path': 'node_modules',
        'service_path': 'listling/service.js',
        'shell': ['listling.css', 'listling', 'images'],
        'map_service_key': client_map_service_key,
        'description': 'Service to make and edit lists collaboratively. Free, simple and no registration required.',
        'color': '#4d8dd9'
    })

class _UserListsEndpoint(CollectionEndpoint):
    def initialize(self):
        super().initialize(
            get_collection=lambda id: self.app.users[id].lists.read(user=self.current_user))

    def post(self, id):
        args = self.check_args({'list_id': str})
        list_id = args.pop('list_id')
        try:
            args['lst'] = self.app.lists[list_id]
        except KeyError:
            raise micro.ValueError('No list {}'.format(list_id))
        lists = self.get_collection(id)
        lists.add(**args, user=self.current_user)
        self.write({})

class _UserListEndpoint(Endpoint):
    def delete(self, id, list_id):
        lists = self.app.users[id].lists
        lst = lists[list_id]
        lists.remove(lst, user=self.current_user)
        self.write({})

class _ListsEndpoint(Endpoint):
    def post(self):
        # Compatibility for endpoint version (deprecated since 0.22.0)
        args = self.check_args({'use_case': (str, 'opt'), 'v': (int, 'opt')})
        lst = self.app.lists.create(**args)
        self.write(lst.json(restricted=True, include=True))

class _ListsCreateExampleEndpoint(Endpoint):
    async def post(self):
        args = self.check_args({'use_case': str})
        lst = await self.app.lists.create_example(**args)
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
            'features': (list, 'opt'),
            'mode': (str, 'opt')
        })
        lst.edit(**args)
        self.write(lst.json(restricted=True, include=True))

class _ListUsersEndpoint(Endpoint):
    def get(self, id):
        lst = self.app.lists[id]
        name = self.get_query_argument('name', '')
        users = lst.users(name)
        self.write({'items': [user.json(restricted=True, include=True) for user in users]})

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
        item = await lst.items.create(**args)
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

class _ItemVotesEndpoint(CollectionEndpoint):
    def initialize(self):
        super().initialize(
            get_collection=lambda list_id, id: self.app.lists[list_id].items[id].votes)

    def post(self, list_id, id):
        votes = self.get_collection(list_id, id)
        votes.vote(user=self.current_user)
        self.set_status(HTTPStatus.CREATED)
        self.write({})

class _ItemVoteEndpoint(Endpoint):
    def delete(self, list_id, id):
        votes = self.app.lists[list_id].items[id].votes
        votes.unvote(user=self.current_user)
        self.write({})

class _ListPage(UI):
    def get_meta(self, *args: str):
        try:
            lst = self.app.lists['List:{}'.format(args[0])]
        except KeyError:
            return super().get_meta()
        description = lst.description or 'Shared list'
        return {
            **super().get_meta(),
            'title': '{} - {}'.format(lst.title, self.app.settings.title),
            'description': description,
            'og:title': lst.title,
            'og:description': description
        }
