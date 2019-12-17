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

# pylint: disable=missing-docstring; test module

from asyncio import sleep
from datetime import timedelta, timezone
import subprocess
from tempfile import mkdtemp
from unittest.mock import Mock, patch

from typing import List, Tuple, cast

from redis.exceptions import RedisError
from tornado.testing import AsyncTestCase, gen_test

import micro
from micro import Activity, Collection, Event, Gone, Location, Trashable, WithContent
from micro.jsonredis import RedisList
from micro.resource import Analyzer, Resource
from micro.test import CatApp, Cat
from micro.util import ON

SETUP_DB_SCRIPT = """\
from time import sleep

from micro.test import CatApp

# Forward compatibility for redis-py 3 (deprecated since 0.30.0)
redis_url = 'redis://localhost/15'

app = CatApp(redis_url=redis_url)
app.r.flushdb()
app.update()
app.sample()

# Compatibility for unmigrated global activity data (deprecated since 0.24.1)
from micro import Event
event = Event.create('meow', None, app=app)
if int(app.r.get('micro_version')) == 6:
    app.r.oset(event.id, event)
    app.r.lpush('activity', event.id)
else:
    app.activity.publish(event)

# Events at different times
app.settings.edit(provider_name='Meow Inc.')
sleep(1)
app.settings.edit(provider_url='https://meow.example.com/')

# Compatibility for app without cats (deprecated since 0.6.0)
if not hasattr(app, 'cats'):
    from micro.test import Cat
    app.r.oset('Cat:0', Cat(id='Cat:0', trashed=False, app=app, authors=[], name=None))
    app.r.oset('Cat:1', Cat(id='Cat:1', trashed=True, app=app, authors=[], name=None))
    app.r.rpush('cats', 'Cat:0', 'Cat:1')
else:
    app.cats.create()
    app.cats.create().trash()

# User without activity
app.login()
"""

