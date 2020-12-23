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

"""Core parts of micro."""

from __future__ import annotations

from asyncio import (CancelledError, Task, Queue, # pylint: disable=unused-import; typing
                     create_task, ensure_future, get_event_loop, shield, sleep)
import builtins
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from functools import partial
from inspect import isawaitable
import json
from logging import getLogger
from pathlib import Path
import re
from smtplib import SMTP
import string
import sys
from typing import (AsyncIterator, Awaitable, Callable, Coroutine, Dict, Generic, Iterator, List,
                    Optional, Set, Sequence, Tuple, Type, TypeVar, Union, cast, overload)
from urllib.parse import SplitResult, urlparse, urlsplit

from pywebpush import WebPusher, WebPushException
from py_vapid import Vapid
from py_vapid.utils import b64urlencode
from redis import StrictRedis
from redis.exceptions import ResponseError
from requests.exceptions import RequestException
from typing_extensions import Protocol

from . import error
from .core import Device, Devices, Object, RewriteFunc, context
from .error import ValueError
from .jsonredis import (ExpectFunc, JSONRedis, JSONRedisSequence, RedisList, RedisSequence,
                        RedisSortedSet, bzpoptimed)
from .ratelimit import RateLimit, RateLimiter
from .resource import ( # pylint: disable=unused-import; typing
    Analyzer, Files, HandleResourceFunc, Image, Resource, Video, handle_image, handle_webpage,
    handle_youtube)
from .util import (Expect, check_email, expect_opt_type, expect_type, parse_isotime, randstr,
                   str_or_none)
from .webapi import CommunicationError

_PUSH_TTL = 24 * 60 * 60

O = TypeVar('O', bound='Object')

class JSONifiable(Protocol):
    """Object which can be encoded to and decoded from a JSON representation."""

    def __init__(self, **kwargs: object) -> None:
        # pylint: disable=super-init-not-called; protocol
        pass

    def json(self, restricted: bool = False, include: bool = False, *,
             rewrite: RewriteFunc = None) -> Dict[str, object]:
        """Return a JSON representation of the object.

        The name of the object type is included as ``__type__``.

        By default, all attributes are included. If *restricted* is ``True``, a restricted view of
        the object is returned, i.e. attributes that should not be available to the current
        :attr:`Application.user` are excluded. If *include* is ``True``, additional fields that may
        be of interest to the caller are included. If *rewrite* is given, it is applied to all URL
        attributes.
        """

class JSONifiableWithParse(JSONifiable, Protocol):
    # pylint: disable=missing-docstring; semi-public

    @staticmethod
    def parse(data: Dict[str, object], **args: object) -> JSONifiable:
        """Parse the given JSON *data* into an object.

        Additional keyword arguments *args* are passed to the constructor.
        """

