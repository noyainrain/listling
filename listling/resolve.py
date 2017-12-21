# TODO

"""TODO: Resolve web content in a form suitable for embedding."""

from tornado.httpclient import AsyncHTTPClient
from html.parser import HTMLParser

IMAGE_TYPES = ['image/jpeg', 'image/png', 'image/svg+xml', 'image/gif']
VIDEO_TYPES = ['video/mp4']

class WebError(Exception):
    pass

class WebContent:
    """
    .. attribute: url -> text/html, image/*, video/*, audio/* -> all

    .. attribute: content_type -> all

    .. attribute: image -> all

    .. attribute: description -> all

    .. attribute: size -> image/*, video/*

       Width and height of graphical content (e.g. image, video).
    """
    # NOTE: maybe also image size

    def __init__(self, url, content_type, description=None, image=None, size=None):
        self.url = url
        self.content_type = content_type
        self.description = description
        self.image = image
        self.size = size

    def __repr__(self):
        #return '<{} {} {} {}>'.format(type(self).__name__, self.url, self.content_type, self.description)
        return str(vars(self))

class Resolver:
    def __init__(self):
        self.handlers = [
            handle_youtube,
            handle_website,
            handle_media
        ]
        self.cache = {}

    async def resolve(self, url):
        if url in self.cache:
            print('yeah, from cache')
            return self.cache[url]

        client = AsyncHTTPClient()
        try:
            response = await client.fetch(url)
        except IOError as e:
            raise WebError('something', e)
        content_type = response.headers['Content-Type'].split(';', 1)[0]
        content = None
        for handler in self.handlers:
            content = await handler(response.effective_url, content_type, response.buffer)
            #print('handler', handler, 'returned', content)
            if content:
                break

        if content:
            self.cache[url] = content
            self.cache[response.effective_url] = content

        #print('result', content)
        return content

class Parser(HTMLParser):
    def __init__(self, **attrs):
        super().__init__()
        self.tags = {}

    def handle_starttag(self, tag, attrs):
        if tag != 'meta':
            return
        #prop = next((v for k, v in attrs if k == 'property' and v.startswith('og:')), False)
        key = next((v for k, v in attrs if k in ['property', 'name']), None)
        value = next((v for k, v in attrs if k in ['content']), None)
        if key and value:
            self.tags.setdefault(key, value)#next(v for k, v in attrs if k == 'content'))

        'image', 'video', 'audio', 'website', 'article'
        'X:type', 'X=url', 'og:description'
        #if tag == 'meta' and ('property', 'og:type') in attrs:
        #    print(tag, attrs)
        #if not self.url:
        #    prop = next((v for k, v in attrs if k == 'property' and v.startswith('og:')), False)
        #    if prop in ['og:image', 'og:video', 'og:audio', 'og:image:url', 'og:video:url', 'og:audio:url']:
        #        self.url = next(a[1] for a in attrs if a[0] == 'content')
        #        print(prop, self.url)

        #if prop:
        #    print(prop, next(a for a in attrs if a[0] == 'content'))
        #og_type = next(v for k, v in attrs if k == 'property')
        #if (tag == 'meta' and attrs['property'] == 'og:type'):

    # TODO: how to quit on end of head?
    #def handle_endtag(self, tag):
    #    if tag == 'head':
    #        self.reset()

async def handle_youtube(url, content_type, data):
    from urllib.parse import quote
    from urllib.parse import unquote
    # TODO does tornado already do this?
    #print('youtube A', url)
    url = unquote(url)
    #print('youtube B', url)
    if 'youtube.com' in url:
        # NOTE; get description + poster via API
        return WebContent(url, 'video/youtube')

async def handle_website(url, content_type, data):
    #print('handle_website', url)
    if (content_type == 'text/html'):
        data = data.read().decode('utf-8')
        parser = Parser()
        parser.feed(data)
        tags = parser.tags
        #print(tags)
        # TODO: parse meta tags no matter if OG
        if tags.get('og:type') in ['image', 'video', 'audio', 'website', 'article']:
            sub_tag = 'og:{}'.format(tags['og:type'])
            url = tags.get(sub_tag) or tags.get('{}:url'.format(sub_tag)) or tags.get('og:url')
            content_type = tags.get('{}:type'.format(sub_tag)) or 'text/html'
            description = tags.get('og:description') or tags.get('description')
            image_url = tags.get('og:image') or tags.get('og:image:url')
            width = tags.get('{}:width'.format(sub_tag))
            height = tags.get('{}:height'.format(sub_tag))
            size = None
            if width and height:
                size = (width, height)
            if url:
                return WebContent(url, content_type, description, image_url, size)
        else:
            return WebContent(url, content_type)
    return None

async def handle_media(url, content_type, data):
    print('handle_media', url)
    audio_types = ['audio/mp3', 'audio/mp4', 'audio/wav']
    if content_type in (IMAGE_TYPES + VIDEO_TYPES + audio_types):
        return WebContent(url, content_type)
    return None
