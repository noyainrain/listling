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
from configparser import ConfigParser
import json
import sys

from tornado.testing import gen_test

from micro import Application, CommunicationError, Event
from micro.tests.test_micro import MicroTestCase

class NotificationTest(MicroTestCase):
    def setUp(self):
        super().setUp()

        config = ConfigParser()
        config.read('test.cfg')
        if 'notification' not in config:
            self.skipTest('No notification test configuration')
        self.push_vapid_private_key = config['notification']['push_vapid_private_key']
        self.push_subscription = config['notification']['push_subscription']

        self.settings = self.app.settings
        self.settings.push_vapid_private_key = self.push_vapid_private_key

    @gen_test(timeout=20)
    async def test_notify(self):
        await self.user.enable_device_notifications(self.push_subscription)
        self.user.notify(Event.create('test', None, app=self.app))

    @gen_test(timeout=20)
    async def test_notify_invalid_push_subscription(self):
        await self.user.enable_device_notifications(self.push_subscription)
        self.user.push_subscription = 'foo'
        self.app.login()
        self.user.notify(Event.create('test', None, app=self.app))
        # Scheduled coroutines are run in the next IO loop iteration but one
        await sleep(0)
        await sleep(0)
        self.assertEqual(self.user.device_notification_status, 'off.expired')

    @gen_test(timeout=20)
    async def test_enable_device_notifications(self):
        await self.user.enable_device_notifications(self.push_subscription)
        self.assertEqual(self.user.device_notification_status, 'on')

    @gen_test(timeout=20)
    async def test_enable_device_notifications_invalid_push_subscription(self):
        push_subscription = json.loads(self.push_subscription)
        push_subscription['endpoint'] += 'foo'
        push_subscription = json.dumps(push_subscription)
        with self.assertRaisesRegex(ValueError, 'push_subscription_invalid'):
            await self.user.enable_device_notifications(push_subscription)
        self.assertEqual(self.user.device_notification_status, 'off')

    @gen_test(timeout=20)
    async def test_enable_device_notifications_invalid_push_subscription_host(self):
        push_subscription = json.dumps(
            {**json.loads(self.push_subscription), 'endpoint': 'http://example.invalid'})
        with self.assertRaises(CommunicationError):
            await self.user.enable_device_notifications(push_subscription)
        self.assertEqual(self.user.device_notification_status, 'off')

    @gen_test(timeout=20)
    async def test_disable_device_notifications(self):
        await self.user.enable_device_notifications(self.push_subscription)
        self.user.disable_device_notifications()
        self.assertEqual(self.user.device_notification_status, 'off')

CONFIG_TEMPLATE = """\
[notification]
push_vapid_private_key = {push_vapid_private_key}
push_subscription = {push_subscription}
"""

def main():
    app = Application()
    config = CONFIG_TEMPLATE.format(push_vapid_private_key=app.settings.push_vapid_private_key,
                                    push_subscription=app.settings.staff[0].push_subscription)
    print(config, end='')

if __name__ == '__main__':
    sys.exit(main())
