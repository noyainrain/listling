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

"""Core parts of micro."""

from asyncio import (CancelledError, Task, Queue, # pylint: disable=unused-import; typing
                     ensure_future, get_event_loop, shield)
import builtins
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from functools import partial
from inspect import isawaitable
import json
from logging import getLogger
import re
from smtplib import SMTP
import sys
from typing import (AsyncIterator, Awaitable, Callable, Coroutine, Dict, Generic, Iterator, List,
                    Optional, Set, Tuple, Type, TypeVar, Union, cast, overload)
from urllib.parse import SplitResult, urlparse, urlsplit

from pywebpush import WebPusher, WebPushException
from py_vapid import Vapid
from py_vapid.utils import b64urlencode
from redis import StrictRedis
from redis.exceptions import ResponseError
from requests.exceptions import RequestException
from tornado.ioloop import IOLoop
from typing_extensions import Protocol

from .error import CommunicationError, ValueError
from .jsonredis import (ExpectFunc, JSONRedis, JSONRedisSequence, JSONRedisMapping, RedisList,
                        RedisSequence, bzpoptimed)
from .resource import ( # pylint: disable=unused-import; typing
    Analyzer, HandleResourceFunc, Image, Resource, Video, handle_image, handle_webpage,
    handle_youtube)
from .util import (Expect, OnType, check_email, expect_opt_type, expect_type, parse_isotime,
                   randstr, run_instant, str_or_none)

_PUSH_TTL = 24 * 60 * 60

O = TypeVar('O', bound='Object')

