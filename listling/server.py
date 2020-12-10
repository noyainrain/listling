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

from datetime import timedelta
from http import HTTPStatus
import json
from typing import Callable, Dict, List, Optional
from urllib.parse import urlsplit

from tornado.web import HTTPError, RequestHandler

from micro import Location, error
from micro.jsonredis import script
from micro.ratelimit import RateLimit, RateLimitError
from micro.server import (
    Endpoint, CollectionEndpoint, Handler, Server, UI, make_activity_endpoints,
    make_orderable_endpoints, make_trashable_endpoints)
from micro.util import Expect, randstr

from . import Listling
from .list import Owners

def make_server(
        *, port: int = 8080, url: str = None, debug: bool = False, redis_url: str = '',
        smtp_url: str = '', files_path: str = 'data', video_service_keys: Dict[str, str] = {},
        client_map_service_key: Optional[str] = None) -> Server:
    """Create an Open Listling server."""
    app = Listling(redis_url=redis_url, smtp_url=smtp_url, files_path=files_path,
                   video_service_keys=video_service_keys)
    handlers = [
        # API
        (r'/api/users/([^/]+)/lists$', _UserListsEndpoint),
        (r'/api/users/([^/]+)/lists/([^/]+)$', _UserListEndpoint),
        (r'/api/lists$', _ListsEndpoint),
        (r'/api/lists/create-example$', _ListsCreateExampleEndpoint),
        (r'/api/lists/([^/]+)$', _ListEndpoint),
        *_make_owners_endpoints(r'/api/lists/([^/]+)/owners', lambda id: app.lists[id].owners),
        (r'/api/lists/([^/]+)/users$', _ListUsersEndpoint),
        (r'/api/lists/([^/]+)/items$', _ListItemsEndpoint),
        *make_orderable_endpoints(r'/api/lists/([^/]+)/items', lambda id: app.lists[id].items),
        *make_activity_endpoints(r'/api/lists/([^/]+)/activity',
                                 lambda id, *args: app.lists[id].activity),
        (r'/api/lists/([^/]+)/items/([^/]+)$', _ItemEndpoint),
        *make_trashable_endpoints(r'/api/lists/([^/]+)/items/([^/]+)',
                                  lambda list_id, id: app.lists[list_id].items[id]),
        (r'/api/lists/([^/]+)/items/([^/]+)/check$', _ItemCheckEndpoint),
        (r'/api/lists/([^/]+)/items/([^/]+)/uncheck$', _ItemUncheckEndpoint),
        (r'/api/lists/([^/]+)/items/([^/]+)/assignees$', _ItemAssigneesEndpoint),
        (r'/api/lists/([^/]+)/items/([^/]+)/assignees/([^/]+)$', _ItemAssigneeEndpoint),
        (r'/api/lists/([^/]+)/items/([^/]+)/votes', _ItemVotesEndpoint),
        (r'/api/lists/([^/]+)/items/([^/]+)/votes/user', _ItemVoteEndpoint),
        # UI
        (r'/s$', _Shorts),
        (r'/s/(.*)$', _Short),
        (r'/lists/([^/]+)(?:/[^/]+)?$', _ListPage)
    ]
    return Server(app, handlers, port=port, url=url, debug=debug, client_config={
        'modules_path': 'node_modules',
        'service_path': 'listling/service.js',
        'shell': ['listling.css', 'listling', 'images'],
        'map_service_key': client_map_service_key,
        'description': 'Make and edit lists collaboratively. Free, simple and no registration required.',
        'color': '#4d8dd9',
        'share_target': True,
        'share_target_accept': ['image/bmp', 'image/gif', 'image/jpeg', 'image/png',
                                'image/svg+xml', '.bmp', '.gif', '.jpg', '.png', '.svg']
    })

