# Open Listling
# Copyright (C) 2017 Open Listling contributors
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

"""Open Listling server."""

import http
import json

import micro
from micro.server import Endpoint, Server
from tornado.web import HTTPError

from . import Listling

# micro
def make_orderable_endpoints(url, get_list):
    return [(url + r'/move', _OrderableMoveEndpoint, {'get_list': get_list})]

class _OrderableMoveEndpoint(Endpoint):
    def initialize(self, get_list):
        super().initialize()
        self.get_list = get_list

    def post(self, *args):
        seq = self.get_list(*args)
        args = self.check_args({'item_id': str, 'to_id': (str, None)})

        try:
            args['item'] = seq[args.pop('item_id')]
        except KeyError:
            raise micro.ValueError('item_not_found')
        args['to'] = args.pop('to_id')
        if args['to'] is not None:
            try:
                args['to'] = seq[args['to']]
            except KeyError:
                raise micro.ValueError('to_not_found')

        seq.move(**args)
        self.write(json.dumps(None))

def make_trashable_endpoints(url, get_object):
    return [
        (url + r'/trash', _TrashableTrashEndpoint, {'get_object': get_object}),
        (url + r'/restore', _TrashableRestoreEndpoint, {'get_object': get_object})
    ]

class _TrashableTrashEndpoint(Endpoint):
    def initialize(self, get_object):
        super().initialize()
        self.get_object = get_object

    def post(self, *args):
        obj = self.get_object(*args)
        obj.trash()
        self.write(obj.json(restricted=True))

class _TrashableRestoreEndpoint(Endpoint):
    def initialize(self, get_object):
        super().initialize()
        self.get_object = get_object

    def post(self, *args):
        obj = self.get_object(*args)
        obj.restore()
        self.write(obj.json(restricted=True))
# /micro

def make_server(port=8080, url=None, debug=False, redis_url='', smtp_url=''):
    """Create an Open Listling server."""
    app = Listling(redis_url, smtp_url=smtp_url)
    handlers = [
        (r'/api/lists$', ListsEndpoint),
        (r'/api/previews/(.+)$', ResolveContentEndpoint),
        (r'/api/lists/create-example$', ListsCreateExampleEndpoint),
        (r'/api/lists/([^/]+)$', ListEndpoint),
        (r'/api/lists/([^/]+)/items$', ListItemsEndpoint),
        *make_orderable_endpoints(r'/api/lists/([^/]+)/items', lambda i: app.lists[i].items),
        (r'/api/lists/([^/]+)/items/([^/]+)$', ItemEndpoint),
        *make_trashable_endpoints(r'/api/lists/([^/]+)/items/([^/]+)', lambda i, j: app.lists[i].items[j]),
        (r'/api/lists/([^/]+)/items/([^/]+)/check', ItemCheckEndpoint),
        (r'/api/lists/([^/]+)/items/([^/]+)/uncheck', ItemUncheckEndpoint)
    ]
    return Server(app, handlers, port, url, client_modules_path='node_modules', debug=debug)

class ResolveContentEndpoint(Endpoint):
    async def get(self, url):
        content = await self.app.resolve_content(url)
        print('content', content)
        if content:
            self.write(vars(content))
        else:
            raise HTTPError(http.client.NOT_FOUND)

class ListsEndpoint(Endpoint):
    def post(self):
        args = self.check_args({
            'title': str,
            'description': (str, None, 'opt'),
            'features': (dict, 'opt')
            # TODO check if keys and values are strings
        })
        lst = self.app.lists.create(**args)
        self.write(lst.json(restricted=True, include=True))

class ListsCreateExampleEndpoint(Endpoint):
    def post(self):
        args = self.check_args({'kind': str})
        lst = self.app.lists.create_example(**args)
        self.write(lst.json(restricted=True, include=True))

class ListEndpoint(Endpoint):
    def get(self, id):
        lst = self.app.lists[id]
        self.write(lst.json(restricted=True, include=True))

    def post(self, id):
        lst = self.app.lists[id]
        args = self.check_args({'title': (str, 'opt'), 'description': (str, None, 'opt')})
        lst.edit(**args)
        self.write(lst.json(restricted=True, include=True))

class ListItemsEndpoint(Endpoint):
    def get(self, id):
        lst = self.app.lists[id]
        self.write(json.dumps([i.json(True, True) for i in lst.items.values()]))

    def post(self, id):
        lst = self.app.lists[id]
        args = self.check_args({'title': str, 'description': (str, None, 'opt')})
        item = lst.items.create(**args)
        self.write(item.json(restricted=True, include=True))

class ItemEndpoint(Endpoint):
    def get(self, list_id, id):
        item = self.app.lists[list_id].items[id]
        self.write(item.json(restricted=True, include=True))

    def post(self, list_id, id):
        item = self.app.lists[list_id].items[id]
        args = self.check_args({'title': (str, 'opt'), 'description': (str, None, 'opt')})
        item.edit(**args)
        self.write(item.json(restricted=True, include=True))

class ItemCheckEndpoint(Endpoint):
    def post(self, lst_id, id):
        item = self.app.lists[lst_id].items[id]
        item.check()
        self.write(item.json(restricted=True, include=True))

class ItemUncheckEndpoint(Endpoint):
    def post(self, lst_id, id):
        item = self.app.lists[lst_id].items[id]
        item.uncheck()
        self.write(item.json(restricted=True, include=True))
