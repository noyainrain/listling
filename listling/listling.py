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

"""Open Listling core."""

from __future__ import annotations

from datetime import date, datetime, timezone
import json
import typing
from typing import Any, Callable, Dict, Optional, Set, cast
from urllib.parse import urlsplit

import micro
from micro import (Activity, Application, AuthRequest, Collection, Editable, Location, Object,
                   Orderable, Trashable, Settings, Event, WithContent, error)
from micro.core import RewriteFunc, context
from micro.jsonredis import (JSONRedis, LexicalRedisSortedSet, RedisList, RedisSequence,
                             RedisSortedSet, lexical_value, script)
from micro.resource import Resource
from micro.util import expect_type, parse_isotime, randstr, str_or_none

from .list import Owners, OwnersEvent

_USE_CASES = {
    'simple': {'title': 'New list', 'features': []},
    'todo': {'title': 'New to-do list', 'features': ['check', 'assign']},
    'poll': {'title': 'New poll', 'features': ['vote'], 'mode': 'view'},
    'shopping': {'title': 'New shopping list', 'features': ['check']},
    'meeting-agenda': {'title': 'New meeting agenda', 'value_unit': 'min', 'features': ['value']},
    'playlist': {'title': 'New playlist', 'features': ['play']},
    'map': {'title': 'New map', 'features': ['location']}
}

_EXAMPLE_DATA = {
    'todo': (
        'Project tasks',
        'Things we need to do to complete our project.',
        [
            {'title': 'Do research', 'checked': True},
            {'title': 'Create draft', 'user_assigned': True},
            {'title': 'Write report', 'text': 'Summary of the results'}
        ]
    ),
    'poll': (
        'Lunch poll',
        'Where will we have lunch today?',
        [
            {'title': 'Burger place', 'user_voted': True},
            {'title': 'Pizzeria', 'text': 'Nice vegan options available'},
            {'title': 'Salad bar'}
        ]
    ),
    'shopping': (
        'Kitchen shopping list',
        'When you go shopping next time, please bring the items from this list.',
        [
            {'title': 'Soy sauce'},
            {'title': 'Vegetables', 'text': 'Especially tomatoes'},
            {'title': 'Chocolate'}
        ]
    ),
    'meeting-agenda': (
        'Working group agenda',
        'We meet on Monday and discuss important issues.',
        [
            {'title': 'Round of introductions'},
            {'title': 'Lunch poll', 'text': 'Where will we have lunch today?', 'value': 45},
            {
                'title': 'Next meeting',
                'text': 'When and where will our next meeting be?',
                'value': 5
            }
        ]
    ),
    'playlist': (
        'Party playlist',
        'Songs we want to hear at our get-together tonight.',
        [
            {
                'title': 'Rick Astley - Never Gonna Give You Up',
                'resource': 'https://www.youtube.com/watch?v=dQw4w9WgXcQ'
            },
            {
                'title': 'Rihanna - Diamonds',
                'resource': 'https://www.youtube.com/watch?v=lWA2pjMjpBs'
            },
            {
                'title': 'Did you know?',
                'text': "The lyrics for Rihanna's song Diamonds were written by singer-songwriter Sia in just 14 minutes."
            }
        ]
    ),
    'map': (
        'Delicious burger places in Berlin',
        'Hand-Picked by ourselves. Your favorite is missing? Let us know!',
        [
            {
                'title': 'Glück to go',
                'text': 'http://www.glueck-to-go.de/',
                'location': Location('Friesenstraße 26, 10965 Berlin, Germany',
                                     (52.48866, 13.394651))
            },
            {
                'title': 'L’herbivore',
                'text': 'https://lherbivore.de/',
                'location': Location('Petersburger Straße 38, 10249 Berlin, Germany',
                                     (52.522951, 13.449482))
            },
            {
                'title': 'YELLOW SUNSHINE',
                'text': 'http://www.yellow-sunshine.de/',
                'location': Location('Wiener Straße 19, 10999 Berlin, Germany',
                                     (52.497561, 13.430773))
            }
        ]
    )
}

