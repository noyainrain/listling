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

"""Open Listling core."""

import micro
from micro import (Activity, Application, Collection, Editable, Object, Orderable, Trashable,
                   Settings, Event)
from micro.jsonredis import JSONRedis
from micro.util import randstr, str_or_none

_USE_CASES = {
    'simple': {'title': 'New list', 'features': []},
    'todo': {'title': 'New to-do list', 'features': ['check']},
    'shopping': {'title': 'New shopping list', 'features': []},
    'meeting-agenda': {'title': 'New meeting agenda', 'features': []}
}

_EXAMPLE_DATA = {
    'todo': (
        'Project tasks',
        'Things we need to do to complete our project.',
        [
            {'title': 'Do research', 'checked': True},
            {'title': 'Create draft'},
            {'title': 'Write report', 'text': 'Summary of the results'}
        ]
    ),
    'shopping': (
        'Kitchen shopping list',
        'When you go shopping next time, please bring the items from this list.',
        [
            {'title': 'Soy sauce'},
            {'title': 'Vegetables', 'text': 'Especially tomatoes'},
            {'title': 'Chocolate (vegan)'}
        ]
    ),
    'meeting-agenda': (
        'Working group agenda',
        'We meet on Monday and discuss important issues.',
        [
            {'title': 'Round of introductions'},
            {'title': 'Lunch poll', 'text': 'What will we have for lunch today?'},
            {'title': 'Next meeting', 'text': 'When and where will our next meeting be?'}
        ]
    )
}

class Listling(Application):
    """See :ref:`Listling`."""

    class Lists(Collection):
        """See :ref:`Lists`."""

        def create(self, use_case=None, description=None, title=None, v=1):
            """See :http:post:`/api/lists`."""
            if v == 1:
                # create(title, description=None)
                title = title or use_case
                if title is None:
                    raise TypeError()
                lst = self.create('simple', v=2)
                lst.edit(title=title, description=description)
                return lst
            if v == 2:
                # create(use_case='simple')
                use_case = use_case or 'simple'
            else:
                raise NotImplementedError()

            if use_case not in _USE_CASES:
                raise micro.ValueError('use_case_unknown')
            data = _USE_CASES[use_case]
            id = 'List:{}'.format(randstr())
            lst = List(
                id, self.app, authors=[self.app.user.id], title=data['title'], description=None,
                features=data['features'],
                activity=Activity('{}.activity'.format(id), self.app, subscriber_ids=[]))
            self.app.r.oset(lst.id, lst)
            self.app.r.rpush(self.map_key, lst.id)
            self.app.activity.publish(
                Event.create('create-list', None, {'lst': lst}, app=self.app))
            return lst

        def create_example(self, use_case):
            """See :http:post:`/api/lists/create-example`."""
            if use_case not in _EXAMPLE_DATA:
                raise micro.ValueError('use_case_unknown')
            data = _EXAMPLE_DATA[use_case]
            description = (
                '{}\n\nThis example was created just for you, so please feel free to play around.'
                .format(data[1]))

            lst = self.create(use_case, v=2)
            lst.edit(title=data[0], description=description)
            for item in data[2]:
                args = dict(item)
                checked = args.pop('checked', False)
                item = lst.items.create(**args)
                if checked:
                    item.check()
            return lst

    def __init__(self, redis_url='', email='bot@localhost', smtp_url='',
                 render_email_auth_message=None):
        super().__init__(redis_url, email, smtp_url, render_email_auth_message)
        self.types.update({'List': List, 'Item': Item})
        self.lists = Listling.Lists((self, 'lists'))

    def do_update(self):
        version = self.r.get('version')
        if not version:
            self.r.set('version', 3)
            return

        version = int(version)
        r = JSONRedis(self.r.r)
        r.caching = False

        # Deprecated since 0.3.0
        if version < 2:
            lists = r.omget(r.lrange('lists', 0, -1))
            for lst in lists:
                lst['features'] = []
                items = r.omget(r.lrange('{}.items'.format(lst['id']), 0, -1))
                for item in items:
                    item['checked'] = False
                r.omset({item['id']: item for item in items})
            r.omset({lst['id']: lst for lst in lists})
            r.set('version', 2)

        # Deprecated since 0.5.0
        if version < 3:
            lists = r.omget(r.lrange('lists', 0, -1))
            for lst in lists:
                lst['activity'] = (
                    Activity('{}.activity'.format(lst['id']), app=self, subscriber_ids=[]).json())
            r.omset({lst['id']: lst for lst in lists})
            r.set('version', 3)

    def create_settings(self):
        # pylint: disable=unexpected-keyword-arg; decorated
        return Settings(
            id='Settings', app=self, authors=[], title='My Open Listling', icon=None,
            icon_small=None, icon_large=None, provider_name=None, provider_url=None,
            provider_description={}, feedback_url=None, staff=[], push_vapid_private_key=None,
            push_vapid_public_key=None, v=2)