class Application:
    """Social micro web app.

    .. attribute:: user

       Current :class:`User`. ``None`` means anonymous access.

    .. attribute:: users

       Collection of all :class:`User`s.

    .. attribute:: analytics

       Analytics unit.

    .. attribute:: redis_url

       See ``--redis-url`` command line option.

    .. attribute:: email

       Sender email address to use for outgoing email. Defaults to ``bot@localhost``.

    .. attribute:: smtp_url

       See ``--smtp-url`` command line option.

    .. attribute:: render_email_auth_message

       Hook function of the form *render_email_auth_message(email, auth_request, auth)*, responsible
       for rendering an email message for the authentication request *auth_request*. *email* is the
       email address to authenticate and *auth* is the secret authentication code.

    .. attribute:: video_service_keys

       See ``--video-service-keys`` command line option.

    .. attribute:: r

       :class:`Redis` database. More precisely a :class:`JSONRedis` instance.

    .. attribute:: files

       File storage. *files_path* is the directory where files are stored (see ``--files-path``
       command line option).

    .. attribute:: analyzer

       Web resource analyzer.

    .. attribute:: rate_limiter

       Subclass API: Mechanism to limit the rate of operations per client.
    """

    def __init__(
            self, redis_url: str = '', email: str = 'bot@localhost', smtp_url: str = '',
            render_email_auth_message: Callable[[str, 'AuthRequest', str], str] = None, *,
            files_path: str = 'data', video_service_keys: Dict[str, str] = {}) -> None:
        check_email(email)
        try:
            # pylint: disable=pointless-statement; port errors are only triggered on access
            urlparse(smtp_url).port
        except builtins.ValueError as e:
            raise ValueError('smtp_url_invalid') from e

        self.redis_url = redis_url
        try:
            urlparts = urlsplit(self.redis_url)
            url = SplitResult(
                urlparts.scheme or 'redis', urlparts.netloc or 'localhost', urlparts.path,
                urlparts.query, urlparts.fragment
            ).geturl()
            self.r = JSONRedis(StrictRedis.from_url(url), self._encode, self._decode)
        except builtins.ValueError as e:
            raise ValueError('redis_url_invalid') from e
        self.files = Files(files_path)

        # pylint: disable=import-outside-toplevel; circular dependency
        from .analytics import Analytics, Referral
        self.types = {
            'User': User,
            'Device': Device,
            'Settings': Settings,
            'Activity': Activity,
            'Event': Event,
            'AuthRequest': AuthRequest,
            'Resource': Resource,
            'Image': Image,
            'Video': Video,
            'Referral': Referral
        } # type: Dict[str, Type[JSONifiable]]
        self.user = None # type: Optional[User]
        self.users = Users(self)
        self.devices = Devices(self)
        self.analytics = Analytics(app=self)

        self.email = email
        self.smtp_url = smtp_url
        self.render_email_auth_message = render_email_auth_message

        self.video_service_keys = video_service_keys
        handlers = [handle_image, handle_webpage] # type: List[HandleResourceFunc]
        if 'youtube' in self.video_service_keys:
            handlers.insert(0, handle_youtube(self.video_service_keys['youtube']))
        self.analyzer = Analyzer(handlers=handlers, files=self.files)
        self.rate_limiter = RateLimiter()

    @property
    def settings(self) -> 'Settings':
        """App :class:`Settings`."""
        return self.r.oget('Settings', default=AssertionError, expect=expect_type(Settings))

    @property
    def activity(self) -> 'Activity':
        """Global :class:`Activity` feed."""
        activity = self.r.oget('Activity', default=AssertionError, expect=expect_type(Activity))
        activity.pre = self.check_user_is_staff
        return activity

    @staticmethod
    def now() -> datetime:
        """Return the current UTC date and time, as aware object with second accuracy."""
        return datetime.now(timezone.utc).replace(microsecond=0)

    def update(self) -> None:
        """Update the database.

        If the database is fresh, it will be initialized. If the database is already up-to-date,
        nothing will be done. It is thus safe to call :meth:`update` without knowing if an update is
        necessary or not.
        """
        Path(self.files.path).mkdir(parents=True, exist_ok=True)

        v = cast(Optional[bytes], self.r.get('micro_version'))
        # If fresh, initialize database
        if not v:
            settings = self.create_settings()
            settings.push_vapid_private_key, settings.push_vapid_public_key = (
                self._generate_push_vapid_keys()) # type: ignore
            self.r.oset(settings.id, settings)
            activity = Activity(id='Activity', app=self, subscriber_ids=[])
            self.r.oset(activity.id, activity)
            self.r.set('micro_version', 9)
            self.do_update()
            return

        v = int(v)
        r = JSONRedis[Dict[str, object]](self.r.r)
        r.caching = False

        # Deprecated since 0.39.0
        if v < 9:
            user_activity: Dict[str, Tuple[datetime, datetime]] = {}
            for event in self._scan_objects(r, Event):
                user_id = cast(str, event['user'])
                t = parse_isotime(cast(str, event['time']))
                first, last = user_activity.get(user_id) or (t, t)
                user_activity[user_id] = (min(first, t), max(last, t))

            now = self.now()
            users = r.omget([id.decode() for id in r.r.lrange('users', 0, -1)],
                            default=AssertionError)
            for user in users:
                first, last = user_activity.get(cast(str, user['id'])) or (now, now)
                user['create_time'] = first.isoformat()
                user['authenticate_time'] = last.isoformat()
            r.omset({cast(str, user['id']): user for user in users})
            r.set('micro_version', 9)

        user_updates = {}
        device_updates = {}
        users = r.omget([id.decode() for id in r.r.lrange('users', 0, -1)], default=AssertionError)
        for user in users:
            # Deprecated since 0.58.0
            if 'auth_secret' in user:
                device = Device(
                    id=f'Device:{randstr()}', app=self, auth_secret=user.pop('auth_secret'),
                    notification_status=user.pop('device_notification_status'),
                    push_subscription=user.pop('push_subscription'), user_id=user['id'])
                r.sadd('devices', device.id)
                authenticate_time = parse_isotime(cast(str, user['authenticate_time']))
                r.zadd(f"{user['id']}.devices", {device.id: -authenticate_time.timestamp()})
                r.hset('auth_secret_map', device.auth_secret, device.id)
                user_updates[cast(str, user['id'])] = user
                device_updates[device.id] = device.json()
        r.omset(user_updates)
        r.omset(device_updates)

        updates = {'User': len(user_updates), 'Device': len(device_updates), **self.do_update()}
        getLogger(__name__).info('Updated database\n%s',
                                 '\n'.join(f'{name}: {n}' for name, n in updates.items()))

    def do_update(self) -> Dict[str, int]:
        """Subclass API: Perform the database update.

        Information about the update, more precisely the number of entity updates by type, is
        returned.

        May be overridden by subclass. Called by :meth:`update`, which takes care of updating (or
        initializing) micro specific data. The default implementation does nothing.
        """
        # pylint: disable=no-self-use; part of subclass API
        return {}

    def create_user(self, data: Dict[str, object]) -> 'User':
        """Subclass API: Create a new user.

        *data* is the JSON data required for :class:`User`.

        May be overridden by subclass. Called by :meth:`login` for new users, which takes care of
        storing the object. By default, a standard :class:`User` is returned.
        """
        # pylint: disable=no-self-use; part of subclass API
        return User(**data) # type: ignore

    def create_settings(self) -> 'Settings':
        """Subclass API: Create and return the app :class:`Settings`.

        *id* must be set to ``Settings``.

        Must be overridden by subclass. Called by :meth:`update` when initializing the database.
        """
        raise NotImplementedError()

    def login(self, code: str = None) -> 'User':
        """See :http:post:`/api/login`.

        The logged-in user is set as current *user*.
        """
        # Compatibility for login (deprecated since 0.58.0)
        if code:
            id = self.r.r.hget('auth_secret_map', code.encode())
            if not id:
                raise ValueError('code_invalid')
            device = self.r.oget(id.decode(), default=AssertionError, expect=expect_type(Device))
            return self.devices.authenticate(device.auth_secret).user
        return self.devices.sign_in().user

    def get_object(self, id, default=KeyError):
        """Get the :class:`Object` given by *id*.

        *default* is the value to return if no object with *id* is found. If it is an
        :exc:`Exception`, it is raised instead.
        """
        object = self.r.oget(id)
        if object is None:
            object = default
        if isinstance(object, Exception):
            raise object
        return object

    def check_user_is_staff(self) -> None:
        """Check if the current :attr:`user` is a staff member."""
        # pylint: disable=protected-access; Settings is a friend
        if not (self.user and self.user.id in self.settings._staff): # type: ignore
            raise error.PermissionError()

    def start_garbage_collect_files(self) -> 'Task[None]':
        """Start the :attr:`files` garbage collect job."""
        async def _run() -> None:
            t = self.now().replace(hour=0, minute=5, second=0)
            while True:
                t += timedelta(days=1)
                await sleep((t - self.now()).total_seconds())
                n = await self.files.garbage_collect(list(self.file_references()))
                getLogger(__name__).info('Garbage collected %d file(s)', n)
        return cast('Task[None]', get_event_loop().create_task(_run()))

    def start_empty_trash(self) -> 'Task[None]':
        """Start the empty trash job."""
        async def _empty_trash() -> None:
            loop = get_event_loop()
            while True:
                coro = cast(
                    Awaitable[Tuple[bytes, float]],
                    loop.run_in_executor(None, partial(bzpoptimed, self.r.r, 'micro_trash')))
                try:
                    id, _ = await shield(coro)
                except CancelledError:
                    # Note that we assume there is only a single consumer of micro_trash
                    self.r.r.zadd('micro_trash', {b'int': 0})
                    await coro
                    raise

                obj = self.r.oget(id.decode(), default=AssertionError,
                                  expect=expect_type(Trashable))
                # pylint: disable=broad-except; catch unhandled exceptions
                try:
                    obj.delete()
                except Exception as e:
                    t = (
                        datetime.now(timezone.utc) + Trashable.RETENTION).timestamp() # type: ignore
                    self.r.r.zadd('micro_trash', {id: t})
                    loop.call_exception_handler(
                        cast(Dict[str, object], {
                            'message': 'Unexpected exception in delete()',
                            'exception': e
                        }))
                del obj
        return cast('Task[None]', ensure_future(_empty_trash()))

    def file_references(self) -> Iterator[str]:
        """Subclass API: Iterate over all file references.

        Called by the :attr:`files` garbage collect job. The default implementation returns an empty
        iterator.
        """
        # pylint: disable=no-self-use; part of API
        return iter(())

    async def send_device_notification(self, push_subscription: str, event: Event) -> None:
        """Send an *event* notification to the device with *push_subscription*.

        If there is a communication issue, a :exc:`micro.error.CommunicationError` is raised.
        """
        try:
            push_subscription = json.loads(push_subscription)
            if not isinstance(push_subscription, dict):
                raise builtins.ValueError()
            urlparts = urlparse(push_subscription['endpoint'])
            pusher = WebPusher(push_subscription)
        except (builtins.ValueError, KeyError, WebPushException) as e:
            raise ValueError('push_subscription_invalid') from e

        # Unfortunately sign() tries to validate the email address
        email = 'bot@email.localhost' if self.email == 'bot@localhost' else self.email
        headers = Vapid.from_raw(self.settings.push_vapid_private_key.encode()).sign({
            'aud': '{}://{}'.format(urlparts.scheme, urlparts.netloc),
            'sub': 'mailto:{}'.format(email)
        })

        try:
            # Firefox does not yet support aes128gcm encoding (see
            # https://bugzilla.mozilla.org/show_bug.cgi?id=1525872)
            send = partial(pusher.send, json.dumps(event.json(restricted=True, include=True)),
                           headers=headers, ttl=_PUSH_TTL, content_encoding='aesgcm')
            response = await get_event_loop().run_in_executor(None, send)
        except RequestException as e:
            raise CommunicationError(f"{e} for POST {push_subscription['endpoint']}") from e
        if response.status_code in (404, 410):
            raise ValueError('push_subscription_invalid')
        if response.status_code != 201:
            raise CommunicationError(
                'Unexpected response status {} for POST {}'.format(response.status_code,
                                                                   push_subscription['endpoint']))

    @staticmethod
    def _encode(object: JSONifiable) -> Dict[str, object]:
        return object.json()

    def _decode(self, json: Dict[str, object]) -> Union[JSONifiable, Dict[str, object]]:
        # pylint: disable=redefined-outer-name; good name
        try:
            type = self.types[str(json['__type__'])]
        except KeyError:
            return json
        if hasattr(type, 'parse'):
            return cast(JSONifiableWithParse, type).parse(json, app=self)
        del json['__type__']
        return type(app=self, **json)

    def _scan_objects(self, r: JSONRedis[Dict[str, object]],
                      cls: 'Type[Object]' = None) -> Iterator[Dict[str, object]]:
        for key in cast(List[bytes], r.keys('*')):
            try:
                obj = r.oget(key.decode(), default=AssertionError)
            except ResponseError:
                pass
            else:
                if ('__type__' in obj and
                        issubclass(self.types[expect_type(str)(obj['__type__'])], cls or Object)):
                    yield obj

    @staticmethod
    def _generate_push_vapid_keys():
        vapid = Vapid()
        vapid.generate_keys()
        return (b64urlencode(vapid.private_key.private_numbers().private_value.to_bytes(32, 'big')),
                b64urlencode(vapid.public_key.public_numbers().encode_point()))