class Listling(Application):
    """See :ref:`Listling`."""

    class Lists(Collection['List']):
        """See :ref:`Lists`."""

        app: Listling

        def create(self, use_case: str = 'simple') -> List:
            """See :http:post:`/api/lists`."""
            user = context.user.get()
            if not user:
                raise error.PermissionError()
            if use_case not in _USE_CASES:
                raise error.ValueError('use_case_unknown')

            data = _USE_CASES[use_case]
            id = 'List:{}'.format(randstr())
            now = self.app.now().timestamp()
            lst = List(
                id=id, app=self.app, authors=[user.id], title=data['title'], description=None,
                order=None, value_unit=data.get('value_unit'), features=data['features'],
                mode=data.get('mode', 'collaborate'), item_template=None,
                value_summary_ids=[('total', 0)] if 'value' in data['features'] else [],
                activity=Activity(id=f'{id}.activity', subscriber_ids=[], app=self.app))
            self.app.r.oset(lst.id, lst)
            self.app.r.zadd(f'{lst.id}.owners', {user.id.encode(): -now})
            self.app.r.zadd(f'{lst.id}.users', {user.id.encode(): -now})
            self.app.r.rpush(self.ids.key, lst.id)
            user.lists.add(lst)
            self.app.activity.publish(
                Event.create('create-list', None, {'lst': lst}, app=self.app))
            return lst

        async def create_example(self, use_case: str) -> List:
            """See :http:post:`/api/lists/create-example`."""
            if use_case not in _EXAMPLE_DATA:
                raise error.ValueError('use_case_unknown')
            data = _EXAMPLE_DATA[use_case]
            description = (
                '{}\n\n*This example was created just for you, so please feel free to play around.*'
                .format(data[1]))

            lst = self.create(use_case)
            await lst.edit(title=data[0], description=description)
            for item in data[2]:
                args = dict(item)
                checked = args.pop('checked', False)
                user_assigned = args.pop('user_assigned', False)
                user_voted = args.pop('user_voted', False)
                item = await lst.items.create(**args)
                if checked:
                    item.check()
                if user_assigned:
                    item.assignees.assign(context.user.get())
                if user_voted:
                    item.votes.vote()
            return lst

    def __init__(
            self, redis_url: str = '', email: str = 'bot@localhost', smtp_url: str = '',
            render_email_auth_message: Callable[[str, AuthRequest, str], str] = None, *,
            files_path: str = 'data', video_service_keys: Dict[str, str] = {}) -> None:
        super().__init__(
            redis_url=redis_url, email=email, smtp_url=smtp_url,
            render_email_auth_message=render_email_auth_message, files_path=files_path,
            video_service_keys=video_service_keys)
        self.types.update({'User': User, 'List': List, 'Item': Item, 'OwnersEvent': OwnersEvent})
        self.lists = Listling.Lists(RedisList('lists', self.r.r), app=self)
        self.items = Items(self)

    @staticmethod
    def now() -> datetime:
        """Return the current UTC date and time, as aware object."""
        return datetime.now(timezone.utc)

    def do_update(self) -> Dict[str, int]:
        if not self.r.get('version'):
            self.r.set('version', 9)
            return {}

        r: JSONRedis[Dict[str, object]] = JSONRedis(self.r.r)
        r.caching = False

        list_updates = {}
        items_updates = 0
        item_updates = {}
        item_rel_updates = set()

        # Deprecated since 0.39.0
        if not r.scard('items'):
            list_ids = [id.decode() for id in r.lrange('lists', 0, -1)]
            item_ids = [id.decode() for list_id in list_ids for id in r.lrange(f"{list_id}.items", 0, -1)]
            if item_ids:
                r.sadd('items', *item_ids)
                items_updates = 1

        lists = r.omget(r.lrange('lists', 0, -1), default=AssertionError)
        for lst in lists:
            # Deprecated since 0.41.0
            if 'order' not in lst:
                lst['order'] = None
                items = r.omget(r.lrange(f"{lst['id']}.items", 0, -1), default=AssertionError)
                for item in items:
                    id_by_title = lexical_value(cast(str, item['id']), cast(str, item['title']))
                    r.zadd(f"{lst['id']}.items.by_title", {id_by_title: 0})
                    r.hset(f"{lst['id']}.items.by_title.lexical", item['id'], id_by_title)
                list_updates[cast(str, lst['id'])] = lst
        r.omset(list_updates)

        items = r.omget(r.smembers('items'), default=AssertionError)
        for item in items:
            # Deprecated since 0.40.0
            if 'time' not in item:
                item['time'] = None
                item_updates[cast(str, item['id'])] = item
        r.omset(item_updates)

        # Deprecated since 0.39.1
        item_ids_valid = {id.decode() for id in r.smembers('items')}
        item_ids_db = {key.decode().split('.')[0] for key in r.keys('Item:*')}
        for id in item_ids_db - item_ids_valid:
            r.delete(f'{id}.assignees', f'{id}.votes')
            item_rel_updates.add(id)

        # Deprecated since 0.43.0
        for lst in lists:
            if 'value_summary_ids' not in lst:
                lst['activity'] = Activity(app=self, pre=None,
                                           **cast('dict[str, object]', lst['activity']))
                List(app=self, value_summary_ids=[], **lst).update_value_summary()
                list_updates[cast(str, lst['id'])] = lst

        return {
            'List': len(list_updates),
            'Items': items_updates,
            'Item': len(set(item_updates) | item_rel_updates)
        }

    def create_user(self, data):
        return User(**data)

    def create_settings(self) -> Settings:
        # pylint: disable=unexpected-keyword-arg; decorated
        return Settings(
            id='Settings', app=self, authors=[], title='My Open Listling', icon=None,
            icon_small=None, icon_large=None, provider_name=None, provider_url=None,
            provider_description={}, feedback_url=None, staff=[], push_vapid_private_key='',
            push_vapid_public_key='')

    def file_references(self):
        for lst in self.lists[:]:
            for item in lst.items[:]:
                if item.resource and urlsplit(item.resource.url).scheme == 'file':
                    yield item.resource.url

