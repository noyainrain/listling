# TODO

import os

from listling.resolve import Resolver

from tornado.web import Application
from tornado.testing import AsyncHTTPTestCase, gen_test

class ResolverTestCase(AsyncHTTPTestCase):
    def get_app(self):
        return Application(static_path=os.path.join(os.path.dirname(__file__), 'res'), static_url_prefix='/')

    # TODO: test_ext
    #@gen_test
    #async def test_resolve_youtube(self):
    #    resolver = Resolver()
    #    content = await resolver.resolve('https://www.youtube.com/watch?v=MFQPaN3Slws')
    #    print(content)
    #    self.assertTrue(content)
    #    self.assertEqual(content.content_type, 'video/youtube')

    @gen_test
    async def test_resolve_media(self):
        resolver = Resolver()
        content = await resolver.resolve(self.get_url('/image.png'))
        print(content)
        self.assertTrue(content)
        self.assertEqual(content.content_type, 'image/png')

    @gen_test
    async def test_resolve_media_cached(self):
        resolver = Resolver()
        content = await resolver.resolve(self.get_url('/image.png'))
        print(content)
        content = await resolver.resolve(self.get_url('/image.png'))
        print(content)
        self.assertTrue(content)
        self.assertEqual(content.content_type, 'image/png')

    @gen_test
    async def test_resolve_website(self):
        resolver = Resolver()
        content = await resolver.resolve(self.get_url('/website.html'))
        print(content)
        self.assertTrue(content)
        self.assertEqual(content.content_type, 'text/html')

    @gen_test
    async def test_resolve_website_og(self):
        resolver = Resolver()
        content = await resolver.resolve(self.get_url('/og.html'))
        print(content)
        self.assertTrue(content)
        self.assertEqual(content.content_type, 'video/mp4')