class _UserListsEndpoint(CollectionEndpoint):
    app: Listling

    def initialize(self):
        super().initialize(
            get_collection=lambda id: self.app.users[id].lists.read(user=self.current_user))

    def post(self, id: str) -> None:
        lists = self.get_collection(id)
        try:
            lst = self.app.lists[self.get_arg('list_id', Expect.str)]
        except KeyError as e:
            raise error.ValueError(f'No list {e}') from e
        lists.add(lst)
        self.write({})

class _UserListEndpoint(Endpoint):
    app: Listling

    def delete(self, id: str, list_id: str) -> None:
        lists = self.app.users[id].lists
        lst = lists[list_id]
        lists.remove(lst)
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
    app: Listling

    def get(self, id):
        lst = self.app.lists[id]
        self.write(lst.json(restricted=True, include=True))

    async def post(self, id: str) -> None:
        lst = self.app.lists[id]
        args = self.check_args({
            'title': (str, 'opt'),
            'description': (str, None, 'opt'),
            'features': (list, 'opt'),
            'mode': (str, 'opt'),
            'item_template': (str, None, 'opt')
        })
        if 'value_unit' in self.args:
            args['value_unit'] = self.get_arg('value_unit', Expect.opt(Expect.str))
        await lst.edit(**args)
        self.write(lst.json(restricted=True, include=True))

def _make_owners_endpoints(url: str, get_owners: Callable[..., Owners]) -> List[Handler]:
    return [(fr'{url}$', _OwnersEndpoint, {'get_collection': get_owners}),
            (fr'{url}/([^/]+)$', _OwnerEndpoint, {'get_owners': get_owners})]

class _OwnersEndpoint(CollectionEndpoint):
    def post(self, *args: str) -> None:
        owners = self.get_collection(*args)
        try:
            user = self.app.users[self.get_arg('user_id', Expect.str)]
        except KeyError as e:
            raise error.ValueError(f'No user {e}') from e
        owners.grant(user)

class _OwnerEndpoint(Endpoint):
    def initialize(self, *, get_owners: Callable[..., Owners]) -> None: # type: ignore[override]
        super().initialize()
        self.get_owners = get_owners

    def delete(self, *args: str) -> None:
        owners = self.get_owners(*args[:-1])
        user = owners[args[-1]]
        owners.revoke(user)

class _ListUsersEndpoint(Endpoint):
    def get(self, id):
        lst = self.app.lists[id]
        name = self.get_query_argument('name', '')
        users = lst.users(name)
        self.write({'items': [user.json(restricted=True, include=True) for user in users]})

class _ListItemsEndpoint(Endpoint):
    app: Listling

    def get(self, id):
        lst = self.app.lists[id]
        self.write(
            json.dumps(
                [item.json(restricted=True, include=True, rewrite=self.server.rewrite)
                 for item in lst.items[:]]))

    async def post(self, id: str) -> None:
        lst = self.app.lists[id]
        args = self.check_args({
            'text': (str, None, 'opt'),
            'resource': (str, None, 'opt'),
            'title': str,
            'location': (dict, None, 'opt')
        })
        if args.get('resource') is not None:
            args['resource'] = self.server.rewrite(args['resource'], reverse=True)
        value = self.get_arg('value', Expect.opt(Expect.float), default=None)
        if args.get('location') is not None:
            try:
                args['location'] = Location.parse(args['location'])
            except TypeError as e:
                raise error.ValueError('bad_location_type') from e
        item = await lst.items.create(value=value, **args)
        self.write(item.json(restricted=True, include=True, rewrite=self.server.rewrite))

class _ItemEndpoint(Endpoint):
    app: Listling

    def get(self, list_id, id):
        item = self.app.lists[list_id].items[id]
        self.write(item.json(restricted=True, include=True, rewrite=self.server.rewrite))

    async def post(self, list_id: str, id: str) -> None:
        item = self.app.lists[list_id].items[id]
        args = self.check_args({
            'text': (str, None, 'opt'),
            'resource': (str, None, 'opt'),
            'title': (str, 'opt'),
            'location': (dict, None, 'opt')
        })
        if args.get('resource') is not None:
            args['resource'] = self.server.rewrite(args['resource'], reverse=True)
        if 'value' in self.args:
            args['value'] = self.get_arg('value', Expect.opt(Expect.float))
        if args.get('location') is not None:
            try:
                args['location'] = Location.parse(args['location'])
            except TypeError as e:
                raise error.ValueError('bad_location_type') from e
        await item.edit(**args)
        self.write(item.json(restricted=True, include=True, rewrite=self.server.rewrite))