class Gone:
    """See :ref:`Gone`."""

    def json(self, restricted: bool = False, include: bool = False, *,
             rewrite: RewriteFunc = None) -> Dict[str, object]:
        """See :meth:`JSONifiable.json`."""
        # pylint: disable=unused-argument; part of API
        return {'__type__': type(self).__name__}

class Editable:
    """:class:`Object` that can be edited."""

    id = None # type: str
    app = None # type: Application
    trashed = None # type: bool

    def __init__(self, authors: List[str],
                 activity: Union['Activity', Callable[[], 'Activity']] = None) -> None:
        self._authors = authors
        self.__activity = activity

    @property
    def authors(self) -> List['User']:
        # pylint: disable=missing-docstring; already documented
        return self.app.r.omget(self._authors, default=AssertionError, expect=expect_type(User))

    async def edit(self, **attrs: object) -> None:
        """See :http:post:`/api/(object-url)`."""
        if not self.app.user:
            raise error.PermissionError()
        if isinstance(self, Trashable) and self.trashed:
            raise ValueError('object_trashed')

        coro = self.do_edit(**attrs)
        if isawaitable(coro):
            await cast(Awaitable[None], coro)
        if not self.app.user.id in self._authors:
            self._authors.append(self.app.user.id)
        self.app.r.oset(self.id, self)

        if self.__activity is not None:
            activity = self.__activity() if callable(self.__activity) else self.__activity
            activity.publish(Event.create('editable-edit', self, app=self.app)) # type: ignore

    def do_edit(self, **attrs: object) -> Optional[Awaitable[None]]:
        """Subclass API: Perform the edit operation.

        More precisely, validate and then set the given *attrs*.

        Must be overridden by host. Called by :meth:`edit`, which takes care of basic permission
        checking, managing *authors* and storing the updated object in the database.
        """
        raise NotImplementedError()

    def json(self, restricted: bool = False, include: bool = False, *,
             rewrite: RewriteFunc = None) -> Dict[str, object]:
        """Subclass API: Return a JSON object representation of the editable part of the object."""
        return {
            'authors': [a.json(restricted=restricted, rewrite=rewrite) for a in self.authors]
                       if include else self._authors
        }

