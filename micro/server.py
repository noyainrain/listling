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

# pylint: disable=abstract-method; Tornado handlers define a semi-abstract data_received()
# pylint: disable=arguments-differ; Tornado handler arguments are defined by URLs
# pylint: disable=missing-docstring; Tornado handlers are documented globally

"""Server components."""

from asyncio import (CancelledError, Future, Task, gather, # pylint: disable=unused-import; typing
                     get_event_loop, ensure_future)
from collections.abc import Mapping
from datetime import datetime, timezone
from functools import partial
from http import HTTPStatus
import http.client
import json
from logging import getLogger
import os
from pathlib import Path
import re
from signal import SIGINT
from typing import (Callable, ClassVar, Dict, List, Optional, Sequence, Tuple, Type, TypeVar, Union,
                    cast)
from urllib.parse import urljoin, urlparse, urlsplit

from mypy_extensions import TypedDict, VarArg
from tornado.httpclient import AsyncHTTPClient, HTTPResponse # pylint: disable=unused-import; typing
from tornado.httpserver import HTTPServer
from tornado.httputil import HTTPServerRequest
from tornado.template import DictLoader, Loader, filter_whitespace
from tornado.web import Application, HTTPError, RequestHandler, StaticFileHandler

from . import micro, templates, error
from .core import context
from .micro import ( # pylint: disable=unused-import; typing
    Activity, AuthRequest, Collection, JSONifiable, Object, User, InputError, Trashable)
from .ratelimit import RateLimitError
from .resource import NoResourceError, ForbiddenResourceError, BrokenResourceError
from .util import (Expect, ExpectFunc, cancel, look_up_files, str_or_none, parse_slice,
                   check_polyglot)
from .webapi import CommunicationError

LIST_LIMIT = 100
SLICE_URL = r'(?:/(\d*:\d*))?'

_CLIENT_ERROR_LOG_TEMPLATE = """\
Client error occurred
%s%s
Stack:
%s
URL: %s
User: %s
Device info: %s"""

_LOGGER = getLogger(__name__)

class _UndefinedType:
    pass
_UNDEFINED = _UndefinedType()

Handler = Union[Tuple[str, Type[RequestHandler]],
                Tuple[str, Type[RequestHandler], Dict[str, object]]]

_ApplicationSettings = TypedDict('_ApplicationSettings', # pylint: disable=invalid-name; type alias
                                 {'static_path': str, 'server': 'Server'})

_T = TypeVar('_T')

