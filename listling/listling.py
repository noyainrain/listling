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

"""Open Listling core."""

import micro
from micro import Application, Editable, Object, Settings
from micro.jsonredis import JSONRedis, JSONRedisMapping
from micro.util import randstr

EXAMPLE_DATA = {
    'todo': (
        'Project tasks',
        'Things we need to do to complete the project.',
        {'check': 'user'},
        [
            {'title': 'Do research', 'checked': True},
            {'title': 'Build prototype'},
            {'title': 'Write report', 'description': 'Summary of the results'}
        ]
    ),
    'simple': (
        'Some list',
        'Items can be added, removed and edited.',
        {},
        [{'title': 'Item A'}, {'title': 'Item B'}, {'title': 'Item C'}]
    ),
    'shopping': (
        'Kitchen shopping list',
        'When you go shopping next time, please bring the items from this list.',
        {},
        [
            {'title': 'Soy sauce'},
            {'title': 'Vegetables', 'description': 'Especially tomatoes'},
            {'title': 'Chocolate (vegan)'}
        ]
    ),
    'meeting-agenda': (
        'Working group agenda',
        'We meet and discuss important issues.',
        {},
        [
            {'title': 'Round of introductions'},
            {'title': 'Lunch poll', 'description': 'What will we have for lunch today?'},
            {'title': 'Next meeting', 'description': 'When and where will our next meeting be?'}
        ]
    )
}

# micro material
class Trashable:
    def __init__(self, trashed):
        self.trashed = trashed

    def trash(self):
        self.trashed = True
        self.app.r.oset(self.id, self)

    def restore(self):
        self.trashed = False
        self.app.r.oset(self.id, self)

    def json(self, restricted=True, include=False):
        return {trashed: self.trashed}

class Orderable:
    """TODO.

    Mixin for JSONRedisMapping.
    """

    def move(self, item, to):
        """TODO"""
        # Copied from Meetling
        if to:
            if to.id not in self:
                raise micro.ValueError('to_not_found')
            if to == item:
                # No op
                return
        if not self.r.lrem(self.map_key, 1, item.id):
            raise micro.ValueError('item_not_found')
        if to:
            self.r.linsert(self.map_key, 'after', to.id, item.id)
        else:
            self.r.lpush(self.map_key, item.id)

class Container(JSONRedisMapping):
    """
    .. attribute:: count

       Number of items in the container.

    .. attribute:: host

       Host the container is attached to. Tuple (object, attr).

    .. attribute:: attr XXX

       Name of the attribute the container is attached to on the :attr:`host`.
    """

    def __init__(self, count, host):
        self.count = count
        self.host = host
        self.__app = self.host[0].app
        super().__init__(self.__app.r, '{}.{}.items'.format(self.host[0].id, self.host[1]))

    def __len__(self):
        return self.count

    def add(self, item):
        """Subclass API: TODO."""
        self.count += 1
        self.__app.r.rpush(self.map_key, item.id)
        self.__app.r.oset(self.host[0].id, self.host[0])

    def json(self):
        return {'count': self.count}
# /micro---


