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

from micro import error
from micro.core import context
from .test_micro import MicroTestCase

class DevicesTest(MicroTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.devices = self.app.devices

    def test_getitem_as_user(self) -> None:
        device = self.user.devices[0]
        context.user.set(self.devices.sign_in().user)
        with self.assertRaises(error.PermissionError):
            # pylint: disable=pointless-statement; error raised on access
            self.devices[device.id]

    def test_authenticate(self) -> None:
        device = self.devices.authenticate(self.user.devices[0].auth_secret)
        self.assertEqual(device, self.user.devices[0])
        self.assertEqual(device.user, self.app.user)

    def test_authenticate_secret_invalid(self) -> None:
        with self.assertRaises(error.AuthenticationError):
            self.devices.authenticate('foo')

    def test_sign_in(self):
        device = self.devices.sign_in()
        user = device.user
        context.user.set(user)
        self.assertEqual(device, self.devices[device.id])
        self.assertEqual(user.devices[:], [device])
        self.assertIn(self.staff_member, self.app.settings.staff)