class Server:
    """Server for micro apps.

    The server may optionally serve the client in :attr:`client_config` *path*. All files from
    *modules_path*, ``manifest.webmanifest``, ``manifest.js`` and the script at *service_path* are
    delivered, with a catch-all for ``index.html``.

    Also, the server may act as a dynamic build system for the client. ``index.html`` is rendered as
    template. A web app manifest ``manifest.webmanifest`` and a build manifest ``manifest.js`` (see
    *shell*) are generated.

    .. attribute:: app

       Underlying :class:`micro.Application`.

    .. attribute:: handlers

       Table of request handlers.

       It is a list of tuples, mapping a URL regular expression pattern to a
       :class:`tornado.web.RequestHandler` class.

    .. attribute:: port

       See ``--port`` command line option.

    .. attribute:: url

       See ``--url`` command line option.

    .. attribute:: debug

       See ``--debug`` command line option.

    .. attribute:: client_config

       Client configuration:

       - ``path``: Location from where static files and templates are delivered
       - ``service_path``: Location of service worker script. Defaults to the included micro service
         worker.
       - ``shell``: Set of files that make up the client shell. See
         :func:`micro.util.look_up_files`.
       - ``map_service_key``: See ``--client-map-service-key`` command line option
       - ``description``: Short description of the service
       - ``color``: CSS primary color of the service
       - ``share_target``: Indicates if the client accepts content via the Web Share Target API.
         Defaults to ``False``. Shared content is received at ``/share`` with a
         :data:`navigator.serviceWorker` message ``{type, data}``, where *type* is ``share`` and
         *data* is a *ShareData* object.
       - ``share_target_accept``: Media types and filename extensions (starting with ``.``) of
         accepted files, if any. Defaults to ``[]``.
    """

    ClientConfig = TypedDict('ClientConfig', {
        'path': str,
        'modules_path': str,
        'service_path': str,
        'shell': Sequence[str],
        'map_service_key': Optional[str],
        'description': str,
        'color': str,
        'share_target': bool,
        'share_target_accept': Sequence[str]
    })
    ClientConfigArg = TypedDict('ClientConfigArg', {
        'path': str,
        'modules_path': str,
        'service_path': str,
        'shell': Sequence[str],
        'map_service_key': Optional[str],
        'description': str,
        'color': str,
        'share_target': bool,
        'share_target_accept': Sequence[str]
    }, total=False)

    def __init__(
            self, app: micro.Application, handlers: Sequence[Handler], *, port: int = 8080,
            url: str = None, debug: bool = False, client_config: ClientConfigArg = {}) -> None:
        url = url or 'http://localhost:{}'.format(port)
        try:
            urlparts = urlparse(url)
        except ValueError as e:
            raise ValueError('url_invalid') from e
        not_allowed = {'username', 'password', 'path', 'params', 'query', 'fragment'}
        if not (urlparts.scheme in {'http', 'https'} and urlparts.hostname and
                not any(cast(object, getattr(urlparts, k)) for k in not_allowed)):
            raise ValueError('url_invalid')

        self.app = app
        self.port = port
        self.url = url
        self.debug = debug
        self.client_config = {
            'path': 'client',
            'modules_path': '.',
            'service_path': os.path.join(client_config.get('modules_path', '.'),
                                         '@noyainrain/micro/service.js'),
            'map_service_key': None,
            'description': 'Social micro web app',
            'color': '#08f',
            'share_target': False,
            'share_target_accept': [],
            **client_config, # type: ignore
            'shell': list(client_config.get('shell') or [])
        } # type: Server.ClientConfig

        self.app.email = 'bot@' + urlparts.hostname
        self.app.render_email_auth_message = self._render_email_auth_message

        def get_activity(*args: str) -> Activity:
            # pylint: disable=unused-argument; part of API
            return self.app.activity
        self.handlers = [
            # API
            (r'/api/login$', _LoginEndpoint),
            (r'/api/users/([^/]+)$', _UserEndpoint),
            (r'/api/users/([^/]+)/set-email$', _UserSetEmailEndpoint),
            (r'/api/users/([^/]+)/finish-set-email$', _UserFinishSetEmailEndpoint),
            (r'/api/users/([^/]+)/remove-email$', _UserRemoveEmailEndpoint),
            (r'/api/users/([^/]+)/devices$', CollectionEndpoint,
             {'get_collection': lambda id: self.app.users[id].devices}), # type: ignore[misc]
            (r'/api/devices$', _DevicesEndpoint),
            (r'/api/devices/([^/]+)$', _DeviceEndpoint),
            (r'/api/settings$', _SettingsEndpoint),
            *make_activity_endpoints(r'/api/activity', get_activity),
            # Compatibility with old global activity URL (deprecated since 0.57.0)
            *make_activity_endpoints(r'/api/activity/v2', get_activity),
            # Provide alias because /api/analytics triggers popular ad blocking filters
            (r'/api/(?:analytics|stats)/statistics/([^/]+)$', _StatisticEndpoint),
            (r'/api/(?:analytics|stats)/referrals$', _ReferralsEndpoint),
            (r'/api/(?:analytics|stats)/referrals/summary$', _ReferralSummaryEndpoint),
            (r'/api/previews/([^/]+)$', _PreviewEndpoint),
            (r'/files$', _FilesEndpoint), # type: ignore[misc]
            (r'/files/([^/]+)$', _FileEndpoint), # type: ignore[misc]
            *handlers,
            # UI
            (r'/log-client-error$', _LogClientErrorEndpoint),
            (r'/index.html$', _Index),
            (r'/manifest.webmanifest$', _WebManifest), # type: ignore
            (r'/manifest.js$', _BuildManifest), # type: ignore
            (fr"/static/{self.client_config['service_path']}$", _Service), # type: ignore
            (r'/static/(.*)$', _Static, {'path': self.client_config['path']}), # type: ignore
            (r'/.*$', UI), # type: ignore
        ] # type: List[Handler]

        application = Application(
            self.handlers, compress_response=True, # type: ignore[arg-type]
            template_path=self.client_config['path'], debug=self.debug, server=self)
        # Install static file handler manually to allow pre-processing
        cast(_ApplicationSettings, application.settings).update(
            {'static_path': self.client_config['path']})
        self._server = HTTPServer(application, xheaders=True)

        self._garbage_collect_files_task = None # type: Optional[Task[None]]
        self._empty_trash_task = None # type: Optional[Task[None]]
        self._collect_statistics_task = None # type: Optional[Task[None]]
        self._message_templates = DictLoader(templates.MESSAGE_TEMPLATES, autoescape=None)
        self._micro_templates = Loader(
            os.path.join(self.client_config['path'], self.client_config['modules_path'],
                         '@noyainrain/micro'))

    def start(self) -> None:
        """Start the server."""
        self.app.update() # type: ignore
        self._garbage_collect_files_task = self.app.start_garbage_collect_files()
        self._empty_trash_task = self.app.start_empty_trash()
        self._collect_statistics_task = self.app.analytics.start_collect_statistics()
        self._server.listen(self.port)

    async def stop(self) -> None:
        """Stop the server."""
        self._server.stop()
        if self._garbage_collect_files_task:
            await cancel(self._garbage_collect_files_task)
        if self._empty_trash_task:
            await cancel(self._empty_trash_task)
        if self._collect_statistics_task:
            await cancel(self._collect_statistics_task)

    def run(self) -> None:
        """Start the server and run it continuously."""
        self.start()
        loop = get_event_loop()
        def _on_sigint() -> None:
            async def _stop() -> None:
                await self.stop()
                loop.stop()
            ensure_future(_stop())
        loop.add_signal_handler(SIGINT, _on_sigint)
        getLogger(__name__).info('Started server at %s/', self.url)
        loop.run_forever()

    def rewrite(self, url: str, *, reverse: bool = False) -> str:
        """Rewrite an internal file *url* to a public URL.

        If *reverse* is ``True``, mapping is done in the opposite direction.
        """
        if reverse:
            prefix = f'{self.url}/files/'
            return f'file:/{url[len(prefix):]}' if url.startswith(prefix) else url
        return f'{self.url}/files/{url[6:]}' if url.startswith('file:/') else url

    def _render_email_auth_message(self, email, auth_request, auth):
        template = self._message_templates.load('email_auth')
        msg = template.generate(email=email, auth_request=auth_request, auth=auth, app=self.app,
                                server=self).decode()
        return '\n\n'.join([filter_whitespace('oneline', p.strip()) for p in
                            re.split(r'\n{2,}', msg)])

