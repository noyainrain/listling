# micro
# Copyright (C) 2020 micro contributors
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

from typing import Dict, List, Optional
from urllib.parse import urljoin

from tornado.httpclient import AsyncHTTPClient, HTTPResponse
from tornado.testing import AsyncTestCase

from .core import Device, RewriteFunc
from .jsonredis import RedisList
from .micro import (Activity, Application, Collection, Editable, Object, Orderable, Settings,
                    Trashable, WithContent)
from .resource import Resource
from .server import Server
from .util import expect_opt_type, expect_type, randstr

class ServerTestCase(AsyncTestCase):
    """Subclass API: Server test case.

    .. attribute:: server

       :class:`server.Server` under test. Must be set by subclass.

    .. attribute:: client_device

       User device for interacting with the server. May be set by subclass.
    """

    def setUp(self) -> None:
        super().setUp()
        self.server: Optional[Server] = None
        self.client_device: Optional[Device] = None

    async def request(self, url: str, *, headers: Dict[str, str] = {},
                      raise_error: bool = True, **args: object) -> HTTPResponse:
        """Run a request against the given *url* path.

        The request is issued by :attr:`client_user`, if set. This is a convenient wrapper around
        :meth:`tornado.httpclient.AsyncHTTPClient.fetch` and keyword arguments are passed through.
        """
        if not self.server:
            raise ValueError('No server')
        if self.client_device:
            headers.update({'Cookie': f'auth_secret={self.client_device.auth_secret}'})
        return await AsyncHTTPClient().fetch(urljoin(self.server.url, url), headers=headers,
                                             raise_error=raise_error, **args)

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

    def __init__(self, redis_url: str = '', *, files_path: str = 'data') -> None:
        super().__init__(redis_url=redis_url, files_path=files_path)
        self.types.update({'Cat': Cat})
        self.cats = self.Cats(app=self)

    def create_settings(self) -> Settings:
        # pylint: disable=unexpected-keyword-arg; decorated
        return Settings(
            id='Settings', app=self, authors=[], title='CatApp', icon=None, icon_small=None,
            icon_large=None, provider_name=None, provider_url=None, provider_description={},
            feedback_url=None, staff=[], push_vapid_private_key='', push_vapid_public_key='')

class Cat(Object, Editable, Trashable, WithContent):
    """Cute cat."""
    # pylint: disable=invalid-overridden-method; do_edit may be async

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

    def json(self, restricted: bool = False, include: bool = False, *,
             rewrite: RewriteFunc = None) -> Dict[str, object]:
        return {
            **super().json(restricted=restricted, include=include, rewrite=rewrite),
            **Editable.json(self, restricted=restricted, include=include, rewrite=rewrite),
            **Trashable.json(self, restricted=restricted, include=include, rewrite=rewrite),
            **WithContent.json(self, restricted=restricted, include=include, rewrite=rewrite),
            'name': self.name,
            'activity': self.activity.json(restricted=restricted, rewrite=rewrite)
        }