class User(micro.User):
    """See :ref:`User`."""

    class Lists(Collection['List']):
        """See :ref:`UserLists`."""
        # We use setattr / getattr to work around a Pylint error for Generic classes (see
        # https://github.com/PyCQA/pylint/issues/2443)

        def __init__(self, user):
            super().__init__(RedisSortedSet('{}.lists'.format(user.id), user.app.r), app=user.app)
            setattr(self, 'user', user)

        def add(self, lst: List) -> None:
            """See: :http:post:`/users/(id)/lists`."""
            if context.user.get() != getattr(self, 'user'):
                raise error.PermissionError()
            self.app.r.zadd(self.ids.key, {lst.id: -self.app.now().timestamp()})

        def remove(self, lst: List) -> None:
            """See :http:delete:`/users/(id)/lists/(list-id)`.

            If *lst* is not in the collection, a :exc:`micro.error.ValueError` is raised.
            """
            if context.user.get() != getattr(self, 'user'):
                raise error.PermissionError()
            if getattr(self, 'user') in lst.owners:
                raise error.ValueError(f"user {getattr(self, 'user').id} is owner of lst {lst.id}")
            if self.app.r.zrem(self.ids.key, lst.id) == 0:
                raise error.ValueError(
                    'No lst {} in lists of user {}'.format(lst.id, getattr(self, 'user').id))

        def read(self, *, user):
            """Return collection for reading."""
            if user != getattr(self, 'user'):
                raise error.PermissionError()
            return self

    def __init__(self, *, app: Application, **data: object) -> None:
        super().__init__(app=app, **data)
        self.lists = User.Lists(self)

    def json(self, restricted=False, include=False, *, rewrite=None):
        return {
            **super().json(restricted=restricted, include=include, rewrite=rewrite),
            **({'lists': self.lists.json(restricted=restricted, include=include, rewrite=rewrite)}
               if restricted and self.app.user == self else {})
        }