class Endpoint(RequestHandler):
    """JSON REST API endpoint.

    .. attribute:: server

       Context server.

    .. attribute:: app

       Context :class:`Application`.

    .. attribute:: args

       Dictionary of JSON arguments passed by the client.
    """

    current_user = None # type: Optional[User]

    def __init__(self, application: Application, request: HTTPServerRequest,
                 **kwargs: object) -> None:
        # Erase Any from kwargs
        super().__init__(application, request, **kwargs)

    def initialize(self, **args: object) -> None:
        # pylint: disable=unused-argument; part of subclass API
        self.server = cast(_ApplicationSettings, self.application.settings)['server']
        self.app = self.server.app
        self.args = {} # type: Dict[str, object]

    def prepare(self) -> None:
        context.client.set(self.request.remote_ip) # type: ignore

        self.app.user = None
        auth_secret = self.get_cookie('auth_secret')
        if auth_secret:
            device = self.app.devices.authenticate(auth_secret)
            self.current_user = device.user
            context.user.set(self.current_user)
            context.device.set(device)

        if self.request.body:
            try:
                self.args = json.loads(self.request.body.decode())
            except ValueError as e:
                raise HTTPError(http.client.BAD_REQUEST) from e
            if not isinstance(self.args, Mapping):
                raise HTTPError(http.client.BAD_REQUEST)

        if self.request.method in {'GET', 'HEAD'}:
            self.set_header('Cache-Control', 'no-cache')

    def patch(self, *args, **kwargs):
        try:
            op = getattr(self, 'patch_{}'.format(self.args.pop('op')))
        except KeyError as e:
            raise HTTPError(http.client.BAD_REQUEST) from e
        except AttributeError as e:
            raise HTTPError(http.client.UNPROCESSABLE_ENTITY) from e
        # Pass through future to support async methods
        return op(*args, **kwargs)

    def write_error(self, status_code: int, **kwargs: object) -> None:
        e = cast(Tuple[Type[BaseException], BaseException, object], kwargs['exc_info'])[1]
        if isinstance(e, KeyError):
            self.set_status(http.client.NOT_FOUND)
            self.write({'__type__': 'NotFoundError'}) # type: ignore
        elif isinstance(e, RateLimitError):
            self.set_status(http.client.TOO_MANY_REQUESTS)
            data = {'__type__': type(e).__name__, 'message': str(e)}
            self.write(data)
        elif isinstance(e, InputError):
            self.set_status(http.client.BAD_REQUEST)
            self.write({**e.json(), 'errors': e.errors}) # type: ignore
        elif isinstance(e, CommunicationError):
            self.set_status(http.client.BAD_GATEWAY)
            self.write({'__type__': type(e).__name__, 'message': str(e)}) # type: ignore
        elif isinstance(e, error.AuthenticationError):
            self.set_status(http.client.BAD_REQUEST)
            self.clear_cookie('auth_secret')
            self.write(e.json())
        elif isinstance(e, error.Error):
            status = {
                error.ValueError: http.client.BAD_REQUEST,
                error.PermissionError: http.client.FORBIDDEN,
                NoResourceError: http.client.NOT_FOUND,
                ForbiddenResourceError: http.client.FORBIDDEN,
                BrokenResourceError: http.client.BAD_REQUEST
            }
            self.set_status(status[type(e)])
            self.write(e.json())
        else:
            super().write_error(status_code, **kwargs)

    def log_exception(self, typ, value, tb):
        # These errors are handled specially and there is no need to log them as exceptions
        if issubclass(typ, (KeyError, RateLimitError, CommunicationError, error.Error)):
            return
        super().log_exception(typ, value, tb)

    def get_arg(self, name: str, expect: ExpectFunc[_T], *,
                default: Union[_T, _UndefinedType] = _UNDEFINED) -> _T:
        """Return the argument with the given *name*, asserting its type with *expect*.

        If the argument does not exist, *default* is returned. If the argument has an unexpected
        type or is missing with no *default*, a :exc:`micro.error.ValueError` is raised.
        """
        arg = self.args.get(name, default)
        if arg is _UNDEFINED:
            raise error.ValueError('Missing {}'.format(name))
        try:
            return expect(arg)
        except TypeError as e:
            raise error.ValueError('Bad {} type'.format(name)) from e

    def check_args(self, type_info):
        """Check *args* for their expected type.

        *type_info* maps argument names to :class:`type` s. If multiple types are valid for an
        argument, a tuple can be given. The special keyword ``'opt'`` marks an argument as optional.
        ``None`` is equvialent to ``type(None)``. An example *type_info* could look like::

            {'name': str, 'pattern': (str, 'opt')}

        If any argument has an unexpected type, an :exc:`InputError` with ``bad_type`` is raised. If
        an argument is missing but required, an :exc:`InputError` with ``missing`` is raised.

        A filtered subset of *args* is returned, matching those present in *type_info*. Thus any
        excess argument passed by the client can safely be ignored.
        """
        args = {k: v for k, v in self.args.items() if k in type_info.keys()}

        e = InputError()
        for arg, types in type_info.items():
            # Normalize
            if not isinstance(types, tuple):
                types = (types, )
            types = tuple(type(None) if t is None else t for t in types)

            # Check
            if arg not in args:
                if 'opt' not in types:
                    e.errors[arg] = 'missing'
            else:
                types = tuple(t for t in types if isinstance(t, type))
                # NOTE: We currently do not handle types being empty (e.g. it contained only
                # keywords)
                if not isinstance(args.get(arg), types):
                    e.errors[arg] = 'bad_type'
        e.trigger()

        return args