class Trashable:
    """Mixin for :class:`Object` which can be trashed and restored.

    .. attribute:: RETENTION

       Duration after a trashed object will permanently be deleted.
    """

    RETENTION = timedelta(days=7)

    id = None # type: str
    app = None # type: Application

    def __init__(self, trashed: bool,
                 activity: Union['Activity', Callable[[], 'Activity']] = None) -> None:
        self.trashed = trashed
        self.__activity = activity

    def delete(self) -> None:
        """Subclass API: Permanently delete the object."""
        raise NotImplementedError()

    def trash(self) -> None:
        """See :http:post:`/api/(object-url)/trash`."""
        if not self.app.user:
            raise error.PermissionError()
        if self.trashed:
            return

        self.trashed = True
        self.app.r.oset(self.id, self)
        self.app.r.r.zadd(
            'micro_trash',
            {self.id.encode(): (datetime.now(timezone.utc) + Trashable.RETENTION).timestamp()})
        if self.__activity is not None:
            activity = self.__activity() if callable(self.__activity) else self.__activity
            activity.publish(Event.create('trashable-trash', cast(Object, self), app=self.app))

    def restore(self) -> None:
        """See :http:post:`/api/(object-url)/restore`."""
        if not self.app.user:
            raise error.PermissionError()
        if not self.trashed:
            return

        self.trashed = False
        self.app.r.oset(self.id, self)
        self.app.r.r.zrem('micro_trash', self.id.encode())
        if self.__activity is not None:
            activity = self.__activity() if callable(self.__activity) else self.__activity
            activity.publish(Event.create('trashable-restore', cast(Object, self), app=self.app))

    def json(self, restricted: bool = False, include: bool = False, *,
             rewrite: RewriteFunc = None) -> Dict[str, object]:
        """Subclass API: Return a JSON representation of the trashable part of the object."""
        # pylint: disable=unused-argument; part of subclass API
        return {'trashed': self.trashed}

class WithContent:
    """:class:`Editable` :class:`Object` with content."""

    app = None # type: Application

    @staticmethod
    async def process_attrs(attrs: Dict[str, object], *, app: Application) -> Dict[str, object]:
        """Pre-Process the given attributes *attrs* for editing."""
        if 'text' in attrs:
            text = attrs['text']
            if text is not None:
                attrs['text'] = str_or_none(expect_type(str)(text))
        if 'resource' in attrs:
            url = attrs['resource']
            if url is not None:
                attrs['resource'] = await app.analyzer.analyze(expect_type(str)(url))
        return attrs

    def __init__(self, *, text: str = None, resource: Resource = None) -> None:
        self.text = text
        self.resource = resource

    async def pre_edit(self, attrs: Dict[str, object]) -> Dict[str, object]:
        """Prepare the edit operation.

        More precisely, validate and pre-process the given *attrs*.
        """
        if 'resource' in attrs and self.resource and attrs['resource'] == self.resource.url:
            del attrs['resource']
        return await self.process_attrs(attrs, app=self.app)

    def do_edit(self, **attrs: object) -> Optional[Awaitable[None]]: # type: ignore
        """See :meth:`Editable.do_edit`."""
        if 'text' in attrs:
            self.text = expect_opt_type(str)(attrs['text'])
        if 'resource' in attrs:
            self.resource = expect_opt_type(Resource)(attrs['resource'])

    def json(self, restricted: bool = False, include: bool = False, *,
             rewrite: RewriteFunc = None) -> Dict[str, object]:
        """See :meth:`JSONifiable.json`."""
        # pylint: disable=unused-argument; part of API
        return {
            'text': self.text,
            'resource': self.resource.json(rewrite=rewrite) if self.resource else None
        }

