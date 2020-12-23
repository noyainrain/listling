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

# type: ignore
# pylint: disable=missing-docstring; test module

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from micro.analytics import Point
from micro.tests.test_micro import MicroTestCase

class AnalyticsTest(MicroTestCase):
    now = None # type: datetime

    def _now() -> datetime: # type: ignore
        # pylint: disable=no-method-argument; patch rejects static methods (see
        # https://bugs.python.org/issue23078)
        return AnalyticsTest.now

    @patch('micro.Application.now', side_effect=_now)
    def setUp(self, now) -> None:
        # pylint: disable=unused-argument,arguments-differ; part of API
        AnalyticsTest.now = datetime(2015, 8, 27, 16, 56, 23, tzinfo=timezone.utc)
        super().setUp()

    @patch('micro.Application.now', side_effect=_now)
    def test_collect_statistics(self, now) -> None:
        # pylint: disable=unused-argument; part of API
        timeline = [AnalyticsTest.now, AnalyticsTest.now + timedelta(days=2),
                    AnalyticsTest.now + timedelta(days=33)]

        self.app.analytics.collect_statistics()
        AnalyticsTest.now = timeline[1]
        self.app.devices.authenticate(self.user.devices[0].auth_secret)
        self.app.analytics.collect_statistics()
        AnalyticsTest.now = timeline[2]
        self.app.devices.sign_in()
        self.app.analytics.collect_statistics()

        users = [Point(timeline[0], 2), Point(timeline[1], 2), Point(timeline[2], 3)]
        users_actual = [Point(timeline[0], 0), Point(timeline[1], 1), Point(timeline[2], 1)]
        users_active = [Point(timeline[0], 0), Point(timeline[1], 1), Point(timeline[2], 0)]
        self.assertEqual(self.app.analytics.statistics['users'].get(user=self.staff_member), users)
        self.assertEqual(self.app.analytics.statistics['users-actual'].get(user=self.staff_member),
                         users_actual)
        self.assertEqual(self.app.analytics.statistics['users-active'].get(user=self.staff_member),
                         users_active)

class ReferralsTest(MicroTestCase):
    def test_add(self) -> None:
        referral = self.app.analytics.referrals.add('https://example.org/', user=self.user)
        self.assertEqual(referral.url, 'https://example.org/')
        self.assertIn(referral.id, self.app.analytics.referrals)

    def test_summarize(self) -> None:
        self.app.user = self.staff_member
        ten_days_ago = self.app.now() - timedelta(days=10)
        with patch.object(self.app, 'now', return_value=ten_days_ago):
            self.app.analytics.referrals.add('https://example.org/', user=self.user)
        self.app.analytics.referrals.add('https://example.org/foo', user=self.user)
        self.app.analytics.referrals.add('https://example.org/foo', user=self.user)
        self.app.analytics.referrals.add('https://example.org/bar', user=self.user)

        summary = self.app.analytics.referrals.summarize()

        self.assertEqual(len(summary), 2)
        self.assertEqual(summary[0], ('https://example.org/foo', 2))
        self.assertEqual(summary[1], ('https://example.org/bar', 1))

    def test_summarize_period(self) -> None:
        self.app.user = self.staff_member
        earlier = self.app.now() - timedelta(minutes=2)
        with patch.object(self.app, 'now', return_value=earlier):
            self.app.analytics.referrals.add('https://example.org/', user=self.user)
        self.app.analytics.referrals.add('https://example.org/foo', user=self.user)
        self.app.analytics.referrals.add('https://example.org/foo', user=self.user)
        self.app.analytics.referrals.add('https://example.org/bar', user=self.user)

        later = earlier + timedelta(minutes=1)
        future = self.app.now() + timedelta(minutes=1)
        summary = self.app.analytics.referrals.summarize((later, future))

        self.assertEqual(len(summary), 2)
        self.assertEqual(summary[0], ('https://example.org/foo', 2))
        self.assertEqual(summary[1], ('https://example.org/bar', 1))