class _ItemCheckEndpoint(Endpoint):
    def post(self, lst_id, id):
        item = self.app.lists[lst_id].items[id]
        item.check()
        self.write(item.json(restricted=True, include=True, rewrite=self.server.rewrite))

class _ItemUncheckEndpoint(Endpoint):
    def post(self, lst_id, id):
        item = self.app.lists[lst_id].items[id]
        item.uncheck()
        self.write(item.json(restricted=True, include=True, rewrite=self.server.rewrite))

class _ItemAssigneesEndpoint(CollectionEndpoint):
    def initialize(self):
        super().initialize(
            get_collection=lambda list_id, id: self.app.lists[list_id].items[id].assignees)

    def post(self, list_id, id):
        assignees = self.get_collection(list_id, id)
        try:
            assignee_id = self.get_arg('assignee_id', Expect.str)
            assignee = self.app.users[assignee_id]
        except KeyError as e:
            raise error.ValueError(f'No assignee {assignee_id}') from e
        assignees.assign(assignee)
        self.set_status(HTTPStatus.CREATED)
        self.write({})

class _ItemAssigneeEndpoint(Endpoint):
    def delete(self, list_id, id, assignee_id):
        assignees = self.app.lists[list_id].items[id].assignees
        assignee = assignees[assignee_id]
        assignees.unassign(assignee)
        self.write({})

class _ItemVotesEndpoint(CollectionEndpoint):
    def initialize(self):
        super().initialize(
            get_collection=lambda list_id, id: self.app.lists[list_id].items[id].votes)

    def post(self, list_id, id):
        votes = self.get_collection(list_id, id)
        votes.vote()
        self.set_status(HTTPStatus.CREATED)
        self.write({})

class _ItemVoteEndpoint(Endpoint):
    def delete(self, list_id, id):
        votes = self.app.lists[list_id].items[id].votes
        votes.unvote()
        self.write({})

class _Shorts(RequestHandler):
    def post(self) -> None:
        try:
            url = self.request.body.decode()
        except UnicodeDecodeError as e:
            raise HTTPError(HTTPStatus.BAD_REQUEST) from e
        # Relative URL may produce redirect loop
        components = urlsplit(url)
        if not (components.scheme or components.netloc or components.path.startswith('/')):
            raise HTTPError(HTTPStatus.BAD_REQUEST)

        # Choose short length n such that (1 - (1 - s / 26 ** n) ** r) <= p, where the probability
        # to find any short p = 1‰, the presumed number of active shorts s = 50 and the rate limit
        # r = 100
        short = randstr(5)
        f = script(self.application.settings['server'].app.r, """
            local key, url = KEYS[1], ARGV[1]
            redis.call('SET', key, url)
            redis.call('EXPIRE', key, 24 * 60 * 60)
        """)
        f([f'short:{short}'], [url])
        self.set_status(HTTPStatus.CREATED)
        self.set_header('Location', f'/s/{short}')

class _Short(RequestHandler):
    def get(self, short: str) -> None:
        app = self.application.settings['server'].app
        try:
            app.rate_limiter.count(RateLimit('shorts.get', 100, timedelta(days=1)),
                                   self.request.remote_ip)
        except RateLimitError as e:
            raise HTTPError(HTTPStatus.TOO_MANY_REQUESTS) from e
        url = app.r.get(f'short:{short}')
        if not url:
            raise HTTPError(HTTPStatus.NOT_FOUND)
        self.redirect(url, permanent=True)

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