class Collection(Generic[O], Sequence[O]):
    """See :ref:`Collection`.

    .. attribute:: ids

       Redis sequence tracking the (IDs of) objects that the collection contains.

    .. attribute:: check

       Function of the form *check(key)*, which is called before an object is retrieved via *key*.
       May be ``None``.

    .. attribute:: expect

       Function narrowing the type of a retrieved object.

    .. attribute:: app

       Context application.

    .. describe:: c[key]

       *key* may also be a string, in which case the object with the given ID is retrieved.

       Redis operations: ``RedisSequence[k] + n``, where n is the number of retrieved items, or
       ``i in RedisSequence + 1`` if *key* is a string.

    .. describe:: item in c

       *item* may also be a string, in which case the membership of the object with the given ID is
       tested.
    """

    def __init__(
            self, ids: RedisSequence, *, check: Callable[[Union[int, slice, str]], None] = None,
            expect: ExpectFunc[O] = cast(ExpectFunc[O], expect_type(Object)),
            app: Application) -> None:
        self.ids = ids
        self.check = check
        self.expect = expect
        self.app = app

    def index(self, x: Union[O, str], start: int = 0, stop: int = sys.maxsize) -> int:
        """See :meth:`Sequence.index`.

        *x* may also be a string, in which case the index of the object with the given ID is
        returned.
        """
        if isinstance(x, Object):
            return self.index(x.id, start, stop)
        return self.ids.index(cast(str, x).encode(), start, stop)

    def __len__(self) -> int:
        return len(self.ids)

    @overload
    def __getitem__(self, key: Union[int, str]) -> O:
        # pylint: disable=function-redefined; overload
        pass
    @overload
    def __getitem__(self, key: slice) -> List[O]:
        # pylint: disable=function-redefined; overload
        pass
    def __getitem__(self, key: Union[int, slice, str]) -> Union[O, List[O]]:
        # pylint: disable=function-redefined; overload
        if self.check:
            self.check(key)
        if isinstance(key, str):
            if key not in self:
                raise KeyError()
            return self.app.r.oget(key, default=ReferenceError, expect=self.expect)
        if isinstance(key, slice): # type: ignore[misc]
            return self.app.r.omget([id.decode() for id in self.ids[key]],
                                    default=ReferenceError, expect=self.expect)
        return self.app.r.oget(self.ids[key].decode(), default=ReferenceError,
                               expect=self.expect)

    def __iter__(self) -> Iterator[O]:
        # Optimized and used by count()
        return iter(self[:])

    def __contains__(self, item: object) -> bool:
        if isinstance(item, Object):
            return item.id in self
        return isinstance(item, str) and item.encode() in self.ids

    def json(self, restricted: bool = False, include: bool = False, *, rewrite: RewriteFunc = None,
             slc: slice = None) -> Dict[str, object]:
        """See :meth:`JSONifiable.json`.

        *slc* is a slice of items to include, if any.
        """
        count = len(self)
        if slc:
            items = self[slc]
            start = 0 if cast(Optional[int], slc.start) is None else cast(int, slc.start)
            stop = start + len(items)
        return {
            'count': count,
            **(
                {
                    'items': [item.json(restricted=restricted, include=include, rewrite=rewrite)
                              for item in items],
                    'slice': [start, stop]
                } if slc else {})
        }

class Orderable:
    """Mixin for :class:`Collection` whose items can be ordered.

    The underlying Redis collection must be a Redis list.
    """

    ids = None # type: RedisSequence
    app = None # type: Application

    def move(self, item: Object, to: Optional[Object]) -> None:
        """See :http:post:`/api/(collection-path)/move`."""
        if to:
            if to.id not in self: # type: ignore
                raise ValueError('to_not_found')
            if to == item:
                # No op
                return
        if not cast(int, self.app.r.lrem(self.ids.key, 1, item.id)):
            raise ValueError('item_not_found')
        if to:
            self.app.r.linsert(self.ids.key, 'after', to.id, item.id)
        else:
            self.app.r.lpush(self.ids.key, item.id)