class List(Object, Editable):
    """See :ref:`List`."""

    class Items(Collection, Orderable):
        """See :ref:`Items`."""

        def create(self, title, text=None):
            """See :http:post:`/api/lists/(id)/items`."""
            if str_or_none(title) is None:
                raise micro.ValueError('title_empty')
            item = Item(
                id='Item:{}'.format(randstr()), app=self.app, authors=[self.app.user.id],
                trashed=False, list_id=self.host[0].id, title=title, text=str_or_none(text),
                checked=False)
            self.app.r.oset(item.id, item)
            self.app.r.rpush(self.map_key, item.id)
            self.host[0].activity.publish(
                Event.create('list-create-item', self.host[0], {'item': item}, self.app))
            return item

    def __init__(self, id, app, authors, title, description, features, activity):
        super().__init__(id, app)
        Editable.__init__(self, authors, activity)
        self.title = title
        self.description = description
        self.features = features
        self.items = List.Items((self, 'items'))
        self.activity = activity
        self.activity.host = self

    def do_edit(self, **attrs):
        if 'title' in attrs and str_or_none(attrs['title']) is None:
            raise micro.ValueError('title_empty')
        if 'features' in attrs and not set(attrs['features']) <= {'check'}:
            raise micro.ValueError('feature_unknown')
        if 'title' in attrs:
            self.title = attrs['title']
        if 'description' in attrs:
            self.description = str_or_none(attrs['description'])
        if 'features' in attrs:
            self.features = attrs['features']

    def json(self, restricted=False, include=False):
        return {
            **super().json(restricted, include),
            **Editable.json(self, restricted, include),
            'title': self.title,
            'description': self.description,
            'features': self.features,
            'activity': self.activity.json(restricted)
        }

class Item(Object, Editable, Trashable):
    """See :ref:`Item`."""

    def __init__(self, id, app, authors, trashed, list_id, title, text, checked):
        super().__init__(id, app)
        Editable.__init__(self, authors, lambda: self.list.activity)
        Trashable.__init__(self, trashed, lambda: self.list.activity)
        self._list_id = list_id
        self.title = title
        self.text = text
        self.checked = checked

    @property
    def list(self):
        # pylint: disable=missing-docstring; already documented
        return self.app.lists[self._list_id]

    def check(self):
        """See :http:post:`/api/lists/(list-id)/items/(id)/check`."""
        _check_feature(self.app.user, 'check', self)
        self.checked = True
        self.app.r.oset(self.id, self)
        self.list.activity.publish(Event.create('item-check', self, app=self.app))

    def uncheck(self):
        """See :http:post:`/api/lists/(list-id)/items/(id)/uncheck`."""
        _check_feature(self.app.user, 'check', self)
        self.checked = False
        self.app.r.oset(self.id, self)
        self.list.activity.publish(Event.create('item-uncheck', self, app=self.app))

    def do_edit(self, **attrs):
        if 'title' in attrs and str_or_none(attrs['title']) is None:
            raise micro.ValueError('title_empty')
        if 'title' in attrs:
            self.title = attrs['title']
        if 'text' in attrs:
            self.text = str_or_none(attrs['text'])

    def json(self, restricted=False, include=False):
        return {
            **super().json(restricted, include),
            **Editable.json(self, restricted, include),
            **Trashable.json(self, restricted, include),
            'list_id': self._list_id,
            'title': self.title,
            'text': self.text,
            'checked': self.checked
        }

def _check_feature(user, feature, item):
    if feature not in item.list.features:
        raise micro.ValueError('feature_disabled')
    if not user:
        raise PermissionError()
