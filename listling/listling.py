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

"""Open Listling core."""

import json
from time import time
from urllib.parse import urlsplit

import micro
from micro import (Activity, Application, Collection, Editable, Location, Object, Orderable,
                   Trashable, Settings, Event, WithContent, error)
from micro.jsonredis import JSONRedis, RedisSortedSet, script
from micro.util import parse_isotime, randstr, str_or_none

_USE_CASES = {
    'simple': {'title': 'New list', 'features': []},
    'todo': {'title': 'New to-do list', 'features': ['check', 'assign']},
    'poll': {'title': 'New poll', 'features': ['vote'], 'mode': 'view'},
    'shopping': {'title': 'New shopping list', 'features': ['check']},
    'meeting-agenda': {'title': 'New meeting agenda', 'features': []},
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
            {'title': 'Lunch poll', 'text': 'Where will we have lunch today?'},
            {'title': 'Next meeting', 'text': 'When and where will our next meeting be?'}
        ]
    ),
    'playlist': (
        'Party playlist',
        'Songs we want to hear at our get-together tonight.',
        [
            {
                'title': 'Rick Astley - Never Gonna Give You Up',
                'text': 'https://www.youtube.com/watch?v=dQw4w9WgXcQ',
                'resource': 'https://www.youtube.com/watch?v=dQw4w9WgXcQ'
            },
            {
                'title': 'Rihanna - Diamonds',
                'text': 'https://www.youtube.com/watch?v=lWA2pjMjpBs',
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
                'text': 'Website: http://www.glueck-to-go.de/',
                'location': Location('Friesenstraße 26, 10965 Berlin, Germany',
                                     (52.48866, 13.394651))
            },
            {
                'title': 'L’herbivore',
                'text': 'Website: https://lherbivore.de/',
                'location': Location('Petersburger Straße 38, 10249 Berlin, Germany',
                                     (52.522951, 13.449482))
            },
            {
                'title': 'YELLOW SUNSHINE',
                'text': 'Website: http://www.yellow-sunshine.de/',
                'location': Location('Wiener Straße 19, 10999 Berlin, Germany',
                                     (52.497561, 13.430773))
            }
        ]
    )
}