class User(Object, Editable):
    """See :ref:`User`."""

    def __init__(self, *, app: Application, **data: Dict[str, object]) -> None:
        super().__init__(id=cast(str, data['id']), app=app)
        Editable.__init__(self, authors=cast(List[str], data['authors']))
        self.name = cast(str, data['name'])
        self.email = cast(Optional[str], data['email'])
        self.create_time = parse_isotime(cast(str, data['create_time']))
        self.authenticate_time = parse_isotime(cast(str, data['authenticate_time']))
        self.devices = Collection(
            RedisSortedSet(f'{self.id}.devices', app.r.r), check=self._check_user,
            expect=expect_type(Device), app=app)

    @property
    def auth_secret(self) -> str:
        # pylint: disable=missing-function-docstring; already documented
        # Compatibility with device attributes (deprecated since 0.58.0)
        return self.devices[0].auth_secret

    @property
    def device_notification_status(self) -> str:
        # pylint: disable=missing-function-docstring; already documented
        # Compatibility with device attributes (deprecated since 0.58.0)
        return self.devices[0].notification_status

    @property
    def push_subscription(self) -> Optional[str]:
        # pylint: disable=missing-function-docstring; already documented
        # Compatibility with device attributes (deprecated since 0.58.0)
        return self.devices[0].push_subscription

    def store_email(self, email: str) -> None:
        """Update the user's *email* address.

        If *email* is already associated with another user, a :exc:`ValueError`
        (``email_duplicate``) is raised.
        """
        check_email(email)
        id = self.app.r.r.hget('user_email_map', email.encode())
        if id and id.decode() != self.id:
            raise ValueError('email_duplicate')

        if self.email:
            self.app.r.hdel('user_email_map', self.email)
        self.email = email
        self.app.r.oset(self.id, self)
        self.app.r.hset('user_email_map', self.email, self.id)

    def set_email(self, email: str) -> 'AuthRequest':
        """See :http:post:`/api/users/(id)/set-email`."""
        if self.app.user != self:
            raise error.PermissionError()
        check_email(email)

        code = randstr(length=5, charset=string.ascii_uppercase)
        auth_request = AuthRequest(id='AuthRequest:' + randstr(), app=self.app, email=email,
                                   code=code)
        self.app.r.oset(auth_request.id, auth_request)
        self.app.r.expire(auth_request.id, 10 * 60)
        if self.app.render_email_auth_message:
            self._send_email(email, self.app.render_email_auth_message(email, auth_request, code))
        return auth_request

    def finish_set_email(self, auth_request: 'AuthRequest', auth: str) -> None:
        """See :http:post:`/api/users/(id)/finish-set-email`."""
        # pylint: disable=protected-access; auth_request is a friend
        if self.app.user != self:
            raise error.PermissionError()
        auth_request.verify(auth)
        self.app.r.delete(auth_request.id)
        self.store_email(auth_request._email)

    def remove_email(self):
        """See :http:post:`/api/users/(id)/remove-email`."""
        if self.app.user != self:
            raise error.PermissionError()
        if not self.email:
            raise ValueError('user_no_email')

        self.app.r.hdel('user_email_map', self.email)
        self.email = None
        self.app.r.oset(self.id, self)

    def send_email(self, msg):
        """Send an email message to the user.

        *msg* is the message string of the following form: It starts with a line containing the
        subject prefixed with ``Subject:_``, followed by a blank line, followed by the body.

        If the user's ::attr:`email` is not set, a :exc:`ValueError` (``user_no_email``) is raised.
        If communication with the SMTP server fails, an :class:`EmailError` is raised.
        """
        if not self.email:
            raise ValueError('user_no_email')
        self._send_email(self.email, msg)

    def notify(self, event: Event) -> None:
        """Notify the user about *event*.

        The notification is delivered to all enabled devices. If a device's *push_subscription* has
        expired, notifications are disabled for that device.
        """
        devices = self.app.r.omget([id.decode() for id in self.devices.ids], default=AssertionError,
                                   expect=expect_type(Device))
        for device in devices:
            if device.notification_status == 'on':
                create_task(self._notify(device, event))

    async def enable_device_notifications(self, push_subscription: str) -> None:
        """See :http:patch:`/api/users/(id)` (``enable_device_notifications``)."""
        # Compatibility with device actions (deprecated since 0.58.0)
        await self.devices[0].enable_notifications(push_subscription,
                                                   _event_type='user-enable-device-notifications')

    def disable_device_notifications(self) -> None:
        """See :http:patch:`/api/users/(id)` (``disable_device_notifications``)."""
        # Compatibility with device actions (deprecated since 0.58.0)
        self.devices[0].disable_notifications()

    def do_edit(self, **attrs):
        if self.app.user != self:
            raise error.PermissionError()

        e = InputError()
        if 'name' in attrs and not str_or_none(attrs['name']):
            e.errors['name'] = 'empty'
        e.trigger()

        if 'name' in attrs:
            self.name = attrs['name']

    def json(self, restricted: bool = False, include: bool = False, *,
             rewrite: RewriteFunc = None) -> Dict[str, object]:
        """See :meth:`Object.json`."""
        # Compatibility with device attributes (deprecated since 0.58.0)
        device = context.device.get()
        return {
            **super().json(restricted=restricted, include=include, rewrite=rewrite),
            **Editable.json(self, restricted=restricted, include=include, rewrite=rewrite),
            'name': self.name,
            **(
                {} if restricted and context.user.get() != self else {
                    'email': self.email,
                    'create_time': self.create_time.isoformat(),
                    'authenticate_time': self.authenticate_time.isoformat()
                }),
            **(
                {
                    'auth_secret': device.auth_secret,
                    'device_notification_status': device.notification_status,
                    'push_subscription': device.push_subscription
                } if restricted and context.user.get() == self and device else {})
        }

    def _send_email(self, to: str, msg: str) -> None:
        match = re.fullmatch(r'Subject: ([^\n]+)\n\n(.+)', msg, re.DOTALL)
        if not match:
            raise ValueError('msg_invalid')

        msg = EmailMessage()
        msg['To'] = to
        msg['From'] = self.app.email
        msg['Subject'] = match.group(1)
        msg.set_content(match.group(2))

        components = urlparse(self.app.smtp_url)
        host = components.hostname or 'localhost'
        port = components.port or 25
        try:
            with SMTP(host=host, port=port) as smtp:
                smtp.send_message(msg)
        except OSError as e:
            raise EmailError() from e

    async def _notify(self, device: Device, event: Event) -> None:
        try:
            assert device.push_subscription
            await self.app.send_device_notification(device.push_subscription, event)
        except (ValueError, CommunicationError) as e:
            if isinstance(e, ValueError):
                if str(e) != 'push_subscription_invalid':
                    raise e
                device.abort_notifications()
            getLogger(__name__).error('Failed to deliver notification: %s', str(e))

    def _check_user(self, _: Union[int, slice, str]) -> None:
        if context.user.get() != self:
            raise error.PermissionError()

class Users:
    """See :ref:`Users`."""

    def __init__(self, app: Application) -> None:
        self.app = app
        self._ids = RedisList('users', app.r.r)

    def __len__(self) -> int:
        return len(self._ids)

    def __getitem__(self, key: str) -> User:
        if not key.startswith('User:'):
            raise KeyError(key)
        return self.app.r.oget(key, default=KeyError, expect=expect_type(User))

    def __iter__(self) -> Iterator[User]:
        users = self.app.r.omget([id.decode() for id in self._ids], default=AssertionError,
                                 expect=expect_type(User))
        return iter(users)

