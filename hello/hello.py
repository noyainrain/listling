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

"""micro application example."""

from __future__ import annotations

import sys
from typing import List, Optional, cast

from micro import Application, Collection, Editable, Event, Object, Settings, WithContent, error
from micro.core import context
from micro.jsonredis import RedisList
from micro.resource import Resource
from micro.server import CollectionEndpoint, Server
from micro.util import Expect, make_command_line_parser, randstr, setup_logging

class Hello(Application):
    """Hello application.

    .. attribute:: greetings

       See :class:`Hello.Greetings`.
    """

    class Greetings(Collection):
        """Collection of all class:`Greeting`s."""

        app: Hello

        async def create(self, text: Optional[str], resource: Optional[str]) -> Greeting:
            """Create a :class:`Greeting` and return it."""
            user = context.user.get()
            if not user:
                raise error.PermissionError()
            attrs = await WithContent.process_attrs({'text': text, 'resource': resource},
                                                    app=self.app)
            if not (attrs['text'] or attrs['resource']):
                raise error.ValueError('No text and resource')

            greeting = Greeting(
                id='Greeting:{}'.format(randstr()), app=self.app, authors=[user.id],
                text=attrs['text'], resource=attrs['resource'])
            self.app.r.oset(greeting.id, greeting)
            self.app.r.lpush(self.ids.key, greeting.id)
            self.app.activity.publish(
                Event.create('greetings-create', None, detail={'greeting': greeting}, app=self.app))
            return greeting

    def __init__(self, redis_url='', email='bot@localhost', smtp_url='',
                 render_email_auth_message=None, *, files_path='data', video_service_keys={}):
        super().__init__(
            redis_url=redis_url, email=email, smtp_url=smtp_url,
            render_email_auth_message=render_email_auth_message, files_path=files_path,
            video_service_keys=video_service_keys)
        self.types.update({'Greeting': Greeting})
        self.greetings = Hello.Greetings(RedisList('greetings', self.r.r), app=self)

    def create_settings(self) -> Settings:
        # pylint: disable=unexpected-keyword-arg; decorated
        return Settings(
            id='Settings', app=self, authors=[], title='Hello', icon=None, icon_small=None,
            icon_large=None, provider_name=None, provider_url=None, provider_description={},
            feedback_url=None, staff=[], push_vapid_private_key='', push_vapid_public_key='')

class Greeting(Object, Editable, WithContent):
    """Public greeting.

    .. attribute:: text

       Text content.
    """
    # pylint: disable=invalid-overridden-method; do_edit may be async

    def __init__(self, *, app: Hello, **data: object) -> None:
        super().__init__(id=cast(str, data['id']), app=app)
        Editable.__init__(self, authors=cast(List[str], data['authors']))
        WithContent.__init__(self, text=cast(Optional[str], data['text']),
                             resource=cast(Optional[Resource], data['resource']))

    async def do_edit(self, **attrs):
        attrs = await WithContent.pre_edit(self, attrs)
        if not (attrs.get('text', self.text) or attrs.get('resource', self.resource)):
            raise error.ValueError('No text and resource')
        WithContent.do_edit(attrs)

    def json(self, restricted=False, include=False, *, rewrite=None):
        return {
            **super().json(restricted=restricted, include=include, rewrite=rewrite),
            **Editable.json(self, restricted=restricted, include=include, rewrite=rewrite),
            **WithContent.json(self, restricted=restricted, include=include, rewrite=rewrite)
        }

def make_server(*, port=8080, url=None, debug=False, redis_url='', smtp_url='',
                files_path='data', video_service_keys={}, client_map_service_key=None):
    """Create a Hello server."""
    app = Hello(redis_url=redis_url, smtp_url=smtp_url, files_path=files_path,
                video_service_keys=video_service_keys)
    handlers = [
        (r'/api/greetings$', _GreetingsEndpoint, {'get_collection': lambda *args: app.greetings})
    ]
    return Server(app, handlers, port=port, url=url, debug=debug, client_config={
        'path': '.',
        'modules_path': 'node_modules',
        'shell': ['hello.js'],
        'map_service_key': client_map_service_key
    })

class _GreetingsEndpoint(CollectionEndpoint):
    # pylint: disable=abstract-method; Tornado handlers define a semi-abstract data_received()
    # pylint: disable=arguments-differ; Tornado handler arguments are defined by URLs
    # pylint: disable=missing-docstring; Tornado handlers are documented globally

    async def post(self):
        text = self.get_arg('text', Expect.opt(Expect.str))
        resource = self.get_arg('resource', Expect.opt(Expect.str))
        if resource is not None:
            resource = self.server.rewrite(resource, reverse=True)
        greeting = await self.app.greetings.create(text, resource)
        self.write(greeting.json(restricted=True, include=True, rewrite=self.server.rewrite))

def main(args):
    """Run Hello.

    *args* is the list of command line arguments.
    """
    args = make_command_line_parser().parse_args(args[1:])
    if 'video_service_keys' in args:
        values = iter(args.video_service_keys)
        args.video_service_keys = dict(zip(values, values))
    setup_logging(args.debug if 'debug' in args else False)
    make_server(**vars(args)).run()
    return 0

if __name__ == '__main__':
    sys.exit(main(sys.argv))
