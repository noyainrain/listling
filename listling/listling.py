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
from micro import Application, Collection, Editable, Object, Orderable, Trashable, Settings, Event
from micro.util import randstr, str_or_none

_EXAMPLE_DATA = {
    'shopping': (
        'Kitchen shopping list',
        'When you go shopping next time, please bring the items from this list.',
        [('Soy sauce', None), ('Vegetables', 'Especially tomatoes'), ('Chocolate (vegan)', None)]
    ),
    'meeting-agenda': (
        'Working group agenda',
        'We meet on Monday and discuss important issues.',
        [
            ('Round of introductions', None),
            ('Lunch poll', 'What will we have for lunch today?'),
            ('Next meeting', 'When and where will our next meeting be?')
        ]
    )
}

class Listling(Application):
    """See :ref:`Listling`."""

    class Lists(Collection):
        """See :ref:`Lists`."""

        def create(self, title, description=None):
            """See :http:post:`/api/lists`."""
            if str_or_none(title) is None:
                raise micro.ValueError('title_empty')
            lst = List(id='List:{}'.format(randstr()), app=self.app, authors=[self.app.user.id],
                       title=title, description=str_or_none(description))
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
            lst = self.create(data[0], description)
            for item in data[2]:
                lst.items.create(item[0], item[1])
            return lst

    def __init__(self, redis_url='', email='bot@localhost', smtp_url='',
                 render_email_auth_message=None):
        super().__init__(redis_url, email, smtp_url, render_email_auth_message)
        self.types.update({'List': List, 'Item': Item})
        self.lists = Listling.Lists((self, 'lists'))

    def do_update(self):
        version = self.r.get('version')
        if not version:
            self.r.set('version', 1)

    def create_settings(self):
        return Settings(
            id='Settings', app=self, authors=[], title='My Open Listling', icon=None, favicon=None,
            provider_name=None, provider_url=None, provider_description={}, feedback_url=None,
            staff=[])

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
                trashed=False, list_id=self.host[0].id, title=title, text=str_or_none(text))
            self.app.r.oset(item.id, item)
            self.app.r.rpush(self.map_key, item.id)
            return item

    def __init__(self, id, app, authors, title, description):
        super().__init__(id, app)
        Editable.__init__(self, authors)
        self.title = title
        self.description = description
        self.items = List.Items((self, 'items'))

    def do_edit(self, **attrs):
        if 'title' in attrs and str_or_none(attrs['title']) is None:
            raise micro.ValueError('title_empty')
        if 'title' in attrs:
            self.title = attrs['title']
        if 'description' in attrs:
            self.description = str_or_none(attrs['description'])

    def json(self, restricted=False, include=False):
        return {**super().json(restricted, include), **Editable.json(self, restricted, include),
                'title': self.title, 'description': self.description}

class Item(Object, Editable, Trashable):
    """See :ref:`Item`."""

    def __init__(self, id, app, authors, trashed, list_id, title, text):
        super().__init__(id, app)
        Editable.__init__(self, authors)
        Trashable.__init__(self, trashed)
        self._list_id = list_id
        self.title = title
        self.text = text

    @property
    def list(self):
        # pylint: disable=missing-docstring; already documented
        return self.app.lists[self._list_id]

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
            'text': self.text
        }
