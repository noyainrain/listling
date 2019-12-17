# webapi
# Released into the public domain
# https://github.com/noyainrain/micro/blob/master/micro/webapi.py

# pylint: disable=missing-docstring; test module

import json
from typing import Dict, Optional, cast

from tornado.testing import AsyncHTTPTestCase, gen_test
from tornado.web import Application, RequestHandler

from micro.webapi import CommunicationError, WebAPI, WebAPIError

class EchoEndpoint(RequestHandler):
    # pylint: disable=abstract-method; Tornado handlers define a semi-abstract data_received()

    def respond(self, code: Optional[str]) -> None:
        args = cast(object, json.loads(self.request.body.decode())) if self.request.body else None
        query = {name: values[0].decode() for name, values in self.request.query_arguments.items()}
        headers = dict(self.request.headers)
        if code:
            self.set_status(int(code))
        self.write({'args': args, 'query': query, 'headers': headers})

    get = respond
    post = respond

class WebAPITest(AsyncHTTPTestCase):
    def get_app(self) -> Application:
        return Application([(r'/api/echo(?:/(\d{3}))?$', EchoEndpoint)])

    @gen_test
    async def test_call(self) -> None:
        api = WebAPI(self.get_url('/api/'), query={'auth': 'abc'}, headers={'Auth': 'def'})
        echo = await api.call('POST', 'echo', args={'a': 42}, query={'b': 'Meow!'})
        self.assertEqual(echo.get('args'), cast(Dict[str, object], {'a': 42}))
        self.assertEqual(echo.get('query'), cast(Dict[str, object], {'b': 'Meow!', 'auth': 'abc'}))
        headers = echo.get('headers', {})
        assert isinstance(headers, dict)
        self.assertEqual(headers.get('Auth'), 'def')

    @gen_test
    async def test_call_error(self) -> None:
        api = WebAPI(self.get_url('/api/'))
        with self.assertRaises(WebAPIError) as cm:
            await api.call('POST', 'echo/400', args={'value': 'Meow!'})
        self.assertEqual(cm.exception.error.get('args'),
                         cast(Dict[str, object], {'value': 'Meow!'}))
        self.assertFalse(cm.exception.error.get('query'))
        self.assertEqual(cm.exception.status, 400)

    @gen_test
    async def test_call_no_host(self) -> None:
        api = WebAPI('https://example.invalid/api/')
        with self.assertRaises(CommunicationError):
            await api.call('GET', 'echo')