class Listling(Application):
    """See :ref:`Listling`."""

    class Lists(Collection):
        """See :ref:`Lists`."""

        def create(self, use_case='simple', *, v=2):
            """See :http:post:`/api/lists`."""
            # pylint: disable=unused-argument; former feature toggle
            # Compatibility for endpoint version (deprecated since 0.22.0)
            if not self.app.user:
                raise micro.PermissionError()
            if use_case not in _USE_CASES:
                raise micro.ValueError('use_case_unknown')

            data = _USE_CASES[use_case]
            id = 'List:{}'.format(randstr())
            lst = List(
                id=id, app=self.app, authors=[self.app.user.id], title=data['title'],
                description=None, features=data['features'], mode=data.get('mode', 'collaborate'),
                activity=Activity('{}.activity'.format(id), self.app, subscriber_ids=[]))
            self.app.r.oset(lst.id, lst)
            self.app.r.zadd('{}.users'.format(lst.id), {self.app.user.id.encode(): -time()})
            self.app.r.rpush(self.map_key, lst.id)
            self.app.user.lists.add(lst, user=self.app.user)
            self.app.activity.publish(
                Event.create('create-list', None, {'lst': lst}, app=self.app))
            return lst

        async def create_example(self, use_case):
            """See :http:post:`/api/lists/create-example`."""
            if use_case not in _EXAMPLE_DATA:
                raise micro.ValueError('use_case_unknown')
            data = _EXAMPLE_DATA[use_case]
            description = (
                '{}\n\n*This example was created just for you, so please feel free to play around.*'
                .format(data[1]))

            lst = self.create(use_case, v=2)
            lst.edit(title=data[0], description=description)
            for item in data[2]:
                args = dict(item)
                checked = args.pop('checked', False)
                user_assigned = args.pop('user_assigned', False)
                user_voted = args.pop('user_voted', False)
                item = await lst.items.create(**args)
                if checked:
                    item.check()
                if user_assigned:
                    item.assignees.assign(self.app.user, user=self.app.user)
                if user_voted:
                    item.votes.vote(user=self.app.user)
            return lst

    def __init__(self, redis_url='', email='bot@localhost', smtp_url='',
                 render_email_auth_message=None, *, files_path='data', video_service_keys={}):
        super().__init__(
            redis_url=redis_url, email=email, smtp_url=smtp_url,
            render_email_auth_message=render_email_auth_message, files_path=files_path,
            video_service_keys=video_service_keys)
        self.types.update({'User': User, 'List': List, 'Item': Item})
        self.lists = Listling.Lists((self, 'lists'))

    def do_update(self):
        version = self.r.get('version')
        if not version:
            self.r.set('version', 8)
            return

        version = int(version)
        r = JSONRedis(self.r.r)
        r.caching = False

        # Deprecated since 0.14.0
        if version < 7:
            now = time()
            lists = r.omget(r.lrange('lists', 0, -1))
            for lst in lists:
                r.zadd('{}.lists'.format(lst['authors'][0]), {lst['id']: -now})
            r.set('version', 7)

        # Deprecated since 0.23.0
        if version < 8:
            lists = r.omget(r.lrange('lists', 0, -1))
            for lst in lists:
                users_key = '{}.users'.format(lst['id'])
                self.r.zadd(users_key, {lst['authors'][0].encode(): 0})
                events = r.omget(r.lrange('{}.activity.items'.format(lst['id']), 0, -1))
                for event in reversed(events):
                    t = parse_isotime(event['time'], aware=True).timestamp()
                    self.r.zadd(users_key, {event['user'].encode(): -t})
            r.set('version', 8)

    def create_user(self, data):
        return User(**data)

    def create_settings(self):
        # pylint: disable=unexpected-keyword-arg; decorated
        return Settings(
            id='Settings', app=self, authors=[], title='My Open Listling', icon=None,
            icon_small=None, icon_large=None, provider_name=None, provider_url=None,
            provider_description={}, feedback_url=None, staff=[], push_vapid_private_key=None,
            push_vapid_public_key=None, v=2)

    def file_references(self):
        for lst in self.lists[:]:
            for item in lst.items[:]:
                if item.resource and urlsplit(item.resource.url).scheme == 'file':
                    yield item.resource.url