class Listling(Application):
    """See :ref:`Listling`."""

    class Lists(JSONRedisMapping):
        """TODO."""

        def __init__(self, app):
            self._app = app
            super().__init__(self._app.r, 'lists')

        def create(self, title, description=None, features={}):
            f = {'check': None}
            f.update(features)
            lst = List(
                id='List:{}'.format(randstr()), trashed=False, app=self._app,
                authors=[self._app.user.id], title=title, description=description,
                features=f)
            self._app.r.oset(lst.id, lst)
            self._app.r.rpush(self.map_key, lst.id)
            return lst

        def create_example(self, kind):
            """TODO."""
            if kind not in EXAMPLE_DATA:
                raise micro.ValueError("kind_unknown")
            data = EXAMPLE_DATA[kind]

            description = "{}\n\nThis example was created just for you, so please feel free to play around with it."
            description = description.format(data[1])

            lst = self.create(data[0], description, data[2])
            for item in data[3]:
                lst.items.create(**item)
            return lst

    def __init__(self, redis_url='', email='bot@localhost', smtp_url='',
                 render_email_auth_message=None):
        super().__init__(redis_url, email, smtp_url, render_email_auth_message)
        self.types.update({'List': List, 'Item': Item})
        self.lists = Listling.Lists(self)

    def create_settings(self):
        return Settings(
            id='Settings', trashed=False, app=self, authors=[], title='My Open Listling', icon=None,
            favicon=None, provider_name=None, provider_url=None, provider_description={},
            feedback_url=None, staff=[])

    def do_update(self):
        version = self.r.get('version')

        r = JSONRedis(self.r.r)
        r.caching = False

        if not version:
            lists = r.omget(r.lrange('lists', 0, -1))
            for lst in lists:
                lst['features'] = {}
                items = r.omget(r.lrange('{}.items'.format(lst['id']), 0, -1))
                for item in items:
                    item['checked'] = False
                    item['lst_id'] = lst['id']
                r.omset({i['id']: i for i in items})
            r.omset({l['id']: l for l in lists})
            r.set('version', 1)
            return

class List(Object, Editable):
    """TODO."""

    class Items(JSONRedisMapping, Orderable):
        """TODO."""

        def __init__(self, host):
            self.host = host
            self._app = host.app
            super().__init__(self._app.r, '{}.items'.format(host.id))

        def create(self, title, description=None, checked=False):
            item = Item(
                id='Item:{}'.format(randstr()), trashed=False, app=self._app,
                authors=[self._app.user.id], title=title, description=description,
                checked=checked, lst_id=self.host.id)
            self._app.r.oset(item.id, item)
            self._app.r.rpush(self.map_key, item.id)
            return item

    def __init__(self, id, trashed, app, authors, title, description, features):
        super().__init__(id, trashed, app)
        Editable.__init__(self, authors)
        self.title = title
        self.description = description
        self.features = features
        #self.items = Items(host=(self, 'items'), **items)
        self.items = List.Items(self)

    def do_edit(self, **attrs):
        if 'title' in attrs:
            self.title = attrs['title']
        if 'description' in attrs:
            self.description = attrs['description']

    def json(self, restricted=False, include=False):
        return {**super().json(restricted, include), **Editable.json(self, restricted, include),
                'title': self.title, 'description': self.description, 'features': self.features} #, 'items': self.items.json()}

class Item(Object, Editable, Trashable):
    def __init__(self, id, trashed, app, authors, title, description, checked, lst_id):
        super().__init__(id, trashed, app)
        Editable.__init__(self, authors)
        Trashable.__init__(self, trashed)
        self.title = title
        self.description = description
        self.checked = checked
        self._lst_id = lst_id

    @property
    def lst(self):
        return self.app.lists[self._lst_id]

    def check(self):
        if not self.lst.features['check']:
            raise ValueError('check_disabled')
        #self.list.features['check'] == 'user'
        #self.list.features['check'] == 'item_owner' and self.app.user.id in [*self.owners, *self.list._owners, *self.app.settings.staff]
        #self.list.features['check'] == 'list_owner' and self.app.user.id in [*self.list.owners, *self.app.settings.staff]
        self.checked = True
        self.app.r.oset(self.id, self)

    def uncheck(self):
        if not self.lst.features['check']:
            raise ValueError('check_disabled')
        self.checked = False
        self.app.r.oset(self.id, self)

    def do_edit(self, **attrs):
        if 'title' in attrs:
            self.title = attrs['title']
        if 'description' in attrs:
            self.description = attrs['description']

    def json(self, restricted=False, include=False):
        return {**super().json(restricted, include), **Editable.json(self, restricted, include),
                'title': self.title, 'description': self.description, 'checked': self.checked,
                'lst_id': self._lst_id}