class Settings(Object, Editable):
    """See :ref:`Settings`.

    .. attribute:: push_vapid_private_key

       VAPID private key used for sending device notifications.
    """

    def __init__(
            self, *, id: str, app: Application, authors: List[str], title: str, icon: Optional[str],
            icon_small: str = None, icon_large: str = None, provider_name: Optional[str],
            provider_url: Optional[str], provider_description: Optional[Dict[str, str]],
            feedback_url: Optional[str], staff: List[str], push_vapid_private_key: str,
            push_vapid_public_key: str) -> None:
        super().__init__(id, app)
        Editable.__init__(self, authors=authors, activity=lambda: app.activity)
        self.title = title
        self.icon = icon
        self.icon_small = icon_small
        self.icon_large = icon_large
        self.provider_name = provider_name
        self.provider_url = provider_url
        self.provider_description = provider_description
        self.feedback_url = feedback_url
        self._staff = staff
        self.push_vapid_private_key = push_vapid_private_key
        self.push_vapid_public_key = push_vapid_public_key

    @property
    def staff(self) -> List[User]:
        # pylint: disable=missing-docstring; already documented
        return self.app.r.omget(self._staff, default=AssertionError, expect=expect_type(User))

    def do_edit(self, **attrs):
        if not self.app.user.id in self._staff:
            raise error.PermissionError()

        e = InputError()
        if 'title' in attrs and not str_or_none(attrs['title']):
            e.errors['title'] = 'empty'
        e.trigger()

        if 'title' in attrs:
            self.title = attrs['title']
        if 'icon' in attrs:
            self.icon = str_or_none(attrs['icon'])
        if 'icon_small' in attrs:
            self.icon_small = str_or_none(attrs['icon_small'])
        if 'icon_large' in attrs:
            self.icon_large = str_or_none(attrs['icon_large'])
        if 'provider_name' in attrs:
            self.provider_name = str_or_none(attrs['provider_name'])
        if 'provider_url' in attrs:
            self.provider_url = str_or_none(attrs['provider_url'])
        if 'provider_description' in attrs:
            self.provider_description = attrs['provider_description']
        if 'feedback_url' in attrs:
            self.feedback_url = str_or_none(attrs['feedback_url'])

    def json(self, restricted=False, include=False, *, rewrite=None):
        return {
            **super().json(restricted=restricted, include=include, rewrite=rewrite),
            **Editable.json(self, restricted=restricted, include=include, rewrite=rewrite),
            'title': self.title,
            'icon': self.icon,
            'icon_small': self.icon_small,
            'icon_large': self.icon_large,
            'provider_name': self.provider_name,
            'provider_url': self.provider_url,
            'provider_description': self.provider_description,
            'feedback_url': self.feedback_url,
            'staff': [u.json(restricted=restricted, rewrite=rewrite) for u in self.staff] if include
                     else self._staff,
            'push_vapid_public_key': self.push_vapid_public_key,
            **({} if restricted else {'push_vapid_private_key': self.push_vapid_private_key})
        }

class Activity(Object, JSONRedisSequence[JSONifiable]):
    """See :ref:`Activity`.

    .. attribute:: post

       Hook of the form ``post(event)`` that is called after :meth:`publish` with the corresponding
       *event*. May be ``None``.
    """

    class Stream(AsyncIterator['Event']):
        """:cls:`collections.abc.AsyncGenerator` of events."""
        # Syntax for Python 3.6+:
        #
        # async def stream(self) -> AsyncGenerator['Event', None]:
        #     """Return a live stream of events."""
        #     queue = Queue() # type: Queue[Event]
        #     self._streams.add(queue)
        #     try:
        #         while True:
        #             yield await cast(Coroutine[object, None, Event], queue.get())
        #     except GeneratorExit as e:
        #         self._streams.remove(queue)
        #         # Work around https://bugs.python.org/issue34730
        #         queue.put_nowait(None) # type: ignore

        def __init__(self, streams: Set['Queue[Optional[Event]]']) -> None:
            self._queue = Queue() # type: Queue[Optional[Event]]
            self._streams = streams
            self._streams.add(self._queue)

        async def asend(self, value: None) -> 'Event':
            # pylint: disable=unused-argument, missing-docstring; part of API
            event = await cast(Coroutine[object, None, Optional[Event]], self._queue.get())
            if event is None:
                raise StopAsyncIteration()
            return event

        async def athrow(self, typ: Type[BaseException], val: BaseException = None,
                         tb: object = None) -> 'Event':
            # pylint: disable=unused-argument, missing-docstring; part of API
            raise val if val else typ()

        async def aclose(self) -> None:
            # pylint: disable=missing-docstring; part of API
            self._streams.remove(self._queue)
            self._queue.put_nowait(None)

        async def __anext__(self) -> 'Event':
            return await self.asend(None)

    def __init__(self, id: str, app: Application, subscriber_ids: List[str],
                 pre: Callable[[], None] = None) -> None:
        super().__init__(id, app)
        JSONRedisSequence.__init__(self, app.r, '{}.items'.format(id), pre)
        self.post = None # type: Optional[Callable[[Event], None]]
        self.host = None # type: Optional[object]
        self._subscriber_ids = subscriber_ids
        self._streams = set() # type: Set[Queue[Optional[Event]]]

    @property
    def subscribers(self) -> List[User]:
        """List of :class:`User`s who subscribed to the activity."""
        return self.app.r.omget(self._subscriber_ids, default=AssertionError,
                                expect=expect_type(User))

    def publish(self, event: 'Event') -> None:
        """Publish an *event* to the feed.

        All :attr:`subscribers`, except the user who triggered the event, are notified.
        """
        # If the event is published to multiple activity feeds, it is stored (and overwritten)
        # multiple times, but that's acceptable for a more convenient API
        self.r.oset(event.id, event)
        self.r.lpush(self.list_key, event.id)
        for subscriber in self.subscribers:
            if subscriber is not event.user:
                subscriber.notify(event)
        for stream in self._streams:
            stream.put_nowait(event)
        if self.post:
            self.post(event)

    def subscribe(self):
        """See :http:patch:`/api/(activity-url)` (``subscribe``)."""
        if not self.app.user:
            raise error.PermissionError()
        if not self.app.user.id in self._subscriber_ids:
            self._subscriber_ids.append(self.app.user.id)
        self.app.r.oset(self.host.id if self.host else self.id, self.host or self)

    def unsubscribe(self):
        """See :http:patch:`/api/(activity-url)` (``unsubscribe``)."""
        if not self.app.user:
            raise error.PermissionError()
        try:
            self._subscriber_ids.remove(self.app.user.id)
        except ValueError:
            pass
        self.app.r.oset(self.host.id if self.host else self.id, self.host or self)

    def stream(self) -> 'Activity.Stream':
        """Return a live stream of events."""
        return Activity.Stream(self._streams)

    def json(self, restricted: bool = False, include: bool = False, *, rewrite: RewriteFunc = None,
             slice: 'slice' = None) -> Dict[str, object]:
        # pylint: disable=arguments-differ; extension
        return {
            **super().json(restricted=restricted, include=include, rewrite=rewrite),
            **({'subscriber_ids': self._subscriber_ids} if not restricted else {}),
            **({'user_subscribed': self.app.user and self.app.user.id in self._subscriber_ids}
               if restricted else {}),
            **(
                {
                    'items': [event.json(restricted=True, include=True, rewrite=rewrite)
                              for event in self[slice]]
                } if slice else {})
        }