class User(micro.User):
    """See :ref:`User`."""

    class Lists(Collection):
        """See :ref:`UserLists`."""
        # We use setattr / getattr to work around a Pylint error for Generic classes (see
        # https://github.com/PyCQA/pylint/issues/2443)

        def __init__(self, user):
            super().__init__(RedisSortedSet('{}.lists'.format(user.id), user.app.r), app=user.app)
            setattr(self, 'user', user)

        def add(self, lst, *, user):
            """See: :http:post:`/users/(id)/lists`."""
            if user != getattr(self, 'user'):
                raise micro.PermissionError()
            self.app.r.zadd(self.ids.key, {lst.id: -time()})

        def remove(self, lst, *, user):
            """See :http:delete:`/users/(id)/lists/(list-id)`.

            If *lst* is not in the collection, a :exc:`micro.error.ValueError` is raised.
            """
            if user != getattr(self, 'user'):
                raise micro.PermissionError()
            if lst.authors[0] == getattr(self, 'user'):
                raise micro.ValueError(
                    'user {} is owner of lst {}'.format(getattr(self, 'user').id, lst.id))
            if self.app.r.zrem(self.ids.key, lst.id) == 0:
                raise micro.ValueError(
                    'No lst {} in lists of user {}'.format(lst.id, getattr(self, 'user').id))

        def read(self, *, user):
            """Return collection for reading."""
            if user != getattr(self, 'user'):
                raise micro.PermissionError()
            return self

    def __init__(self, *, app, **data):
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

    _PERMISSIONS = {
        'collaborate': {
            'item-owner': {                                    'item-modify'},
            'user':       {'list-modify', 'list-items-create', 'item-modify'}
        },
        'contribute': {
            'item-owner': {                                    'item-modify'},
            'user': {                     'list-items-create'               }
        },
        'view': {
            'item-owner': set(),
            'user':       set()
        }
    }

    class Items(Collection, Orderable):
        """See :ref:`Items`."""

        async def create(self, title, *, text=None, resource=None, location=None):
            """See :http:post:`/api/lists/(id)/items`."""
            # pylint: disable=protected-access; List is a friend
            self.host[0]._check_permission(self.app.user, 'list-items-create')
            attrs = await WithContent.process_attrs({'text': text, 'resource': resource},
                                                    app=self.app)
            if str_or_none(title) is None:
                raise micro.ValueError('title_empty')

            item = Item(
                id='Item:{}'.format(randstr()), app=self.app, authors=[self.app.user.id],
                trashed=False, text=attrs['text'], resource=attrs['resource'],
                list_id=self.host[0].id, title=title,
                location=location.json() if location else None, checked=False)
            self.app.r.oset(item.id, item)
            self.app.r.rpush(self.map_key, item.id)
            self.host[0].activity.publish(
                Event.create('list-create-item', self.host[0], {'item': item}, self.app))
            return item

        def move(self, item, to):
            # pylint: disable=protected-access; List is a friend
            self.host[0]._check_permission(self.app.user, 'list-modify')
            super().move(item, to)

    def __init__(self, *, id, app, authors, title, description, features, mode, activity):
        super().__init__(id=id, app=app)
        Editable.__init__(self, authors=authors, activity=activity)
        self.title = title
        self.description = description
        self.features = features
        self.mode = mode
        self.items = List.Items((self, 'items'))
        self.activity = activity
        self.activity.post = self._on_activity_publish
        self.activity.host = self

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

    def do_edit(self, **attrs):
        self._check_permission(self.app.user, 'list-modify')
        if 'title' in attrs and str_or_none(attrs['title']) is None:
            raise micro.ValueError('title_empty')
        if ('features' in attrs and
                not set(attrs['features']) <= {'check', 'assign', 'vote', 'location', 'play'}):
            raise micro.ValueError('feature_unknown')
        if 'mode' in attrs and attrs['mode'] not in {'collaborate', 'contribute', 'view'}:
            raise micro.ValueError('Unknown mode')

        if 'title' in attrs:
            self.title = attrs['title']
        if 'description' in attrs:
            self.description = str_or_none(attrs['description'])
        if 'features' in attrs:
            self.features = attrs['features']
        if 'mode' in attrs:
            self.mode = attrs['mode']

    def json(self, restricted=False, include=False, *, rewrite=None):
        return {
            **super().json(restricted=restricted, include=include, rewrite=rewrite),
            **Editable.json(self, restricted=restricted, include=include, rewrite=rewrite),
            'title': self.title,
            'description': self.description,
            'features': self.features,
            'mode': self.mode,
            'activity': self.activity.json(restricted=restricted, rewrite=rewrite),
            **({'items': self.items.json(restricted=restricted, include=include, rewrite=rewrite)}
               if restricted else {}),
        }

    def _check_permission(self, user, op):
        permissions = List._PERMISSIONS[self.mode]
        if not (
            user and (
                op in permissions['user'] or
                user == self.authors[0] or
                user in self.app.settings.staff)):
            raise micro.PermissionError()

    def _on_activity_publish(self, event):
        self.app.r.zadd('{}.users'.format(self.id), {event.user.id.encode(): -time()})

