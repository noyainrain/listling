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

"""Core parts of micro.

.. data: RewriteFunc

   Function of the form ``rewrite(url)`` which rewrites the given *url*.
"""

from __future__ import annotations

from contextvars import ContextVar
from datetime import timedelta
import json
import typing
from typing import Callable, Dict, Optional, cast

from . import error
from .jsonredis import script
from .util import expect_type, randstr

if typing.TYPE_CHECKING:
    from micro import Application, User

RewriteFunc = Callable[[str], str]

class context:
    """Application context.

    .. attribute:: user

       Current user. ``None`` means anonymous access.

    .. attribute:: device

       Current user device. ``None`` means anonymous access.

    .. attribute:: client

       Identifier of the current client, e.g. a network address.
    """
    # pylint: disable=invalid-name; namespace

    user: ContextVar[Optional['User']] = ContextVar('user', default=None)
    device: ContextVar[Optional['Device']] = ContextVar('device', default=None)
    client = ContextVar('client', default='local')

class Object:
    """Object in the application universe.

    .. attribute:: app

       Context :class:`Application`.
    """

    def __init__(self, id: str, app: 'Application') -> None:
        self.id = id
        self.app = app

    def json(self, restricted: bool = False, include: bool = False, *,
             rewrite: RewriteFunc = None) -> Dict[str, object]:
        """See :meth:`JSONifiable.json`.

        Subclass API: May be overridden by subclass. The default implementation returns the
        attributes of :class:`Object`. *restricted* and *include* are ignored.
        """
        # pylint: disable=unused-argument; part of subclass API
        return {'__type__': type(self).__name__, 'id': self.id}

    def __repr__(self):
        return '<{}>'.format(self.id)

class Device(Object):
    """See :ref:`Device`."""

    def __init__(self, *, app: 'Application', **data: object) -> None:
        super().__init__(id=cast(str, data['id']), app=app)
        self.auth_secret = cast(str, data['auth_secret'])
        self.notification_status = cast(str, data['notification_status'])
        self.push_subscription = cast(Optional[str], data['push_subscription'])
        self.user_id = cast(str, data['user_id'])

    @property
    def user(self) -> 'User':
        # pylint: disable=missing-function-docstring; already documented
        return self.app.users[self.user_id]

    async def enable_notifications(self, push_subscription: str, *,
                                   _event_type: str ='device-enable-notifications') -> None:
        """See :http:patch:`/api/devices/(id)` (``enable_notifications``)."""
        # Compatibility with User device actions (deprecated since 0.58.0)
        user = context.user.get()
        if not (user and user.id == self.user_id):
            raise error.PermissionError()
        # pylint: disable=import-outside-toplevel; circular dependency
        from .micro import Event
        await self.app.send_device_notification(push_subscription,
                                                Event.create(_event_type, self, app=self.app))
        self.notification_status = 'on'
        self.push_subscription = push_subscription
        self.app.r.oset(self.id, self)

    def disable_notifications(self) -> None:
        """See :http:patch:`/api/devices/(id)` (``disable_notifications``)."""
        user = context.user.get()
        if not (user and user.id == self.user_id):
            raise error.PermissionError()
        self.notification_status = 'off'
        self.push_subscription = None
        self.app.r.oset(self.id, self)

    def abort_notifications(self) -> None:
        """Disable notifications because *push_subscription* expired."""
        self.notification_status = 'off.expired'
        self.push_subscription = None
        self.app.r.oset(self.id, self)

    def json(self, restricted: bool = False, include: bool = False, *,
             rewrite: RewriteFunc = None) -> Dict[str, object]:
        return {
            **super().json(restricted=restricted, include=include, rewrite=rewrite),
            'auth_secret': self.auth_secret,
            'notification_status': self.notification_status,
            'push_subscription': self.push_subscription,
            'user_id': self.user_id,
            **({'user': self.user.json(restricted=restricted, rewrite=rewrite)} if include else {})
        }

class Devices:
    """See :ref:`Devices`."""

    def __init__(self, app: 'Application') -> None:
        self.app = app

    def __getitem__(self, key: str) -> Device:
        if not key.startswith('Device:'):
            raise KeyError(key)
        device = self.app.r.oget(key, default=KeyError, expect=expect_type(Device))
        user = context.user.get()
        if not (user and user.id == device.user_id):
            raise error.PermissionError()
        return device

    def authenticate(self, secret: str) -> Device:
        """Authenticate a user :cls:`Device` with *secret* and return it.

        The device owner is set as current :attr:`Application.user`. If the authentication fails, an
        :exc:`error.AuthenticationError` is raised.
        """
        id = self.app.r.r.hget('auth_secret_map', secret.encode())
        if not id:
            raise error.AuthenticationError()
        device = self.app.r.oget(id.decode(), default=AssertionError, expect=expect_type(Device))
        user = device.user
        self.app.user = user

        now = self.app.now()
        if now - user.authenticate_time >= timedelta(hours=1):
            user.authenticate_time = now
            self.app.r.oset(user.id, user)
            self.app.r.zadd(user.devices.ids.key, {device.id: -now.timestamp()}, xx=True)
        return device

    def sign_in(self) -> Device:
        """See :http:post:`/api/devices`."""
        id = 'User:' + randstr()
        now = self.app.now()
        user = self.app.create_user({
            'id': id,
            'app': self.app,
            'authors': [id],
            'name': 'Guest',
            'email': None,
            'create_time': now.isoformat(),
            'authenticate_time': now.isoformat()
        })
        self.app.r.oset(user.id, user)
        self.app.r.rpush('users', user.id)

        device = Device(
            id=f'Device:{randstr()}', app=self.app, auth_secret=randstr(),
            notification_status='off', push_subscription=None, user_id=user.id)
        f = script(self.app.r.r, """
            local device_data, now = ARGV[1], ARGV[2]
            local device = cjson.decode(device_data)
            redis.call("SET", device.id, device_data)
            redis.call("SADD", "devices", device.id)
            redis.call("ZADD", device.user_id .. ".devices", -now, device.id)
            redis.call("HSET", "auth_secret_map", device.auth_secret, device.id)
        """)
        f([], [json.dumps(device.json()), now.timestamp()])

        # Promote first user to staff
        if len(self.app.users) == 1:
            settings = self.app.settings
            # pylint: disable=protected-access; Settings is a friend
            settings._staff = [user.id]
            self.app.r.oset(settings.id, settings)

        return self.authenticate(device.auth_secret)