class JSONifiable(Protocol):
    """Object which can be encoded to and decoded from a JSON representation."""

    def __init__(self, **kwargs: object) -> None:
        # pylint: disable=super-init-not-called; protocol
        pass

    def json(self, restricted: bool = False, include: bool = False) -> Dict[str, object]:
        """Return a JSON representation of the object.

        The name of the object type is included as ``__type__``.

        By default, all attributes are included. If *restricted* is ``True``, a restricted view of
        the object is returned, i.e. attributes that should not be available to the current
        :attr:`Application.user` are excluded. If *include* is ``True``, additional fields that may
        be of interest to the caller are included.
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

    .. attribute:: analyzer

       Web resource analyzer.
    """

    def __init__(
            self, redis_url: str = '', email: str = 'bot@localhost', smtp_url: str = '',
            render_email_auth_message: Callable[[str, 'AuthRequest', str], str] = None, *,
            video_service_keys: Dict[str, str] = {}) -> None:
        check_email(email)
        try:
            # pylint: disable=pointless-statement; port errors are only triggered on access
            urlparse(smtp_url).port
        except builtins.ValueError:
            raise ValueError('smtp_url_invalid')

        self.redis_url = redis_url
        try:
            urlparts = urlsplit(self.redis_url)
            url = SplitResult(
                urlparts.scheme or 'redis', urlparts.netloc or 'localhost', urlparts.path,
                urlparts.query, urlparts.fragment
            ).geturl()
            self.r = JSONRedis(StrictRedis.from_url(url), self._encode, self._decode)
        except builtins.ValueError:
            raise ValueError('redis_url_invalid')

        # pylint: disable=import-outside-toplevel; circular dependency
        from .analytics import Analytics, Referral
        self.types = {
            'User': User,
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
        self.users = Collection(RedisList('users', self.r.r), expect=expect_type(User), app=self)
        self.analytics = Analytics(app=self)

        self.email = email
        self.smtp_url = smtp_url
        self.render_email_auth_message = render_email_auth_message

        self.video_service_keys = video_service_keys
        handlers = [handle_image, handle_webpage] # type: List[HandleResourceFunc]
        if 'youtube' in self.video_service_keys:
            handlers.insert(0, handle_youtube(self.video_service_keys['youtube']))
        self.analyzer = Analyzer(handlers=handlers)

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

    def update(self):
        """Update the database.

        If the database is fresh, it will be initialized. If the database is already up-to-date,
        nothing will be done. It is thus safe to call :meth:`update` without knowing if an update is
        necessary or not.
        """
        vb = cast(Optional[bytes], self.r.get('micro_version'))

        # If fresh, initialize database
        if not vb:
            settings = self.create_settings()
            settings.push_vapid_private_key, settings.push_vapid_public_key = (
                self._generate_push_vapid_keys())
            self.r.oset(settings.id, settings)
            activity = Activity(id='Activity', app=self, subscriber_ids=[])
            self.r.oset(activity.id, activity)
            self.r.set('micro_version', 9)
            self.do_update()
            return

        v = int(vb)
        r = JSONRedis[Dict[str, object]](self.r.r)
        r.caching = False
        expect_str = expect_type(str)

        # Deprecated since 0.15.0
        if v < 3:
            data = r.oget('Settings', default=AssertionError)
            data['provider_name'] = None
            data['provider_url'] = None
            data['provider_description'] = {}
            r.oset('Settings', data)
            r.set('micro_version', 3)

        # Deprecated since 0.6.0
        if v < 4:
            for obj in self._scan_objects(r):
                if not issubclass(self.types[expect_str(obj['__type__'])], Trashable):
                    del obj['trashed']
                    r.oset(expect_str(obj['id']), obj)
            r.set('micro_version', 4)

        # Deprecated since 0.13.0
        if v < 5:
            data = r.oget('Settings', default=AssertionError)
            data['icon_small'] = data['favicon']
            del data['favicon']
            data['icon_large'] = None
            r.oset('Settings', data)
            r.set('micro_version', 5)

        # Deprecated since 0.14.0
        if v < 6:
            data = r.oget('Settings', default=AssertionError)
            data['push_vapid_private_key'], data['push_vapid_public_key'] = (
                cast(Tuple[str, str], self._generate_push_vapid_keys())) # type: ignore
            r.oset('Settings', data)
            activity = Activity(id='Activity', app=self, subscriber_ids=[])
            r.oset(activity.id, activity.json())

            users = r.omget([id.decode() for id in cast(List[bytes], r.lrange('users', 0, -1))],
                            default=AssertionError)
            for user in users:
                user['device_notification_status'] = 'off'
                user['push_subscription'] = None
            r.omset({expect_str(user['id']): user for user in users})
            r.set('micro_version', 6)

        # Deprecated since 0.24.1
        if v < 7:
            ids = cast(List[bytes], r.lrange('activity', 0, -1))
            if ids:
                r.rpush('Activity.items', *ids)
                r.delete('activity')
            r.set('micro_version', 7)

        # Deprecated since 0.33.0
        if v < 8:
            for obj in self._scan_objects(r, Trashable):
                if obj['trashed']:
                    t = (datetime.now(timezone.utc) + Trashable.RETENTION).timestamp()
                    r.zadd('micro_trash', {obj['id'].encode(): t})
            r.set('micro_version', 8)

        # Deprecated since 0.39.0
        if v < 9:
            activity = {}
            for event in self._scan_objects(r, Event):
                user_id = event['user']
                t = parse_isotime(event['time'], aware=True)
                first, last = activity.get(user_id) or (t, t)
                activity[user_id] = (min(first, t), max(last, t))

            now = self.now()
            users = r.omget(r.lrange('users', 0, -1))
            for user in users:
                first, last = activity.get(user['id']) or (now, now)
                user['create_time'] = first.isoformat()
                user['authenticate_time'] = last.isoformat()
            r.omset({user['id']: user for user in users})
            r.set('micro_version', 9)

        self.do_update()

    def do_update(self) -> None:
        """Subclass API: Perform the database update.

        May be overridden by subclass. Called by :meth:`update`, which takes care of updating (or
        initializing) micro specific data. The default implementation does nothing.
        """

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

    def authenticate(self, secret: str) -> 'User':
        """Authenticate an :class:`User` (device) with *secret*.

        The identified user is set as current *user* and returned. If the authentication fails, an
        :exc:`AuthenticationError` is raised.
        """
        id = self.r.r.hget('auth_secret_map', secret.encode())
        if not id:
            raise AuthenticationError()
        user = self.users[id.decode()]
        self.user = user

        now = self.now()
        if now - user.authenticate_time >= timedelta(hours=1): # type: ignore
            user.authenticate_time = now
            self.r.oset(user.id, user)
        return user

    def login(self, code: str = None) -> 'User':
        """See :http:post:`/api/login`.

        The logged-in user is set as current *user*.
        """
        if code:
            id = self.r.r.hget('auth_secret_map', code.encode())
            if not id:
                raise ValueError('code_invalid')
            id = id.decode()
            user = self.users[id]

        else:
            id = 'User:' + randstr()
            now = self.now()
            user = self.create_user({
                'id': id,
                'app': self,
                'authors': [id],
                'name': 'Guest',
                'email': None,
                'auth_secret': randstr(),
                'create_time': now.isoformat(),
                'authenticate_time': now.isoformat(),
                'device_notification_status': 'off',
                'push_subscription': None
            })
            self.r.oset(user.id, user)
            self.r.rpush('users', user.id)
            self.r.hset('auth_secret_map', user.auth_secret, user.id)

            # Promote first user to staff
            if len(self.users) == 1:
                settings = self.settings # type: ignore
                # pylint: disable=protected-access; Settings is a friend
                settings._staff = [user.id] # type: ignore
                self.r.oset(settings.id, settings) # type: ignore

        return self.authenticate(user.auth_secret)

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
            raise PermissionError()

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
        # Compatibility for Settings without icon_large (deprecated since 0.13.0)
        if issubclass(type, Settings):
            json['v'] = 2
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

class Object:
    """Object in the application universe.

    .. attribute:: app

       Context :class:`Application`.
    """

    def __init__(self, id: str, app: Application) -> None:
        self.id = id
        self.app = app

    def json(self, restricted: bool = False, include: bool = False) -> Dict[str, object]:
        """See :meth:`JSONifiable.json`.

        Subclass API: May be overridden by subclass. The default implementation returns the
        attributes of :class:`Object`. *restricted* and *include* are ignored.
        """
        # pylint: disable=unused-argument; part of subclass API
        # Compatibility for trashed (deprecated since 0.6.0)
        return {'__type__': type(self).__name__, 'id': self.id,
                **({'trashed': False} if restricted else {})}

    def __repr__(self):
        return '<{}>'.format(self.id)

class Gone:
    """See :ref:`Gone`."""

    def json(self, restricted: bool = False, include: bool = False) -> Dict[str, object]:
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

    @overload
    def edit(self, *, asynchronous: None = None, **attrs: object) -> None:
        # pylint: disable=function-redefined,missing-docstring; overload
        pass
    @overload
    def edit(self, *, asynchronous: OnType, **attrs: object) -> Awaitable[None]:
        # pylint: disable=function-redefined,missing-docstring; overload
        pass
    def edit(self, *, asynchronous: OnType = None, **attrs: object) -> Optional[Awaitable[None]]:
        # pylint: disable=function-redefined,missing-docstring; overload
        # Compatibility for synchronous edit (deprecated since 0.27.0)
        coro = self._edit(**attrs)
        if asynchronous is None:
            run_instant(coro)
            return None
        return coro

    async def _edit(self, **attrs: object) -> None:
        """See :http:post:`/api/(object-url)`."""
        if not self.app.user:
            raise PermissionError()
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

    def json(self, restricted: bool = False, include: bool = False) -> Dict[str, object]:
        """Subclass API: Return a JSON object representation of the editable part of the object."""
        return {'authors': [a.json(restricted) for a in self.authors] if include else self._authors}

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
            raise PermissionError()
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
            raise PermissionError()
        if not self.trashed:
            return

        self.trashed = False
        self.app.r.oset(self.id, self)
        self.app.r.r.zrem('micro_trash', self.id.encode())
        if self.__activity is not None:
            activity = self.__activity() if callable(self.__activity) else self.__activity
            activity.publish(Event.create('trashable-restore', cast(Object, self), app=self.app))

    def json(self, restricted=False, include=False):
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

    def json(self, restricted: bool = False, include: bool = False) -> Dict[str, object]:
        """See :meth:`JSONifiable.json`."""
        # pylint: disable=unused-argument; part of API
        return {'text': self.text, 'resource': self.resource.json() if self.resource else None}

class Collection(Generic[O], JSONRedisMapping[O, JSONifiable]):
    """See :ref:`Collection`.

    All sequence operations but iteration are supported for now.

    .. attribute:: ids

       Redis sequence tracking the (IDs of) objects that the collection contains.

    .. attribute:: check

       Function of the form *check(key)*, which is called before an object is retrieved via *key*.
       May be ``None``.

    .. attribute:: expect

       Function narrowing the type of a retrieved object.

    .. attribute:: app

       Context application.

    .. attribute:: host

       Tuple ``(object, attr)`` that specifies the attribute name *attr* on the host *object*
       (:class:`Object` or :class:`Application`) the collection is attached to.

       .. deprecated:: 0.24.0

          Extend :class:`Collection` to implement hosting manually.

    .. describe:: c[key]

       *key* may also be a string, in which case the object with the given ID is retrieved.

       Redis operations: ``RedisSequence[k] + n``, where n is the number of retrieved items, or
       ``i in RedisSequence + 1`` if *key* is a string.

    .. describe:: item in c

       *item* may also be a string, in which case the membership of the object with the given ID is
       tested.

    .. deprecated: 0.24.0

       :class:`JSONRedisMapping` interface. Use :attr:`ids`, ``c[key]`` and ``item in c`` instead.
    """

    @overload
    def __init__(
            self, ids: RedisSequence, *,
            check: Callable[[Union[int, slice, str]], None] = None,
            expect: ExpectFunc[O] = cast(ExpectFunc[O], expect_type(Object)),
            app: Application) -> None:
        # pylint: disable=function-redefined, super-init-not-called; overload
        pass
    @overload
    def __init__(self, host: Tuple[Union[Object, Application], str]) -> None:
        # pylint: disable=function-redefined, super-init-not-called; overload
        pass
    def __init__(
            self, *args: object,
            check: Callable[[Union[int, slice, str]], None] = None,
            expect: ExpectFunc[O] = cast(ExpectFunc[O], expect_type(Object)),
            **kwargs: object) -> None:
        # pylint: disable=function-redefined, super-init-not-called; overload
        # Compatibility for host (deprecated since 0.24.0)
        ids = kwargs.get('ids') or kwargs.get('host') or args[0] if args else None
        if isinstance(ids, tuple):
            host = cast(Tuple[Union[Object, Application], str], ids)
            app = host[0] if isinstance(host[0], Application) else host[0].app
            ids = RedisList(
                ('' if isinstance(host[0], Application) else host[0].id + '.') + host[1], app.r.r)
        elif isinstance(ids, RedisSequence):
            arg = kwargs.get('app')
            assert isinstance(arg, Application)
            app = arg
            host = (app, '')
        else:
            raise TypeError()
        JSONRedisMapping.__init__(self, app.r, ids.key, expect)
        self.host = host

        self.ids = ids
        self.check = check
        self.app = app

    def index(self, x: Union[O, str], start: int = 0, stop: int = sys.maxsize) -> int:
        """See :meth:`Sequence.index`.

        *x* may also be a string, in which case the index of the object with the given ID is
        returned.
        """
        if isinstance(x, Object):
            return self.index(x.id, start, stop)
        return self.ids.index(x.encode(), start, stop)

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
        # Compatibility with JSONRedisMapping (deprecated since 0.24.0)
        assert self.expect

        if self.check:
            self.check(key)
        if isinstance(key, str):
            if key not in self:
                raise KeyError()
            return self.app.r.oget(key, default=ReferenceError, expect=self.expect)
        if isinstance(key, slice):
            return self.app.r.omget([id.decode() for id in self.ids[key]],
                                    default=ReferenceError, expect=self.expect)
        return self.app.r.oget(self.ids[key].decode(), default=ReferenceError,
                               expect=self.expect)

    def __iter__(self) -> Iterator[str]:
        # Compatibility with JSONRedisMapping (deprecated since 0.24.0)
        return (id.decode() for id in self.ids)

    def __contains__(self, item: object) -> bool:
        if isinstance(item, Object):
            return item.id in self
        return isinstance(item, str) and item.encode() in self.ids

    def json(self, restricted: bool = False, include: bool = False, *,
             slc: slice = None) -> Dict[str, object]:
        """See :meth:`JSONifiable.json`.

        *slc* is a slice of items to include, if any.
        """
        count = len(self)
        if slc:
            items = self[slc]
            start = 0 if slc.start is None else slc.start
            stop = start + len(items)
        return {
            'count': count,
            **(
                {'items': [item.json(restricted, include) for item in items],
                 'slice': [start, stop]}
                if slc else {})
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
        self.auth_secret = cast(str, data['auth_secret'])
        self.create_time = parse_isotime(cast(str, data['create_time']), aware=True)
        self.authenticate_time = parse_isotime(cast(str, data['authenticate_time']), aware=True)
        self.device_notification_status = cast(str, data['device_notification_status'])
        self.push_subscription = cast(Optional[str], data['push_subscription'])

    def store_email(self, email):
        """Update the user's *email* address.

        If *email* is already associated with another user, a :exc:`ValueError`
        (``email_duplicate``) is raised.
        """
        check_email(email)
        id = self.app.r.hget('user_email_map', email)
        if id and id.decode() != self.id:
            raise ValueError('email_duplicate')

        if self.email:
            self.app.r.hdel('user_email_map', self.email)
        self.email = email
        self.app.r.oset(self.id, self)
        self.app.r.hset('user_email_map', self.email, self.id)

    def set_email(self, email):
        """See :http:post:`/api/users/(id)/set-email`."""
        if self.app.user != self:
            raise PermissionError()
        check_email(email)

        code = randstr()
        auth_request = AuthRequest(id='AuthRequest:' + randstr(), app=self.app, email=email,
                                   code=code)
        self.app.r.oset(auth_request.id, auth_request)
        self.app.r.expire(auth_request.id, 10 * 60)
        if self.app.render_email_auth_message:
            self._send_email(email, self.app.render_email_auth_message(email, auth_request, code))
        return auth_request

    def finish_set_email(self, auth_request, auth):
        """See :http:post:`/api/users/(id)/finish-set-email`."""
        # pylint: disable=protected-access; auth_request is a friend
        if self.app.user != self:
            raise PermissionError()
        if auth != auth_request._code:
            raise ValueError('auth_invalid')

        self.app.r.delete(auth_request.id)
        self.store_email(auth_request._email)

    def remove_email(self):
        """See :http:post:`/api/users/(id)/remove-email`."""
        if self.app.user != self:
            raise PermissionError()
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

    def notify(self, event: 'Event') -> None:
        """Notify the user about the :class:`Event` *event*.

        If :attr:`push_subscription` has expired, device notifications are disabled.
        """
        if self.device_notification_status != 'on':
            return
        IOLoop.current().add_callback(self._notify, event) # type: ignore

    async def enable_device_notifications(self, push_subscription):
        """See :http:patch:`/api/users/(id)` (``enable_device_notifications``)."""
        if self.app.user != self:
            raise PermissionError()
        await self._send_device_notification(
            push_subscription, Event.create('user-enable-device-notifications', self, app=self.app))
        self.device_notification_status = 'on'
        self.push_subscription = push_subscription
        self.app.r.oset(self.id, self)

    @overload
    def disable_device_notifications(self, user: 'User' = None) -> None:
        # pylint: disable=function-redefined,missing-docstring; overload
        pass
    @overload
    def disable_device_notifications(self, reason: str = None) -> None:
        # pylint: disable=function-redefined,missing-docstring; overload
        pass
    def disable_device_notifications(self, *args: object, **kwargs: object) -> None:
        """See :http:patch:`/api/users/(id)` (``disable_device_notifications``).

        .. deprecated:: 0.17.0

           Argument *reason*.

        .. deprecated:: 0.17.0

           Default value for *user*. Provide it explicitly instead.
        """
        # pylint: disable=function-redefined,missing-docstring; overload
        # Compatibility for reason (deprecated since 0.17.0)
        user = kwargs.get('user', kwargs.get('reason', args[0] if args else None))
        if user is None or isinstance(user, str):
            reason = user
            if reason not in [None, 'expired']:
                raise ValueError('reason_unknown')
            self._disable_device_notifications(reason)
            return
        assert isinstance(user, User)

        if user != self:
            raise PermissionError()
        self._disable_device_notifications()

    def do_edit(self, **attrs):
        if self.app.user != self:
            raise PermissionError()

        e = InputError()
        if 'name' in attrs and not str_or_none(attrs['name']):
            e.errors['name'] = 'empty'
        e.trigger()

        if 'name' in attrs:
            self.name = attrs['name']

    def json(self, restricted: bool = False, include: bool = False) -> Dict[str, object]:
        """See :meth:`Object.json`."""
        return {
            **super().json(restricted, include),
            **Editable.json(self, restricted, include),
            'name': self.name,
            **(
                {} if restricted and self.app.user != self else {
                    'email': self.email,
                    'auth_secret': self.auth_secret,
                    'create_time': self.create_time.isoformat(),
                    'authenticate_time': self.authenticate_time.isoformat(),
                    'device_notification_status': self.device_notification_status,
                    'push_subscription': self.push_subscription
                })
        }

    def _send_email(self, to, msg):
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
        except OSError:
            raise EmailError()

    async def _notify(self, event):
        try:
            await self._send_device_notification(self.push_subscription, event)
        except (ValueError, CommunicationError) as e:
            if isinstance(e, ValueError):
                if e.code != 'push_subscription_invalid':
                    raise e
                self._disable_device_notifications(reason='expired')
            getLogger(__name__).error('Failed to deliver notification: %s', str(e))

    async def _send_device_notification(self, push_subscription, event):
        try:
            push_subscription = json.loads(push_subscription)
            if not isinstance(push_subscription, dict):
                raise builtins.ValueError()
            urlparts = urlparse(push_subscription['endpoint'])
            pusher = WebPusher(push_subscription)
        except (builtins.ValueError, KeyError, WebPushException):
            raise ValueError('push_subscription_invalid')

        # Unfortunately sign() tries to validate the email address
        email = 'bot@email.localhost' if self.app.email == 'bot@localhost' else self.app.email
        headers = Vapid.from_raw(self.app.settings.push_vapid_private_key.encode()).sign({
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
            raise CommunicationError(
                '{} for POST {}'.format(str(e.args[0]), push_subscription['endpoint']))
        if response.status_code in (404, 410):
            raise ValueError('push_subscription_invalid')
        if response.status_code != 201:
            raise CommunicationError(
                'Unexpected response status {} for POST {}'.format(response.status_code,
                                                                   push_subscription['endpoint']))

    def _disable_device_notifications(self, reason: str = None) -> None:
        self.device_notification_status = 'off.{}'.format(reason) if reason else 'off'
        self.push_subscription = None
        self.app.r.oset(self.id, self)

class Settings(Object, Editable):
    """See :ref:`Settings`.

    .. attribute:: push_vapid_private_key

       VAPID private key used for sending device notifications.
    """

    def __init__(
            self, *, id: str, app: Application, authors: List[str], title: str, icon: Optional[str],
            icon_small: str = None, icon_large: str = None, provider_name: Optional[str],
            provider_url: Optional[str], provider_description: Optional[Dict[str, str]],
            feedback_url: Optional[str], staff: List[str], push_vapid_private_key: str = None,
            push_vapid_public_key: str = None, favicon: str = None, v: int = 1) -> None:
        # pylint: disable=unused-argument; part of API
        # Compatibility for versioned function (deprecated since 0.40.0)
        super().__init__(id, app)
        Editable.__init__(self, authors=authors, activity=lambda: app.activity)
        self.title = title
        self.icon = icon
        # Compatibility for favicon (deprecated since 0.13.0)
        self.icon_small = icon_small or favicon
        self.icon_large = icon_large
        self.provider_name = provider_name
        self.provider_url = provider_url
        self.provider_description = provider_description
        self.feedback_url = feedback_url
        self._staff = staff
        # Compatibility for Settings without VAPID keys (deprecated since 0.14.0)
        self.push_vapid_private_key = push_vapid_private_key or ''
        self.push_vapid_public_key = push_vapid_public_key or ''

    @property
    def staff(self):
        # pylint: disable=missing-docstring; already documented
        return self.app.r.omget(self._staff)

    def do_edit(self, **attrs):
        if not self.app.user.id in self._staff:
            raise PermissionError()

        # Compatibility for favicon (deprecated since 0.13.0)
        if 'favicon' in attrs:
            attrs.setdefault('icon_small', attrs['favicon'])

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

    def json(self, restricted=False, include=False):
        return {
            **super().json(restricted, include),
            **Editable.json(self, restricted, include),
            'title': self.title,
            'icon': self.icon,
            'icon_small': self.icon_small,
            'icon_large': self.icon_large,
            'provider_name': self.provider_name,
            'provider_url': self.provider_url,
            'provider_description': self.provider_description,
            'feedback_url': self.feedback_url,
            'staff': [u.json(restricted) for u in self.staff] if include else self._staff,
            'push_vapid_public_key': self.push_vapid_public_key,
            # Compatibility for favicon (deprecated since 0.13.0)
            **({'favicon': self.icon_small} if restricted else
               {'push_vapid_private_key': self.push_vapid_private_key})
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
            raise PermissionError()
        if not self.app.user.id in self._subscriber_ids:
            self._subscriber_ids.append(self.app.user.id)
        self.app.r.oset(self.host.id if self.host else self.id, self.host or self)

    def unsubscribe(self):
        """See :http:patch:`/api/(activity-url)` (``unsubscribe``)."""
        if not self.app.user:
            raise PermissionError()
        try:
            self._subscriber_ids.remove(self.app.user.id)
        except ValueError:
            pass
        self.app.r.oset(self.host.id if self.host else self.id, self.host or self)

    def stream(self) -> 'Activity.Stream':
        """Return a live stream of events."""
        return Activity.Stream(self._streams)

    def json(self, restricted: bool = False, include: bool = False,
             slice: 'slice' = None) -> Dict[str, object]:
        # pylint: disable=arguments-differ; extension
        return {
            **super().json(restricted, include),
            **({'subscriber_ids': self._subscriber_ids} if not restricted else {}),
            **({'user_subscribed': self.app.user and self.app.user.id in self._subscriber_ids}
               if restricted else {}),
            **({'items': [event.json(True, True) for event in self[slice]]} if slice else {})
        }

class Event(Object):
    """See :ref:`Event`.

    .. attribute:: time

       .. deprecated:: 0.39.0

          Naive time. Work with aware object instead (with
          :meth:`datetime.datetime.replace` (``tzinfo=timezone.utc``)).
    """

    @staticmethod
    def create(type: str, object: Optional[Object], detail: Dict[str, object] = {},
               app: Application = None) -> 'Event':
        """Create an event."""
        assert app
        if not app.user:
            raise PermissionError()
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

    def json(self, restricted: bool = False, include: bool = False) -> Dict[str, builtins.object]:
        obj = self._object_id # type: Optional[Union[str, Dict[str, object]]]
        detail = self._detail
        if include:
            obj = self.object.json(restricted, include) if self.object else None
            detail = {k: v.json(restricted, include) if isinstance(v, (Object, Gone)) else v
                      for k, v in self.detail.items()}
        return {
            **super().json(restricted, include),
            'type': self.type,
            'object': obj,
            'user': self.user.json(restricted) if include else self._user_id,
            'time': self.time.isoformat() + 'Z' if self.time else None,
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

    def json(self, restricted=False, include=False):
        return {
            **super().json(restricted, include),
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

class AuthenticationError(Exception):
    """See :ref:`AuthenticationError`."""

class PermissionError(Exception):
    """See :ref:`PermissionError`."""

class EmailError(Exception):
    """Raised if communication with the SMTP server fails."""
