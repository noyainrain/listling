# Open Listling
# Copyright (C) 2019 Open Listling contributors
#
# This program is free software: you can redistribute it and/or modify it under the terms of the GNU
# Affero General Public License as published by the Free Software Foundation, either version 3 of
# the License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without
# even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU
# Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License along with this program.
# If not, see <https://www.gnu.org/licenses/>.

# pylint: disable=missing-docstring; test module

from micro import error
from micro.core import context

from .test_listling import ListlingTestCase

class OwnersTest(ListlingTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.owners = self.app.lists.create().owners

    def test_grant(self) -> None:
        user = self.app.login()
        self.owners.grant(user)
        self.assertEqual(list(self.owners), [user, self.user])
        self.assertIn(self.owners.object, user.lists)

    def test_grant_as_user(self) -> None:
        user = self.app.login()
        context.user.set(user)
        with self.assertRaises(error.PermissionError):
            self.owners.grant(user)

    def test_revoke(self) -> None:
        user = self.app.login()
        self.owners.grant(user)
        self.owners.revoke(user)
        self.assertEqual(list(self.owners), [self.user])

    def test_revoke_single(self) -> None:
        with self.assertRaisesRegex(error.ValueError, 'owners'):
            self.owners.revoke(self.user)

    def test_revoke_as_user(self) -> None:
        context.user.set(self.app.login())
        with self.assertRaises(error.PermissionError):
            self.owners.revoke(self.user)