class List(Object, Editable):
    """See :ref:`List`."""

    app: Listling

    _PERMISSIONS: Dict[str, Dict[str, Set[str]]] = {
        'collaborate': {'user': {'list-modify', 'item-modify'}},
        'view':        {'user': set()}
    }

    class Items(Collection['Item'], Orderable):
        """See :ref:`Items`."""

        app: Listling

        def __init__(self, lst: List, ids: RedisSequence) -> None:
            super().__init__(ids, app=lst.app)
            self.lst = lst

        async def create(self, title: str, *, text: str = None, resource: str = None,
                         value: float = None, time: date = None, location: Location = None) -> Item:
            """See :http:post:`/api/lists/(id)/items`."""
            # pylint: disable=protected-access; List is a friend
            user = context.user.get()
            self.lst._check_permission(user, 'list-modify')
            assert user
            attrs = await WithContent.process_attrs({'text': text, 'resource': resource},
                                                    app=self.app)
            if str_or_none(title) is None:
                raise error.ValueError('title_empty')

            item = Item(
                id='Item:{}'.format(randstr()), app=self.app, authors=[user.id], trashed=False,
                text=attrs['text'], resource=attrs['resource'], list_id=self.lst.id, title=title,
                value=value, time=time.isoformat() if time else None,
                location=location.json() if location else None, checked=False)
            f = script(self.app.r.r, """
                local item_data, id_by_title = unpack(ARGV)
                local item = cjson.decode(item_data)
                redis.call("SET", item.id, item_data)
                redis.call("SADD", "items", item.id)
                redis.call("RPUSH", item.list_id .. ".items", item.id)
                redis.call("ZADD", item.list_id .. ".items.by_title", 0, id_by_title)
                redis.call("HSET", item.list_id .. ".items.by_title.lexical", item.id, id_by_title)
            """)
            f([], [json.dumps(item.json()), lexical_value(item.id, item.title)])
            self.lst.update_value_summary()
            self.lst.activity.publish(
                Event.create('list-create-item', self.lst, {'item': item}, self.app))
            return item

        def move(self, item: Object, to: Object | None) -> None:
            if not isinstance(self.ids, RedisList):
                items = List.Items(self.lst, RedisList(f'{self.lst.id}.items', self.app.r.r))
                items.move(item, to)
                return
            # pylint: disable=protected-access; List is a friend
            self.lst._check_permission(context.user.get(), 'list-modify')
            super().move(item, to)

    class _ListOwners(Owners):
        post_grant_script = 'redis.call("ZADD", user_id .. ".lists", -now, object_id)'

    def __init__(self, *, app: Listling, **data: object) -> None:
        activity = cast(Activity, data['activity'])
        super().__init__(id=cast(str, data['id']), app=app)
        Editable.__init__(self, authors=cast(typing.List[str], data['authors']), activity=activity)
        self.title = cast(str, data['title'])
        self.description = cast(Optional[str], data['description'])
        self.order = cast('str | None', data['order'])
        self.value_unit = cast(Optional[str], data['value_unit'])
        # Work around Lua CJSON encoding empty arrays as objects (see
        # https://github.com/mpx/lua-cjson/issues/11 and https://github.com/redis/redis/issues/8755)
        self.features = cast('list[str]', data['features'] or [])
        self.mode = cast(str, data['mode'])
        self.item_template = cast(Optional[str], data['item_template'])
        self.value_summary_ids = cast(
            'list[tuple[str, float]]',
            [tuple(entry) for entry in data['value_summary_ids']]) # type: ignore[attr-defined]
        self.owners = List._ListOwners(self)
        self.activity = activity
        self.activity.post = self._on_activity_publish
        self.activity.host = self

    @property
    def items(self) -> List.Items:
        # pylint: disable=missing-function-docstring; already documented
        ids = (
            RedisList(f'{self.id}.items', self.app.r.r) if self.order is None
            else LexicalRedisSortedSet(
                f'{self.id}.items.by_title', f'{self.id}.items.by_title.lexical', self.app.r.r))
        return List.Items(self, ids)

    def users(self, name=''):
        """See :http:get:`/api/lists/(id)/users?name=`."""
        f = script(self.app.r, """\
            local key, name = KEYS[1], string.lower(ARGV[1])
            local users = redis.call("mget", unpack(redis.call("zrange", key, 0, -1)))
            local results = {}
            for _, user in ipairs(users) do
                if string.find(string.lower(cjson.decode(user)["name"]), name, 1, true) then
                    table.insert(results, user)
                    if #results == 10 then
                        break
                    end
                end
            end
            return results
        """)
        # Note that returned users may be duplicates because we parse them directly, skipping the
        # JSONRedis cache
        users = f(['{}.users'.format(self.id)], [name])
        return [User(app=self.app, **json.loads(user.decode())) for user in users]

    def update_value_summary(self) -> List:
        """Compute and update the :attr:`value_summary_ids` table."""
        f = script(self.app.r.r, """
            local id = unpack(KEYS)
            local list = cjson.decode(redis.call("GET", id))
            local features = {}
            for _, feature in pairs(list.features) do
                features[feature] = true
            end

            local items = nil
            if features.value then
                local item_ids = redis.call("LRANGE", id .. ".items", 0, -1)
                if next(item_ids) then
                    items = redis.call("MGET", unpack(item_ids))
                else
                    items = {}
                end
            end
            return items
        """)
        items_data = cast('list[bytes] | None', f([self.id]))

        self.value_summary_ids = []
        if items_data is not None:
            items = (Item(app=self.app, **json.loads(item)) for item in items_data)
            self.value_summary_ids.append(
                ('total', sum(item.value or .0 for item in items if not item.trashed)))

        f = script(self.app.r.r, """
            local id, value_summary_ids = unpack(KEYS), unpack(ARGV)
            local list = cjson.decode(redis.call("GET", id))
            list.value_summary_ids = cjson.decode(value_summary_ids)
            redis.call("SET", id, cjson.encode(list))
        """)
        f([self.id], [json.dumps(self.value_summary_ids)])
        return self

    async def edit(self, **attrs: object) -> None:
        await super().edit(**attrs)
        self.update_value_summary()

    def do_edit(self, **attrs: Any) -> None:
        self._check_permission(context.user.get(), 'list-modify')
        if 'title' in attrs and str_or_none(attrs['title']) is None:
            raise error.ValueError('title_empty')
        if 'order' in attrs and attrs['order'] not in {None, 'title'}:
            raise error.ValueError(f"Unknown order {attrs['order']}")
        features = {'check', 'assign', 'vote', 'value', 'time', 'location', 'play'}
        if 'features' in attrs and not set(attrs['features']) <= features:
            raise error.ValueError('feature_unknown')
        if 'mode' in attrs and attrs['mode'] not in {'collaborate', 'view'}:
            raise error.ValueError('Unknown mode')

        if 'title' in attrs:
            self.title = attrs['title']
        if 'description' in attrs:
            self.description = str_or_none(attrs['description'])
        if 'order' in attrs:
            self.order = attrs['order']
        if 'value_unit' in attrs:
            self.value_unit = str_or_none(attrs['value_unit'])
        if 'features' in attrs:
            self.features = attrs['features']
        if 'mode' in attrs:
            self.mode = attrs['mode']
        if 'item_template' in attrs:
            self.item_template = str_or_none(attrs['item_template'])

    def json(self, restricted: bool = False, include: bool = False, *,
             rewrite: RewriteFunc = None) -> dict[str, object]:
        return {
            **super().json(restricted=restricted, include=include, rewrite=rewrite),
            **Editable.json(self, restricted=restricted, include=include, rewrite=rewrite),
            'title': self.title,
            'description': self.description,
            'order': self.order,
            'value_unit': self.value_unit,
            'features': self.features,
            'mode': self.mode,
            'item_template': self.item_template,
            'value_summary_ids': self.value_summary_ids,
            'activity': self.activity.json(restricted=restricted, rewrite=rewrite),
            **(
                {
                    'owners': self.owners.json(restricted=restricted, include=include,
                                               rewrite=rewrite),
                    'items': self.items.json(restricted=restricted, include=include,
                                             rewrite=rewrite)
                } if restricted else {})
        }

    def _check_permission(self, user: Optional[micro.User], op: str) -> None:
        permissions = List._PERMISSIONS[self.mode]
        if not (user and (
                op in permissions['user'] or
                user in self.owners or
                user in self.app.settings.staff)):
            raise error.PermissionError()

    def _on_activity_publish(self, event):
        self.app.r.zadd('{}.users'.format(self.id),
                        {event.user.id.encode(): -self.app.now().timestamp()})