class CollectionEndpoint(Endpoint):
    """API endpoint for a :class:`Collection`.

    .. attribute:: get_collection

       Function of the form *get_collection(*args: str) -> Collection*, responsible for retrieving
       the underlying collection. *args* are the URL arguments.
    """

    def initialize(self, **args: object) -> None:
        super().initialize(**args)
        get_collection = args.get('get_collection')
        if not callable(get_collection):
            raise TypeError()
        self.get_collection = get_collection # type: Callable[[VarArg(str)], Collection[Object]]

    def get(self, *args: str) -> None:
        collection = self.get_collection(*args)
        try:
            slc = parse_slice(cast(str, self.get_query_argument('slice', ':')), limit=LIST_LIMIT)
        except ValueError as e:
            raise error.ValueError('bad_slice_format') from e
        self.write(
            collection.json(restricted=True, include=True, rewrite=self.server.rewrite, slc=slc))

class ActivityStreamEndpoint(Endpoint):
    """Event stream API endpoint for :class:`Activity`.

    .. attribute:: get_activity

       Function of the form ``get_activity(*args)``, responsible for retrieving the activity. *args*
       are the URL arguments.
    """

    def initialize(self, **args: object) -> None:
        super().initialize(**args)
        get_activity = args.get('get_activity')
        if not callable(get_activity):
            raise TypeError()
        self.get_activity = get_activity # type: Callable[[VarArg(str)], Activity]
        self._stream = None # type: Optional[Activity.Stream]

    async def get(self, *args: str) -> None:
        activity = self.get_activity(*args)
        self._stream = activity.stream()
        self.set_header('Content-Type', 'text/event-stream')
        self.flush()
        async for event in self._stream:
            self.app.user = self.current_user
            data = json.dumps(
                event.json(restricted=True, include=True, rewrite=self.server.rewrite))
            self.write('data: {}\n\n'.format(data))
            self.flush()

    def on_connection_close(self) -> None:
        if self._stream:
            ensure_future(self._stream.aclose())

def make_list_endpoints(
        url: str, get_list: Callable[[VarArg(str)], Sequence[JSONifiable]]) -> List[Handler]:
    """Make the API endpoints for a list with support for slicing.

    *url* is the URL of the list.

    *get_list* is a hook of the form *get_list(*args)*, responsible for retrieving the underlying
    list. *args* are the URL arguments.
    """
    return [(url + r'(?:/(\d*:\d*))?$', _ListEndpoint, {'get_list': get_list})]

def make_trashable_endpoints(url, get_object):
    """Make API endpoints for a :class:`Trashable` object.

    *url* is the URL of the object.

    *get_object* is a function of the form *get_object(*args)*, responsible for retrieving the
    object. *args* are the URL arguments.
    """
    return [
        (url + r'/trash$', _TrashableTrashEndpoint, {'get_object': get_object}),
        (url + r'/restore$', _TrashableRestoreEndpoint, {'get_object': get_object})
    ]

def make_orderable_endpoints(url, get_collection):
    """Make API endpoints for a :class:`Orderable` collection.

    *url* and *get_collection* are equivalent to the arguments of :func:`make_list_endpoints`.
    """
    return [(url + r'/move$', _OrderableMoveEndpoint, {'get_collection': get_collection})]

def make_activity_endpoints(url: str,
                            get_activity: Callable[[VarArg(str)], Activity]) -> List[Handler]:
    """Make API endpoints for an :class:`Activity` at *url*.

    *get_activity* is a function of the form ``get_activity(*args)``, responsible for retrieving the
    activity. *args* are the URL arguments.
    """
    return [
        (fr'{url}{SLICE_URL}$', _ActivityEndpoint, {'get_activity': get_activity}),
        (fr'{url}/stream$', ActivityStreamEndpoint, {'get_activity': get_activity})
    ]