class Item(Object, Editable, Trashable, WithContent):
    """See :ref:`Item`."""

    class Assignees(Collection):
        """See :ref:`ItemAssignees`."""

        def __init__(self, item, *, app):
            super().__init__(RedisSortedSet('{}.assignees'.format(item.id), app.r), app=app)
            self.item = item

        def assign(self, assignee, *, user):
            """See :http:post:`/api/lists/(list-id)/items/(id)/assignees`."""
            # pylint: disable=protected-access; Item is a friend
            self.item._check_permission(user, 'list-modify')
            if 'assign' not in self.item.list.features:
                raise error.ValueError('Disabled item list features assign')
            if self.item.trashed:
                raise error.ValueError('Trashed item')
            if not self.app.r.zadd(self.ids.key, {assignee.id.encode(): -time()}):
                raise error.ValueError(
                    'assignee {} already in assignees of item {}'.format(assignee.id, self.item.id))
            self.item.list.activity.publish(
                Event.create('item-assignees-assign', self.item, detail={'assignee': assignee},
                             app=self.app))

        def unassign(self, assignee, *, user):
            """See :http:delete:`/api/lists/(list-id)/items/(id)/assignees/(assignee-id)`."""
            # pylint: disable=protected-access; Item is a friend
            self.item._check_permission(user, 'list-modify')
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

        def vote(self, *, user):
            """See :http:post:`/api/lists/(list-id)/items/(id)/votes`."""
            if not user:
                raise micro.PermissionError()
            if 'vote' not in self.item.list.features:
                raise error.ValueError('Disabled item list features vote')
            if self.app.r.zadd(self.ids.key, {user.id.encode(): -time()}):
                self.item.list.activity.publish(
                    Event.create('item-votes-vote', self.item, app=self.app))

        def unvote(self, *, user):
            """See :http:delete:`/api/lists/(list-id)/items/(id)/votes/user`."""
            if not user:
                raise micro.PermissionError()
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

    def __init__(self, *, id, app, authors, trashed, text, resource, list_id, title, location,
                 checked):
        super().__init__(id, app)
        Editable.__init__(self, authors, lambda: self.list.activity)
        Trashable.__init__(self, trashed, lambda: self.list.activity)
        WithContent.__init__(self, text=text, resource=resource)
        self._list_id = list_id
        self.title = title
        self.location = Location.parse(location) if location else None
        self.checked = checked
        self.assignees = Item.Assignees(self, app=app)
        self.votes = Item.Votes(self, app=app)

    @property
    def list(self):
        # pylint: disable=missing-docstring; already documented
        return self.app.lists[self._list_id]

    def delete(self):
        self.app.r.lrem(self.list.items.ids.key, 1, self.id.encode())
        self.app.r.delete(self.id)

    def check(self):
        """See :http:post:`/api/lists/(list-id)/items/(id)/check`."""
        _check_feature(self.app.user, 'check', self)
        self._check_permission(self.app.user, 'item-modify')
        self.checked = True
        self.app.r.oset(self.id, self)
        self.list.activity.publish(Event.create('item-check', self, app=self.app))

    def uncheck(self):
        """See :http:post:`/api/lists/(list-id)/items/(id)/uncheck`."""
        _check_feature(self.app.user, 'check', self)
        self._check_permission(self.app.user, 'item-modify')
        self.checked = False
        self.app.r.oset(self.id, self)
        self.list.activity.publish(Event.create('item-uncheck', self, app=self.app))

    async def do_edit(self, **attrs):
        self._check_permission(self.app.user, 'item-modify')
        attrs = await WithContent.pre_edit(self, attrs)
        if 'title' in attrs and str_or_none(attrs['title']) is None:
            raise micro.ValueError('title_empty')

        WithContent.do_edit(self, **attrs)
        if 'title' in attrs:
            self.title = attrs['title']
        if 'location' in attrs:
            self.location = attrs['location']

    def trash(self):
        self._check_permission(self.app.user, 'item-modify')
        super().trash()

    def restore(self):
        self._check_permission(self.app.user, 'item-modify')
        super().restore()

    def json(self, restricted=False, include=False, *, rewrite=None):
        return {
            **super().json(restricted=restricted, include=include, rewrite=rewrite),
            **Editable.json(self, restricted=restricted, include=include, rewrite=rewrite),
            **Trashable.json(self, restricted=restricted, include=include, rewrite=rewrite),
            **WithContent.json(self, restricted=restricted, include=include, rewrite=rewrite),
            'list_id': self._list_id,
            'title': self.title,
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

    def _check_permission(self, user, op):
        lst = self.list
        # pylint: disable=protected-access; List is a friend
        permissions = List._PERMISSIONS[lst.mode]
        if not (
            user and (
                op in permissions['user'] or
                user == self.authors[0] and op in permissions['item-owner'] or
                user == lst.authors[0] or
                user in self.app.settings.staff)):
            raise micro.PermissionError()

def _check_feature(user, feature, item):
    if feature not in item.list.features:
        raise micro.ValueError('feature_disabled')
    if not user:
        raise micro.PermissionError()
