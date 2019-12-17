# micro
# Copyright (C) 2018 micro contributors
#
# This program is free software: you can redistribute it and/or modify it under the terms of the GNU
# Lesser General Public License as published by the Free Software Foundation, either version 3 of
# the License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without
# even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public License along with this program.
# If not, see <http://www.gnu.org/licenses/>.

"""Test utilites."""

from typing import List, Optional
from urllib.parse import urljoin

from tornado.httpclient import AsyncHTTPClient
from tornado.testing import AsyncTestCase

from .jsonredis import JSONRedis, RedisList
from .micro import (Activity, Application, Collection, Editable, Object, Orderable, Settings,
                    Trashable, WithContent)
from .resource import Resource
from .util import expect_opt_type, expect_type, randstr

class ServerTestCase(AsyncTestCase):
    """Subclass API: Server test case.

    .. attribute:: server

       :class:`server.Server` under test. Must be set by subclass.

    .. attribute:: client_user

       :class:`User` interacting with the server. May be set by subclass.
    """

    def setUp(self):
        super().setUp()
        self.server = None
        self.client_user = None

    def request(self, url, **args):
        """Run a request against the given *url* path.

        The request is issued by :attr:`client_user`, if set. This is a convenient wrapper around
        :meth:`tornado.httpclient.AsyncHTTPClient.fetch` and *args* are passed through.
        """
        headers = args.pop('headers', {})
        if self.client_user:
            headers.update({'Cookie': 'auth_secret=' + self.client_user.auth_secret})
        return AsyncHTTPClient().fetch(urljoin(self.server.url, url), headers=headers, **args)

class CatApp(Application):
    """Simple application for testing purposes.

    .. attribute:: cats

       See :class:`CatApp.Cats`.
    """

    class Cats(Collection['Cat'], Orderable):
        """Collection of all :class:`Cat`s."""

        def __init__(self, *, app: Application) -> None:
            super().__init__(RedisList('cats', app.r.r), expect=expect_type(Cat), app=app)
            Orderable.__init__(self)

        def create(self, name: str = None) -> 'Cat':
            """Create a cat."""
            cat = Cat.make(name=name, app=self.app)
            self.app.r.oset(cat.id, cat)
            self.app.r.rpush('cats', cat.id)
            return cat

    def __init__(self, redis_url: str = '') -> None:
        super().__init__(redis_url=redis_url)
        self.types.update({'Cat': Cat})
        self.cats = self.Cats(app=self)

    def do_update(self):
        r = JSONRedis(self.r.r)
        r.caching = False

        cats = r.omget(r.lrange('cats', 0, -1))
        for cat in cats:
            # Deprecated since 0.14.0
            if 'activity' not in cat:
                cat['activity'] = Activity(
                    '{}.activity'.format(cat['id']), app=self, subscriber_ids=[]).json()
            # Deprecated since 0.27.0
            if 'text' not in cat:
                cat['text'] = None
                cat['resource'] = None
        r.omset({cat['id']: cat for cat in cats})

    def create_settings(self) -> Settings:
        # pylint: disable=unexpected-keyword-arg; decorated
        return Settings(
            id='Settings', app=self, authors=[], title='CatApp', icon=None, icon_small=None,
            icon_large=None, provider_name=None, provider_url=None, provider_description={},
            feedback_url=None, staff=[], push_vapid_private_key=None, push_vapid_public_key=None,
            v=2)

    def sample(self):
        """Set up some sample data."""
        user = self.login()
        auth_request = user.set_email('happy@example.org')
        self.r.set('auth_request', auth_request.id)

class Cat(Object, Editable, Trashable, WithContent):
    """Cute cat."""

    app = None # type: CatApp

    @staticmethod
    def make(*, name: str = None, app: Application) -> 'Cat':
        """Create a :class:`Cat` object."""
        id = 'Cat:{}'.format(randstr())
        return Cat(id=id, app=app, authors=[], trashed=False, text=None, resource=None, name=name,
                   activity=Activity(id='{}.activity'.format(id), app=app, subscriber_ids=[]))

    def __init__(
            self, *, id: str, app: Application, authors: List[str], trashed: bool,
            text: Optional[str], resource: Optional[Resource], name: Optional[str],
            activity: Activity) -> None:
        super().__init__(id, app)
        Editable.__init__(self, authors, activity)
        Trashable.__init__(self, trashed, activity)
        WithContent.__init__(self, text=text, resource=resource)
        self.name = name
        self.activity = activity
        self.activity.host = self

    def delete(self) -> None:
        self.app.r.r.lrem(self.app.cats.ids.key, 1, self.id.encode())
        self.app.r.r.delete(self.id)

    async def do_edit(self, **attrs: object) -> None:
        attrs = await WithContent.pre_edit(self, attrs)
        WithContent.do_edit(self, **attrs)
        if 'name' in attrs:
            self.name = expect_opt_type(str)(attrs['name'])

    def json(self, restricted=False, include=False):
        return {
            **super().json(restricted, include),
            **Editable.json(self, restricted, include),
            **Trashable.json(self, restricted, include),
            **WithContent.json(self, restricted, include),
            'name': self.name,
            'activity': self.activity.json(restricted)
        }