class _Static(StaticFileHandler):
    def set_extra_headers(self, path: str) -> None:
        server = cast(_ApplicationSettings, self.application.settings)['server']
        if self.get_cache_time(path, self.modified, self.get_content_type()) == 0:
            self.set_header('Cache-Control', 'no-cache')
        if path == server.client_config['service_path']:
            self.set_header('Service-Worker-Allowed', '/')

class UI(RequestHandler):
    """Request handler serving the UI.

    .. attribute:: server

       Context sever.

    .. attribute:: app

       Context application.
    """

    def __init__(self, application: Application, request: HTTPServerRequest,
                 **kwargs: object) -> None:
        # Erase Any from kwargs
        super().__init__(application, request, **kwargs)

    def initialize(self) -> None:
        self.server = cast(_ApplicationSettings, self.application.settings)['server']
        self.app = self.server.app
        # pylint: disable=protected-access; Server is a friend
        self._templates = self.server._micro_templates
        if self.server.debug:
            self._templates.reset()

    def get_meta(self, *args: str) -> Dict[str, str]:
        """Subclass API: Generate meta data for (part of) the UI.

        *args* are the URL arguments.

        Generally, a meta data item is rendered as HTML meta tag, with the following special cases:

        - ``title`` as title tag
        - ``icon-{sizes}`` as link tag with *rel* ``icon`` and the given *sizes*, e.g.
          ``icon-16x16``
        - ``og:*`` as RDFa meta tag

        By default, the returned meta data describes the service in general.
        """
        # pylint: disable=unused-argument; part of API
        settings = self.server.app.settings
        return {
            'title': settings.title,
            'description': self.server.client_config['description'],
            'application-name': settings.title,
            **({'icon-16x16': settings.icon_small} if settings.icon_small else {}),
            # Largest icon size in use across popular platforms (128px with 4x scaling)
            **({'icon-512x512': settings.icon_large} if settings.icon_large else {}),
            'theme-color': self.server.client_config['color'],
            'og:type': 'website',
            'og:url': urljoin(self.server.url, self.request.uri),
            'og:title': settings.title,
            'og:description': self.server.client_config['description'],
            'og:image': urljoin(self.server.url, settings.icon_large),
            'og:image:alt': '{} logo'.format(settings.title),
            'og:site_name': settings.title
        }

    def get(self, *args: str) -> None:
        meta = self.get_meta(*args)
        meta.setdefault('title', '')
        meta.setdefault('icon-16x16', '')
        meta.setdefault('icon-512x512', '')
        meta.setdefault('theme-color', '')

        data = {
            **cast(Dict[str, object], self.get_template_namespace()),
            **self.server.client_config,
            'meta': meta,
        } # type: Dict[str, object]

        self.set_header('Cache-Control', 'no-cache')
        self.set_header('Content-Security-Policy', '; '.join([
            "default-src 'self'",
            "style-src 'self' 'unsafe-inline'",
            # Allow third party APIs and boot script
            "script-src * 'sha256-P4JqQi52XRk4d4LReDaKYGMuOGGbkQf0J2K7+Dk6vzU=' 'unsafe-eval'",
            "connect-src *",
            # Allow third party image APIs
            "img-src * data:",
            # Allow third party embeds
            "frame-src *"
        ]))
        self.render(
            'index.html',
            micro_dependencies=partial(self._render_micro_dependencies, data), # type: ignore
            micro_boot=partial(self._render_micro_boot, data), # type: ignore
            micro_templates=partial(self._render_micro_templates, data)) # type: ignore

    def _render_micro_dependencies(self, data: Dict[str, object]) -> bytes:
        return self._templates.load('dependencies.html').generate(**data)

    def _render_micro_boot(self, data: Dict[str, object]) -> bytes:
        return self._templates.load('boot.html').generate(**data)

    def _render_micro_templates(self, data: Dict[str, object]) -> bytes:
        return self._templates.load('templates.html').generate(**data)

class _Index(UI):
    def get_meta(self, *args: str) -> Dict[str, str]:
        return {}

class _WebManifest(RequestHandler):
    def initialize(self) -> None:
        self._server = cast(_ApplicationSettings, self.application.settings)['server']

    def get(self, *args: str) -> None:
        # pylint: disable=unused-argument; part of API
        settings = self._server.app.settings
        meta = {
            'name': settings.title,
            'description': self._server.client_config['description'],
            'icons': [
                *([{'src': settings.icon_small, 'sizes': '16x16'}] if settings.icon_small else []),
                *([{'src': settings.icon_large, 'sizes': '512x512'}] if settings.icon_large else [])
            ],
            'theme_color': self._server.client_config['color'],
            'background_color': 'white',
            'start_url': '/',
            'display': 'standalone',
            **({
                'share_target': {
                    'action': '/share',
                    'method': 'POST',
                    'enctype': 'multipart/form-data',
                    'params': {
                        'title': 'title',
                        'text': 'text',
                        'url': 'url',
                        **({
                            'files': { # type: ignore
                                'name': 'files',
                                'accept': self._server.client_config['share_target_accept']
                            }
                        } if self._server.client_config['share_target_accept'] else {})
                    }
                }
            } if self._server.client_config['share_target'] else {})
        }

        self.set_header('Cache-Control', 'no-cache')
        self.set_header('Content-Type', 'application/manifest+json')
        self.write(meta)