class Event(Object):
    """See :ref:`Event`."""

    @staticmethod
    def create(type: str, object: Optional[Object], detail: Dict[str, object] = {},
               app: Application = None) -> 'Event':
        """Create an event."""
        assert app
        if not app.user:
            raise error.PermissionError()
        if not str_or_none(type):
            raise ValueError('type_empty')
        if any(k.endswith('_id') for k in detail):
            raise ValueError('detail_invalid_key')

        transformed = {}
        for key, value in detail.items():
            if isinstance(value, Object):
                key = key + '_id'
                value = value.id
            transformed[key] = value
        return Event(
            id='Event:' + randstr(), type=type, object=object.id if object else None,
            user=app.user.id, time=datetime.utcnow().isoformat() + 'Z', detail=transformed, app=app)

    def __init__(self, id: str, type: str, object: Optional[str], user: str, time: str,
                 detail: Dict[str, object], app: Application) -> None:
        super().__init__(id, app)
        self.type = type
        self.time = parse_isotime(time)
        self._object_id = object
        self._user_id = user
        self._detail = detail

    @property
    def object(self) -> Optional[Union[Object, Gone]]:
        # pylint: disable=missing-docstring; already documented
        return (
            self.app.r.oget(self._object_id, expect=expect_type(Object)) or Gone()
            if self._object_id else None)

    @property
    def user(self) -> User:
        # pylint: disable=missing-docstring; already documented
        return self.app.users[self._user_id]

    @property
    def detail(self) -> Dict[str, builtins.object]:
        # pylint: disable=missing-docstring; already documented
        detail = {}
        for key, value in self._detail.items():
            if key.endswith('_id'):
                assert isinstance(value, str)
                key = key[:-3]
                value = self.app.r.oget(value) or Gone()
            detail[key] = value
        return detail

    def json(self, restricted: bool = False, include: bool = False, *,
             rewrite: RewriteFunc = None) -> Dict[str, builtins.object]:
        obj = self._object_id # type: Optional[Union[str, Dict[str, object]]]
        detail = self._detail
        if include:
            obj = (self.object.json(restricted=restricted, include=include, rewrite=rewrite)
                   if self.object else None)
            detail = {
                k: v.json(restricted=restricted, include=include, rewrite=rewrite)
                   if isinstance(v, (Object, Gone)) else v for k, v in self.detail.items()
            }
        return {
            **super().json(restricted=restricted, include=include, rewrite=rewrite),
            'type': self.type,
            'object': obj,
            'user': self.user.json(restricted=restricted, rewrite=rewrite) if include
                    else self._user_id,
            'time': self.time.isoformat(),
            'detail': detail
        }

    def __str__(self) -> str:
        return '<{} {} on {} by {}>'.format(type(self).__name__, self.type, self._object_id,
                                            self._user_id)
    __repr__ = __str__

class AuthRequest(Object):
    """See :ref:`AuthRequest`."""

    def __init__(self, id: str, app: Application, email: str, code: str) -> None:
        super().__init__(id, app)
        self._email = email
        self._code = code

    def verify(self, code: str) -> None:
        """Verify the secret *code*."""
        self.app.rate_limiter.count(RateLimit(f'{self.id}.verify', 10, timedelta(minutes=10)),
                                    context.client.get())
        if code != self._code:
            raise ValueError('Invalid code')

    def json(self, restricted: bool = False, include: bool = False, *,
             rewrite: RewriteFunc = None) -> Dict[str, object]:
        return {
            **super().json(restricted=restricted, include=include, rewrite=rewrite),
            **({} if restricted else {'email': self._email, 'code': self._code})
        }

class Location:
    """See :ref:`Location`."""

    def __init__(self, name: str, coords: Tuple[float, float] = None) -> None:
        if str_or_none(name) is None:
            raise ValueError('empty_name')
        if coords and not (-90 <= coords[0] <= 90 and -180 <= coords[1] <= 180):
            raise ValueError('out_of_range_coords')
        self.name = name
        self.coords = coords

    @staticmethod
    def parse(data: Dict[str, object]) -> 'Location':
        """Parse the given location JSON *data* into a :class:`Location`."""
        coords_list = Expect.opt(Expect.list(Expect.float))(data.get('coords'))
        if coords_list is None:
            coords = None
        else:
            if len(coords_list) != 2:
                raise TypeError()
            coords = (float(coords_list[0]), float(coords_list[1]))
        return Location(Expect.str(data.get('name')), coords)

    def json(self) -> Dict[str, object]:
        """Return a JSON representation of the location."""
        return {'name': self.name, 'coords': list(self.coords) if self.coords else None}

class InputError(ValueError):
    """See :ref:`InputError`.

    To raise an :exc:`InputError`, apply the following pattern::

       def meow(volume):
           e = InputError()
           if not 0 < volume <= 1:
               e.errors['volume'] = 'out_of_range'
           e.trigger()
           # ...
    """

    def __init__(self, errors: Dict[str, str] = {}) -> None:
        super().__init__('input_invalid')
        self.errors = dict(errors)

    def trigger(self):
        """Trigger the error, i.e. raise it if any *errors* are present.

        If *errors* is empty, do nothing.
        """
        if self.errors:
            raise self

class EmailError(Exception):
    """Raised if communication with the SMTP server fails."""