class MicroTestCase(AsyncTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.app = CatApp(redis_url='15')
        self.app.r.flushdb()
        self.app.update() # type: ignore
        self.staff_member = self.app.login() # type: ignore
        self.user = self.app.login() # type: ignore

class ApplicationTest(MicroTestCase):
    def test_init_redis_url_invalid(self):
        with self.assertRaisesRegex(micro.ValueError, 'redis_url_invalid'):
            CatApp(redis_url='//localhost:foo')

    def test_authenticate(self):
        user = self.app.authenticate(self.user.auth_secret)
        self.assertEqual(user, self.user)
        self.assertEqual(user, self.app.user)

    def test_authenticate_secret_invalid(self):
        with self.assertRaises(micro.AuthenticationError):
            self.app.authenticate('foo')

    def test_login(self):
        # login() is called by setUp()
        self.assertIn(self.user.id, self.app.users)
        self.assertEqual(self.user, self.app.user)
        self.assertIn(self.staff_member, self.app.settings.staff)

    def test_login_no_redis(self):
        app = CatApp(redis_url='//localhost:16160')
        with self.assertRaises(RedisError):
            app.login()

    def test_login_code(self):
        user = self.app.login(code=self.staff_member.auth_secret)
        self.assertEqual(user, self.staff_member)

    def test_login_code_invalid(self):
        with self.assertRaisesRegex(micro.ValueError, 'code_invalid'):
            self.app.login(code='foo')

class ApplicationUpdateTest(AsyncTestCase):
    @staticmethod
    def setup_db(tag: str) -> None:
        d = mkdtemp()
        clone = ['git', '-c', 'advice.detachedHead=false', 'clone', '-q', '--single-branch',
                 '--branch', tag, '.', d]
        subprocess.run(clone, check=True)
        subprocess.run(cast(List[str], ['python3', '-c', SETUP_DB_SCRIPT]), cwd=d, check=True)

    def test_update_db_fresh(self):
        app = CatApp(redis_url='15')
        app.r.flushdb()
        app.update()
        self.assertEqual(app.settings.title, 'CatApp')

    @gen_test
    async def test_update_db_version_previous(self) -> None:
        self.setup_db('0.38.1')
        await sleep(1)
        app = CatApp(redis_url='15')
        app.update() # type: ignore

        app.user = app.settings.staff[0]
        first = app.activity[-1].time.replace(tzinfo=timezone.utc)
        last = app.cats[1].activity[0].time.replace(tzinfo=timezone.utc)
        self.assertEqual(app.user.create_time, first)
        self.assertEqual(app.user.authenticate_time, last)
        user = app.users[1]
        self.assertEqual(user.create_time, user.authenticate_time)
        self.assertAlmostEqual(user.create_time, app.now(), delta=timedelta(minutes=1))
        self.assertGreater(user.create_time, last)

    @gen_test
    async def test_update_db_version_first(self):
        Trashable.RETENTION = timedelta(seconds=0.2)
        # NOTE: Tag tmp can be removed on next database update
        self.setup_db('tmp')
        await sleep(1)
        app = CatApp(redis_url='15')
        app.update()

        # Update to version 3
        self.assertFalse(app.settings.provider_description)
        # Update to version 4
        self.assertNotIn('trashed', app.settings.json())
        self.assertFalse(app.cats[0].trashed)
        # Update to version 5
        self.assertFalse(hasattr(app.settings, 'favicon'))
        self.assertIsNone(app.settings.icon_small)
        self.assertIsNone(app.settings.icon_large)
        # Update to version 6
        user = app.settings.staff[0]
        self.assertTrue(app.settings.push_vapid_private_key)
        self.assertTrue(app.settings.push_vapid_public_key)
        self.assertIsNotNone(app.activity.subscribers)
        self.assertEqual(user.device_notification_status, 'off')
        self.assertIsNone(user.push_subscription)
        # Update to version 7
        app.user = app.settings.staff[0]
        self.assertEqual([event.type for event in app.activity],
                         ['editable-edit', 'editable-edit', 'meow'])
        # Update to version 8
        cats = list(app.cats.values())
        app.start_empty_trash()
        await sleep(0.1)
        self.assertEqual(list(app.cats.values()), cats)
        await sleep(0.3)
        self.assertEqual(list(app.cats.values()), cats[:1])
        # Update to version 9
        first = app.activity[-1].time.replace(tzinfo=timezone.utc)
        last = app.activity[0].time.replace(tzinfo=timezone.utc)
        self.assertEqual(app.user.create_time, first)
        self.assertEqual(app.user.authenticate_time, last)
        user = app.users[1]
        self.assertEqual(user.create_time, user.authenticate_time)
        self.assertAlmostEqual(user.create_time, app.now(), delta=timedelta(minutes=1))
        self.assertGreater(user.create_time, last)

class EditableTest(MicroTestCase):
    def setUp(self):
        super().setUp()
        self.cat = self.app.cats.create()

    def test_edit(self):
        self.cat.edit(name='Happy')
        self.cat.edit(name='Grumpy')
        user2 = self.app.login()
        self.cat.edit(name='Hover')
        self.assertEqual(self.cat.authors, [self.user, user2])

    def test_edit_cat_trashed(self):
        self.cat.trash()
        with self.assertRaisesRegex(micro.ValueError, 'object_trashed'):
            self.cat.edit(name='Happy')

    def test_edit_user_anonymous(self):
        self.app.user = None
        with self.assertRaises(micro.PermissionError):
            self.cat.edit(name='Happy')

@patch('micro.test.Cat.delete', autospec=True)
class TrashableTest(MicroTestCase):
    def setUp(self) -> None:
        super().setUp()
        Trashable.RETENTION = timedelta(seconds=0.2)
        self.app.start_empty_trash()

    @gen_test # type: ignore
    async def test_trash(self, delete: Mock) -> None:
        cat = self.app.cats.create()
        cat.trash()
        self.assertTrue(cat.trashed)
        self.assertEqual(cast(Event, cat.activity[0]).type, 'trashable-trash')
        await sleep(0.1)
        # Work around missing assert_not_called() (see https://bugs.python.org/issue28380)
        self.assertEqual(delete.call_count, 0) # type: ignore
        await sleep(0.3)
        delete.assert_called_once_with(cat) # type: ignore

    def test_trash_trashed(self, delete: Mock) -> None:
        # pylint: disable=unused-argument; patch
        cat = self.app.cats.create()
        cat.trash()
        cat.trash()
        self.assertTrue(cat.trashed)
        self.assertEqual(len(cat.activity), 1)

    @gen_test # type: ignore
    async def test_restore(self, delete: Mock) -> None:
        cat = self.app.cats.create()
        cat.trash()
        cat.restore()
        self.assertFalse(cat.trashed)
        self.assertEqual(cast(Event, cat.activity[0]).type, 'trashable-restore')
        await sleep(0.3)
        self.assertEqual(delete.call_count, 0) # type: ignore

async def _analyze(self: Analyzer, url: str) -> Resource:
    # pylint: disable=unused-argument; part of API
    return Resource(url, content_type='text/html')

@patch('micro.resource.Analyzer.analyze', autospec=True, side_effect=_analyze) # type: ignore
class WithContentTest(MicroTestCase):
    @gen_test # type: ignore
    async def test_process_attrs(self, analyze) -> None:
        # pylint: disable=unused-argument; part of API
        attrs = await WithContent.process_attrs({'text': '  ', 'resource': 'http://example.org/'},
                                                app=self.app)
        self.assertIsNone(attrs['text'])
        resource = attrs.get('resource')
        assert isinstance(resource, Resource)
        self.assertEqual(resource.url, 'http://example.org/')

    @gen_test # type: ignore
    async def test_edit(self, analyze) -> None:
        # pylint: disable=unused-argument; part of API
        cat = self.app.cats.create()
        await cat.edit(resource='http://example.org/', asynchronous=ON)
        await cat.edit(text='Meow!', resource='http://example.org/', asynchronous=ON)
        self.assertEqual(cat.text, 'Meow!')
        assert cat.resource
        self.assertEqual(cat.resource.url, 'http://example.org/')

class CollectionTest(MicroTestCase):
    def make_cats(self, *, check=None):
        objects = [Cat.make(name='Happy', app=self.app), Cat.make(name='Grumpy', app=self.app),
                   Cat.make(name='Long', app=self.app), Cat.make(name='Monorail', app=self.app)]
        self.app.r.omset({cat.id: cat for cat in objects})
        self.app.r.rpush('cats', *(cat.id for cat in objects))
        cats = Collection(RedisList('cats', self.app.r.r), check=check, app=self.app)
        return cats, objects

    def test_index(self):
        cats, objects = self.make_cats()
        self.assertEqual(cats.index(objects[2]), objects.index(objects[2]))

    def test_len(self):
        cats, objects = self.make_cats()
        self.assertEqual(len(cats), len(objects))

    def test_getitem(self):
        cats, objects = self.make_cats()
        self.assertEqual(cats[1], objects[1])

    def test_getitem_slice(self):
        cats, objects = self.make_cats()
        self.assertEqual(cats[1:3], objects[1:3])

    def test_getitem_id(self):
        cats, objects = self.make_cats()
        self.assertEqual(cats[objects[0].id], objects[0])

    def test_getitem_missing_id(self):
        cats, _ = self.make_cats()
        with self.assertRaises(KeyError):
            # pylint: disable=pointless-statement; error raised on access
            cats['foo']

    def test_getitem_check(self):
        check = Mock()
        cats, _ = self.make_cats(check=check)
        # pylint: disable=pointless-statement; check called on access
        cats[1]
        check.assert_called_once_with(1)

    def test_iter(self):
        cats, objects = self.make_cats()
        self.assertEqual(list(iter(cats)), [obj.id for obj in objects])

    def test_contains(self):
        cats, objects = self.make_cats()
        self.assertTrue(objects[1] in cats)

    def test_contains_missing_item(self):
        cats, _ = self.make_cats()
        self.assertFalse(Cat.make(app=self.app) in cats)

class OrderableTest(MicroTestCase):
    def make_cats(self):
        return [self.app.cats.create(), self.app.cats.create(), self.app.cats.create()]

    def test_move(self):
        cats = self.make_cats()
        self.app.cats.move(cats[1], cats[2])
        self.assertEqual(list(self.app.cats.values()), [cats[0], cats[2], cats[1]])

    def test_move_to_none(self):
        cats = self.make_cats()
        self.app.cats.move(cats[1], None)
        self.assertEqual(list(self.app.cats.values()), [cats[1], cats[0], cats[2]])

    def test_move_to_item(self):
        cats = self.make_cats()
        self.app.cats.move(cats[1], cats[1])
        self.assertEqual(list(self.app.cats.values()), cats)

    def test_move_item_external(self):
        cats = self.make_cats()
        external = Cat.make(app=self.app)
        with self.assertRaisesRegex(micro.ValueError, 'item_not_found'):
            self.app.cats.move(external, cats[0])

    def test_move_to_external(self):
        cats = self.make_cats()
        external = Cat.make(app=self.app)
        with self.assertRaisesRegex(micro.ValueError, 'to_not_found'):
            self.app.cats.move(cats[0], external)

class UserTest(MicroTestCase):
    def test_edit(self):
        self.user.edit(name='Happy')
        self.assertEqual(self.user.name, 'Happy')

class ActivityTest(MicroTestCase):
    def make_activity(self) -> Activity:
        return Activity('Activity:more', self.app, subscriber_ids=[])

    @patch('micro.User.notify', autospec=True) # type: ignore
    def test_publish(self, notify):
        activity = self.make_activity()
        activity.subscribe()
        self.app.login()
        activity.subscribe()

        event = Event.create('meow', None, app=self.app)
        activity.publish(event)
        self.assertIn(event, activity)
        notify.assert_called_once_with(self.user, event)

    @gen_test
    async def test_publish_stream(self) -> None:
        activity = self.make_activity()
        stream = activity.stream()

        observed = []
        closed = False
        async def observe() -> None:
            nonlocal closed
            async for event in stream:
                observed.append(event)
            closed = True
        self.io_loop.add_callback(observe)
        # Scheduled coroutines are run in the next IO loop iteration but one
        await sleep(0)
        await sleep(0)

        events = [
            Event.create('meow', None, app=self.app), # type:ignore
            Event.create('woof', None, app=self.app) # type:ignore
        ] # type: List[Event]
        activity.publish(events[0]) # type:ignore
        activity.publish(events[1]) # type:ignore
        await sleep(0)
        await stream.aclose()
        await sleep(0)

        self.assertEqual(observed, events)
        self.assertTrue(closed)

    def test_subscribe(self):
        activity = self.make_activity()
        activity.subscribe()
        self.assertIn(self.user, activity.subscribers)

    def test_unsubscribe(self):
        activity = self.make_activity()
        activity.subscribe()
        activity.unsubscribe()
        self.assertNotIn(self.user, activity.subscribers)

class EventTest(MicroTestCase):
    def make_event(self) -> Tuple[Event, Cat]:
        cat = self.app.cats.create()
        event = Event.create('meow', cat, app=self.app)
        return event, cat

    def test_get_object(self) -> None:
        event, cat = self.make_event()
        self.assertEqual(event.object, cat)

    def test_get_object_deleted(self) -> None:
        event, cat = self.make_event()
        cat.delete()
        # Break reference cycle
        cat.activity.host = None
        del cat
        self.assertIsInstance(event.object, Gone)

class LocationTest(MicroTestCase):
    def test_parse(self):
        # coords may be float or int
        location = Location.parse({'name': 'Berlin', 'coords': [52.504043, 13]})
        self.assertEqual(location.name, 'Berlin')
        self.assertEqual(location.coords, (52.504043, 13))