class _BuildManifest(RequestHandler):
    _MICRO_CLIENT_SHELL = [
        '{}/@noyainrain/micro/*.js',
        '!{}/@noyainrain/micro/service.js',
        '!{}/@noyainrain/micro/karma.conf.js',
        '{}/@noyainrain/micro/components/*.js',
        '!{}/@noyainrain/micro/components/analytics.js',
        '{}/@noyainrain/micro/micro.css',
        '{}/@noyainrain/micro/images',
        '{}/webcomponents.js/webcomponents-lite.min.js',
        '{}/event-source-polyfill/src/eventsource.min.js',
        '{}/chart.js/dist/Chart.bundle.min.js',
        '{}/leaflet/dist/leaflet.js',
        '{}/leaflet/dist/leaflet.css',
        '{}/typeface-open-sans/files/open-sans-latin-[346]00.woff',
        '{}/typeface-open-sans/files/open-sans-latin-400italic.woff',
        '{}/@fortawesome/fontawesome-free/css/all.min.css',
        '{}/@fortawesome/fontawesome-free/webfonts/fa-regular-400.woff2',
        '{}/@fortawesome/fontawesome-free/webfonts/fa-solid-900.woff2'
    ]

    _manifest = None # type: ClassVar[Dict[str, object]]

    def initialize(self) -> None:
        self._server = cast(_ApplicationSettings, self.application.settings)['server']

    async def get(self) -> None:
        if not self._manifest:
            shell = [
                'index.html',
                *self._server.client_config['shell'],
                f"!{self._server.client_config['service_path']}",
                *(pattern.format(self._server.client_config['modules_path'])
                  for pattern in self._MICRO_CLIENT_SHELL)
            ]
            shell = [path.relative_to(self._server.client_config['path'])
                     for path in look_up_files(shell, top=self._server.client_config['path'])]
            shell = [path if path == Path('index.html') else Path('static') / path
                     for path in shell]
            # Instead of reading files directly, go through server to handle dynamic content (e.g.
            # rendered templates). Tornado does not provide an API to request a response, so fall
            # back to HTTP.
            client = AsyncHTTPClient()
            requests = (client.fetch('http://localhost:{}/{}'.format(self._server.port, path))
                        for path in shell)
            responses = await cast('Future[Tuple[HTTPResponse]]', gather(*requests))
            shell = ['/{}?v={}'.format(path, response.headers['Etag'].strip('"'))
                     for path, response in zip(shell, responses)]
            _BuildManifest._manifest = {'shell': shell, 'debug': self._server.debug} # type: ignore

        self.set_header('Content-Type', 'text/javascript')
        self.write('micro.service.MANIFEST = {};\n'.format(json.dumps(self._manifest)))

class _Service(RequestHandler):
    _version = None # type: ClassVar[str]

    def initialize(self) -> None:
        self._server = cast(_ApplicationSettings, self.application.settings)['server']

    async def get(self) -> None:
        if not self._version:
            response = await AsyncHTTPClient().fetch(
                'http://localhost:{}/manifest.js'.format(self._server.port))
            _Service._version = response.headers['Etag'].strip('"') # type: ignore

        self.set_header('Content-Type', 'text/javascript')
        self.set_header('Content-Security-Policy', "default-src 'self'")
        self.set_header('Service-Worker-Allowed', '/')
        self.render(self._server.client_config['service_path'], version=self._version)

class _LogClientErrorEndpoint(Endpoint):
    def post(self):
        args = self.check_args({
            'type': str,
            'stack': str,
            'url': str,
            'message': (str, None, 'opt')
        })
        e = micro.InputError()
        if str_or_none(args['type']) is None:
            e.errors['type'] = 'empty'
        if str_or_none(args['stack']) is None:
            e.errors['stack'] = 'empty'
        if str_or_none(args['url']) is None:
            e.errors['url'] = 'empty'
        e.trigger()

        message = str_or_none(args.get('message'))
        message_part = ': ' + message if message else ''
        user = '{} ({})'.format(self.app.user.name, self.app.user.id) if self.app.user else '-'
        _LOGGER.error(
            _CLIENT_ERROR_LOG_TEMPLATE, args['type'], message_part, args['stack'].strip(),
            args['url'], user, self.request.headers.get('user-agent', '-'))
        self.write({})

class _ListEndpoint(Endpoint):
    def initialize(self, get_list):
        super().initialize()
        self.get_list = get_list

    def get(self, *args):
        seq = self.get_list(*args)
        slice = parse_slice(args[-1] or ':', limit=LIST_LIMIT)
        self.write(
            json.dumps([i.json(restricted=True, include=True, rewrite=self.server.rewrite)
                        if isinstance(i, Object) else i for i in seq[slice]]))