class Item(Object, Editable, Trashable, WithContent):
    """See :ref:`Item`."""
    # pylint: disable=invalid-overridden-method; do_edit may be async

    class Assignees(Collection):
        """See :ref:`ItemAssignees`."""

        def __init__(self, item, *, app):
            super().__init__(RedisSortedSet('{}.assignees'.format(item.id), app.r), app=app)
            self.item = item

        def assign(self, assignee: User) -> None:
            """See :http:post:`/api/items/(id)/assignees`."""
            # pylint: disable=protected-access; Item is a friend
            self.item._check_permission(context.user.get(), 'list-modify')
            if 'assign' not in self.item.list.features:
                raise error.ValueError('Disabled item list features assign')
            if self.item.trashed:
                raise error.ValueError('Trashed item')
            if not self.app.r.zadd(self.ids.key,
                                   {assignee.id.encode(): -self.app.now().timestamp()}):
                raise error.ValueError(
                    'assignee {} already in assignees of item {}'.format(assignee.id, self.item.id))
            self.item.list.activity.publish(
                Event.create('item-assignees-assign', self.item, detail={'assignee': assignee},
                             app=self.app))

        def unassign(self, assignee: User) -> None:
            """See :http:delete:`/api/items/(id)/assignees/(assignee-id)`."""
            # pylint: disable=protected-access; Item is a friend
            self.item._check_permission(context.user.get(), 'list-modify')
            if 'assign' not in self.item.list.features:
                raise error.ValueError('Disabled item list features assign')
            if self.item.trashed:
                raise error.ValueError('Trashed item')
            if not self.app.r.zrem(self.ids.key, assignee.id.encode()):
                raise error.ValueError(
                    'No assignee {} in assignees of item {}'.format(assignee.id, self.item.id))
            self.item.list.activity.publish(
                Event.create('item-assignees-unassign', self.item, detail={'assignee': assignee},
                             app=self.app))

    class Votes(Collection):
        """See :ref:`ItemVotes`."""

        def __init__(self, item, *, app):
            super().__init__(RedisSortedSet('{}.votes'.format(item.id), app.r.r), app=app)
            self.item = item

        def vote(self) -> None:
            """See :http:post:`/api/items/(id)/votes`."""
            user = context.user.get()
            if not user:
                raise error.PermissionError()
            if 'vote' not in self.item.list.features:
                raise error.ValueError('Disabled item list features vote')
            if self.app.r.zadd(self.ids.key, {user.id.encode(): -self.app.now().timestamp()}):
                self.item.list.activity.publish(
                    Event.create('item-votes-vote', self.item, app=self.app))

        def unvote(self) -> None:
            """See :http:delete:`/api/items/(id)/votes/user`."""
            user = context.user.get()
            if not user:
                raise error.PermissionError()
            if 'vote' not in self.item.list.features:
                raise error.ValueError('Disabled item list features vote')
            if self.app.r.zrem(self.ids.key, user.id.encode()):
                self.item.list.activity.publish(
                    Event.create('item-votes-unvote', self.item, app=self.app))

        def has_user_voted(self, user):
            """See :ref:`ItemVotes` *user_voted*."""
            return user and user in self

        def json(self, restricted=False, include=False, *, rewrite=None, slc=None):
            return {
                **super().json(restricted=restricted, include=include, rewrite=rewrite, slc=slc),
                **({'user_voted': self.has_user_voted(self.app.user)} if restricted else {})
            }

    def __init__(self, *, app: Listling, **data: object) -> None:
        super().__init__(id=cast(str, data['id']), app=app)
        Editable.__init__(self, authors=cast(typing.List[str], data['authors']),
                          activity=lambda: self.list.activity)
        Trashable.__init__(self, trashed=cast(bool, data['trashed']),
                           activity=lambda: self.list.activity)
        WithContent.__init__(self, text=cast(Optional[str], data['text']),
                             resource=cast(Optional[Resource], data['resource']))
        self._list_id = cast(str, data['list_id'])
        self.title = cast(str, data['title'])
        self.value = cast(Optional[float], data['value'])
        self.time = parse_isotime(cast(str, data['time'])) if data['time'] else None
        self.location = (
            Location.parse(cast(Dict[str, object], data['location'])) if data['location'] else None)
        self.checked = cast(bool, data['checked'])
        self.assignees = Item.Assignees(self, app=app)
        self.votes = Item.Votes(self, app=app)

    @property
    def list(self):
        # pylint: disable=missing-function-docstring; already documented
        return self.app.lists[self._list_id]

    def __eq__(self, other: object) -> bool:
        return isinstance(other, Object) and self.id == other.id

    def __hash__(self) -> int:
        return hash(self.id)

    def delete(self) -> None:
        f = script(self.app.r.r, """
            local id = KEYS[1]
            local item = cjson.decode(redis.call("GET", id))
            redis.call("DEL", id, id .. ".assignees", id .. ".votes")
            redis.call("SREM", "items", id)
            redis.call("LREM", item.list_id .. ".items", 1, id)
            local lexical_key = item.list_id .. ".items.by_title.lexical"
            redis.call(
                "ZREM", item.list_id .. ".items.by_title", redis.call("HGET", lexical_key, id)
            )
            redis.call("HDEL", lexical_key, id)
        """)
        f([self.id])

    def check(self):
        """See :http:post:`/api/items/(id)/check`."""
        _check_feature(self.app.user, 'check', self)
        self._check_permission(self.app.user, 'item-modify')
        self.checked = True
        self.app.r.oset(self.id, self)
        self.list.activity.publish(Event.create('item-check', self, app=self.app))

    def uncheck(self):
        """See :http:post:`/api/items/(id)/uncheck`."""
        _check_feature(self.app.user, 'check', self)
        self._check_permission(self.app.user, 'item-modify')
        self.checked = False
        self.app.r.oset(self.id, self)
        self.list.activity.publish(Event.create('item-uncheck', self, app=self.app))

    async def edit(self, **attrs: object) -> None:
        await super().edit(**attrs)
        self.list.update_value_summary()

    async def do_edit(self, **attrs: Any) -> None:
        self._check_permission(self.app.user, 'item-modify')
        attrs = cast(Dict[str, Any], await WithContent.pre_edit(self, attrs))
        if 'title' in attrs and str_or_none(attrs['title']) is None:
            raise error.ValueError('title_empty')

        WithContent.do_edit(self, **attrs)
        if 'title' in attrs:
            self.title = attrs['title']
            f = script(self.app.r.r, """
                local id, id_by_title = unpack(KEYS), unpack(ARGV)
                local object = cjson.decode(redis.call("GET", id))
                local items_key = object.list_id .. ".items.by_title"
                local lexical_key = items_key .. ".lexical"
                redis.call("ZREM", items_key, redis.call("HGET", lexical_key, id))
                redis.call("ZADD", items_key, 0, id_by_title)
                redis.call("HSET", lexical_key, id, id_by_title)
            """)
            f([self.id], [lexical_value(self.id, self.title)])
        if 'value' in attrs:
            self.value = attrs['value']
        if 'time' in attrs:
            self.time = attrs['time']
        if 'location' in attrs:
            self.location = attrs['location']

    def trash(self):
        self._check_permission(self.app.user, 'item-modify')
        super().trash()
        self.list.update_value_summary()

    def restore(self):
        self._check_permission(self.app.user, 'item-modify')
        super().restore()
        self.list.update_value_summary()

    def json(self, restricted: bool = False, include: bool = False, *,
             rewrite: RewriteFunc = None) -> Dict[str, object]:
        return {
            **super().json(restricted=restricted, include=include, rewrite=rewrite),
            **Editable.json(self, restricted=restricted, include=include, rewrite=rewrite),
            **Trashable.json(self, restricted=restricted, include=include, rewrite=rewrite),
            **WithContent.json(self, restricted=restricted, include=include, rewrite=rewrite),
            'list_id': self._list_id,
            'title': self.title,
            'value': self.value,
            'time': self.time.isoformat() if self.time else None,
            'location': self.location.json() if self.location else None,
            'checked': self.checked,
            **(
                {
                    'assignees': self.assignees.json(restricted=restricted, include=include,
                                                     rewrite=rewrite, slc=slice(None))
                } if include else {}),
            **(
                {'votes': self.votes.json(restricted=restricted, include=include, rewrite=rewrite)}
                if include else {})
        }

    def _check_permission(self, user: Optional[micro.User], op: str) -> None:
        lst = self.list
        # pylint: disable=protected-access; List is a friend
        permissions = List._PERMISSIONS[lst.mode]
        if not (user and (
                op in permissions['user'] or
                user in lst.owners or
                user in self.app.settings.staff)):
            raise error.PermissionError()

class Items:
    """See :ref:`Items`."""

    def __init__(self, app: Listling) -> None:
        self.app = app

    def __getitem__(self, key: str) -> Item:
        if not key.startswith('Item:'):
            raise KeyError(key)
        return self.app.r.oget(key, default=KeyError, expect=expect_type(Item))

def _check_feature(user, feature, item):
    if feature not in item.list.features:
        raise error.ValueError('feature_disabled')
    if not user:
        raise error.PermissionError()
