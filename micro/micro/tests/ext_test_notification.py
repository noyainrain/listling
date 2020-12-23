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

# pylint: disable=missing-docstring; test module

from asyncio import sleep
from configparser import ConfigParser
import json
from typing import Dict, cast

from tornado.testing import gen_test

from micro import Application, Event
from micro.core import context
from micro.tests.test_micro import MicroTestCase
from micro.webapi import CommunicationError

class NotificationTestCase(MicroTestCase):
    def setUp(self) -> None:
        super().setUp()

        config = ConfigParser()
        config.read('test.cfg')
        if 'notification' not in config:
            self.skipTest('No notification test configuration')
        self.push_vapid_private_key = config['notification']['push_vapid_private_key']
        self.push_subscription = config['notification']['push_subscription']

        self.settings = self.app.settings
        self.settings.push_vapid_private_key = self.push_vapid_private_key

class UserNotificationTest(NotificationTestCase):
    @gen_test(timeout=20) # type: ignore[misc]
    async def test_notify(self) -> None:
        await self.user.devices[0].enable_notifications(self.push_subscription)
        self.user.notify(Event.create('test', None, app=self.app))

    @gen_test(timeout=20) # type: ignore[misc]
    async def test_notify_invalid_push_subscription(self) -> None:
        device = self.user.devices[0]
        await device.enable_notifications(self.push_subscription)
        device.push_subscription = 'foo'
        context.user.set(self.app.devices.sign_in().user)
        self.user.notify(Event.create('test', None, app=self.app))
        # Scheduled coroutines are run in the next IO loop iteration but one
        await sleep(0)
        await sleep(0)
        self.assertEqual(device.notification_status, 'off.expired')

class DeviceNotificationTest(NotificationTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.device = self.user.devices[0]

    @gen_test(timeout=20) # type: ignore[misc]
    async def test_enable_notifications(self) -> None:
        await self.device.enable_notifications(self.push_subscription)
        self.assertEqual(self.device.notification_status, 'on')

    @gen_test(timeout=20) # type: ignore[misc]
    async def test_disable_notifications(self) -> None:
        await self.device.enable_notifications(self.push_subscription)
        self.device.disable_notifications()
        self.assertEqual(self.device.notification_status, 'off')

class ApplicationNotificationTest(NotificationTestCase):
    @gen_test(timeout=20) # type: ignore[misc]
    async def test_send_device_notification(self) -> None:
        await self.app.send_device_notification(self.push_subscription,
                                                Event.create('meow', None, app=self.app))

    @gen_test(timeout=20) # type: ignore[misc]
    async def test_send_device_notification_invalid_push_subscription(self) -> None:
        push_subscription = cast(Dict[str, str], json.loads(self.push_subscription))
        push_subscription['endpoint'] += 'foo'
        push_subscription = json.dumps(push_subscription)
        with self.assertRaisesRegex(ValueError, 'push_subscription_invalid'):
            await self.app.send_device_notification(push_subscription,
                                                    Event.create('meow', None, app=self.app))

    @gen_test(timeout=20) # type: ignore[misc]
    async def test_send_device_notification_invalid_push_subscription_host(self) -> None:
        push_subscription = json.dumps({ # type: ignore[misc]
            **cast(Dict[str, str], json.loads(self.push_subscription)),
            'endpoint': 'http://example.invalid'
        })
        with self.assertRaises(CommunicationError):
            await self.app.send_device_notification(push_subscription,
                                                    Event.create('meow', None, app=self.app))

CONFIG_TEMPLATE = """\
[notification]
push_vapid_private_key = {push_vapid_private_key}
push_subscription = {push_subscription}
"""

def main() -> None:
    app = Application()
    user = app.settings.staff[0]
    context.user.set(user)
    config = CONFIG_TEMPLATE.format(push_vapid_private_key=app.settings.push_vapid_private_key,
                                    push_subscription=user.devices[0].push_subscription)
    print(config, end='')

if __name__ == '__main__':
    main()