class _TrashableTrashEndpoint(Endpoint):
    def initialize(self, **args: object) -> None:
        super().initialize(**args)
        get_object = args.get('get_object')
        if not callable(get_object):
            raise TypeError()
        self.get_object = get_object # type: Callable[[VarArg(str)], Trashable]

    def post(self, *args: str) -> None:
        obj = self.get_object(*args)
        obj.trash()
        self.write(obj.json(restricted=True, include=True, rewrite=self.server.rewrite))

class _TrashableRestoreEndpoint(Endpoint):
    def initialize(self, **args: object) -> None:
        super().initialize(**args)
        get_object = args.get('get_object')
        if not callable(get_object):
            raise TypeError()
        self.get_object = get_object # type: Callable[[VarArg(str)], Trashable]

    def post(self, *args: str) -> None:
        obj = self.get_object(*args)
        obj.restore()
        self.write(obj.json(restricted=True, include=True, rewrite=self.server.rewrite))

class _OrderableMoveEndpoint(Endpoint):
    def initialize(self, get_collection):
        super().initialize()
        self.get_collection = get_collection

    def post(self, *args):
        collection = self.get_collection(*args)
        args = self.check_args({'item_id': str, 'to_id': (str, None)})
        try:
            args['item'] = collection[args.pop('item_id')]
        except KeyError as e:
            raise error.ValueError('item_not_found') from e
        args['to'] = args.pop('to_id')
        if args['to'] is not None:
            try:
                args['to'] = collection[args['to']]
            except KeyError as e:
                raise error.ValueError('to_not_found') from e

        collection.move(**args)
        self.write(json.dumps(None))

class _LoginEndpoint(Endpoint):
    def post(self):
        args = self.check_args({'code': (str, 'opt')})
        user = self.app.login(**args)
        context.user.set(user)
        self.write(user.json(restricted=True, rewrite=self.server.rewrite))

class _UserEndpoint(Endpoint):
    def get(self, id: str) -> None:
        self.write(self.app.users[id].json(restricted=True, rewrite=self.server.rewrite))

    async def post(self, id):
        user = self.app.users[id]
        args = self.check_args({'name': (str, 'opt')})
        await user.edit(**args)
        self.write(user.json(restricted=True, rewrite=self.server.rewrite))

    async def patch_enable_notifications(self, id: str) -> None:
        # pylint: disable=missing-docstring; private
        # Compatibility with device actions (deprecated since 0.58.0)
        user = self.app.users[id]
        push_subscription = self.get_arg('push_subscription', Expect.str)
        await user.enable_device_notifications(push_subscription)
        self.write(user.json(restricted=True, rewrite=self.server.rewrite))

    def patch_disable_notifications(self, id: str) -> None:
        # pylint: disable=missing-docstring; private
        # Compatibility with device actions (deprecated since 0.58.0)
        user = self.app.users[id]
        user.disable_device_notifications()
        self.write(user.json(restricted=True, rewrite=self.server.rewrite))

class _UserSetEmailEndpoint(Endpoint):
    def post(self, id):
        user = self.app.users[id]
        args = self.check_args({'email': str})
        auth_request = user.set_email(**args)
        self.write(auth_request.json(restricted=True))

class _UserFinishSetEmailEndpoint(Endpoint):
    def post(self, id):
        user = self.app.users[id]
        args = self.check_args({'auth_request_id': str, 'auth': str})
        args['auth_request'] = self.app.get_object(args.pop('auth_request_id'), None)
        if not isinstance(args['auth_request'], AuthRequest):
            raise error.ValueError('auth_request_not_found')
        user.finish_set_email(**args)
        self.write(user.json(restricted=True, rewrite=self.server.rewrite))

class _UserRemoveEmailEndpoint(Endpoint):
    def post(self, id):
        user = self.app.users[id]
        user.remove_email()
        self.write(user.json(restricted=True, rewrite=self.server.rewrite))

class _DevicesEndpoint(Endpoint):
    def post(self) -> None:
        device = self.app.devices.sign_in()
        context.user.set(device.user)
        self.set_status(HTTPStatus.CREATED)
        self.set_cookie(
            'auth_secret', device.auth_secret, expires_days=360,
            secure=urlsplit(self.server.url).scheme == 'https', httponly=True)
        self.write(device.json(restricted=True, include=True, rewrite=self.server.rewrite))

class _DeviceEndpoint(Endpoint):
    def get(self, id: str) -> None:
        device = context.device.get() if id == 'self' else self.app.devices[id]
        if device is None:
            raise KeyError(id)
        self.set_cookie(
            'auth_secret', device.auth_secret, expires_days=360,
            secure=urlsplit(self.server.url).scheme == 'https', httponly=True)
        self.write(device.json(restricted=True, include=True, rewrite=self.server.rewrite))

    async def patch_enable_notifications(self, id: str) -> None:
        # pylint: disable=missing-docstring; private
        device = self.app.devices[id]
        push_subscription = self.get_arg('push_subscription', Expect.str)
        await device.enable_notifications(push_subscription)
        self.write(device.json(restricted=True, include=True, rewrite=self.server.rewrite))

    def patch_disable_notifications(self, id: str) -> None:
        # pylint: disable=missing-docstring; private
        device = self.app.devices[id]
        device.disable_notifications()
        self.write(device.json(restricted=True, include=True, rewrite=self.server.rewrite))

class _SettingsEndpoint(Endpoint):
    def get(self):
        self.write(
            self.app.settings.json(restricted=True, include=True, rewrite=self.server.rewrite))

    async def post(self):
        args = self.check_args({
            'title': (str, 'opt'),
            'icon': (str, None, 'opt'),
            'icon_small': (str, None, 'opt'),
            'icon_large': (str, None, 'opt'),
            'provider_name': (str, None, 'opt'),
            'provider_url': (str, None, 'opt'),
            'provider_description': (dict, 'opt'),
            'feedback_url': (str, None, 'opt')
        })
        if 'provider_description' in args:
            try:
                check_polyglot(args['provider_description'])
            except ValueError as e:
                raise error.ValueError('provider_description_bad_type') from e

        settings = self.app.settings
        await settings.edit(**args)
        self.write(settings.json(restricted=True, include=True, rewrite=self.server.rewrite))

class _ActivityEndpoint(Endpoint):
    def initialize(self, get_activity):
        super().initialize()
        self.get_activity = get_activity

    def get(self, *args):
        activity = self.get_activity(*args)
        slice = parse_slice(args[-1] or ':', limit=LIST_LIMIT)
        self.write(
            activity.json(restricted=True, include=True, rewrite=self.server.rewrite, slice=slice))

    def patch_subscribe(self, *args):
        # pylint: disable=missing-docstring; private
        activity = self.get_activity(*args)
        activity.subscribe()
        self.write(activity.json(restricted=True, include=True))

    def patch_unsubscribe(self, *args):
        # pylint: disable=missing-docstring; private
        activity = self.get_activity(*args)
        activity.unsubscribe()
        self.write(activity.json(restricted=True, include=True))

class _StatisticEndpoint(Endpoint):
    def get(self, topic: str) -> None:
        statistic = self.app.analytics.statistics[topic]
        self.write(statistic.json(user=self.current_user))

class _ReferralsEndpoint(CollectionEndpoint):
    def initialize(self, **args: object) -> None:
        super().initialize(get_collection=lambda: self.app.analytics.referrals, **args)

    def post(self) -> None:
        url = self.get_arg('url', Expect.str)
        referral = self.app.analytics.referrals.add(url, user=self.current_user)
        self.set_status(HTTPStatus.CREATED) # type: ignore
        self.write(referral.json(restricted=True, include=True))

class _ReferralSummaryEndpoint(Endpoint):
    def get(self) -> None:
        period: Optional[Tuple[datetime, datetime]] = None
        period_arg = self.get_query_argument("period", None)
        if period_arg:
            try:
                start, end = period_arg.split('/')
                period = (datetime.fromisoformat(start).replace(tzinfo=timezone.utc),
                          datetime.fromisoformat(end).replace(tzinfo=timezone.utc))
            except (TypeError, ValueError) as e:
                raise error.ValueError('Bad period format') from e

        data = self.app.analytics.referrals.summarize(period)
        data = {'referrers': [{'url': referrer[0], 'count': referrer[1]} for referrer in data]}
        self.write(data)

class _PreviewEndpoint(Endpoint):
    async def get(self, url: str) -> None:
        resource = await self.app.analyzer.analyze(self.server.rewrite(url, reverse=True))
        self.write(resource.json(rewrite=self.server.rewrite))

class _FilesEndpoint(RequestHandler):
    CONTENT_TYPES = {'image/bmp', 'image/gif', 'image/jpeg', 'image/png', 'image/svg+xml'}

    def initialize(self) -> None:
        self.server = cast(_ApplicationSettings, self.application.settings)['server']

    async def post(self) -> None:
        content_type = cast(Optional[str], self.request.headers.get('Content-Type'))
        if content_type not in self.CONTENT_TYPES:
            raise HTTPError(HTTPStatus.UNSUPPORTED_MEDIA_TYPE)
        url = await self.server.app.files.write(self.request.body, content_type)
        self.set_header('Location', self.server.rewrite(url))
        self.set_status(HTTPStatus.CREATED)

class _FileEndpoint(RequestHandler):
    def initialize(self) -> None:
        self.server = cast(_ApplicationSettings, self.application.settings)['server']

    async def get(self, name: str) -> None:
        try:
            data, content_type = await self.server.app.files.read(f'file:/{name}')
        except LookupError as e:
            raise HTTPError(HTTPStatus.NOT_FOUND) from e
        self.set_header('Content-Type', content_type)
        self.set_header('Cache-Control', f'max-age={60 * 60 * 24 * 360}')
        self.write(data)
