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

"""Analytics functionality.

.. data: StatisticFunc

   Function of the form ``f(t)`` that computes a single statistic value. *t* is the current time.
"""

from asyncio import Task, ensure_future, sleep # pylint: disable=unused-import; typing
import json
from datetime import datetime, timedelta
import typing
from typing import Callable, Dict, Iterator, List, Mapping, Optional, cast
from urllib.parse import urlsplit

from . import error
from .jsonredis import RedisSortedSet
from .micro import Collection, Object, User
from .util import expect_type, parse_isotime, randstr

if typing.TYPE_CHECKING:
    from .micro import Application

StatisticFunc = Callable[[datetime], float]

class Analytics:
    """Analytics unit.

    .. attribute:: definitions

       Statistic definitions by topic.

    .. attribute:: statistics

       Statistics over time by topic.

    .. attribute:: referrals

       Referrals from other sites.

    .. attribute:: app

       Context application.
    """

    def __init__(self, *, definitions: Mapping[str, StatisticFunc] = {},
                 app: 'Application') -> None:
        self.definitions = {
            'users': self._count_users,
            'users-actual': self._count_users_actual,
            'users-active': self._count_users_active,
            **definitions
        } # type: Dict[str, StatisticFunc]
        self.statistics = {topic: Statistic(topic, app=app) for topic in self.definitions}
        self.referrals = Referrals(app=app)
        self.app = app

    def collect_statistics(self, *, _t: datetime = None) -> None:
        """Collect statistics for all topics."""
        t = _t or self.app.now()
        for topic, f in self.definitions.items():
            # pylint: disable=protected-access; Statistic is a friend
            self.statistics[topic]._add(Point(t, f(t))) # type: ignore

    def start_collect_statistics(self) -> 'Task[None]':
        """Start the collect statistics job."""
        async def _run() -> None:
            t = self.app.now().replace(hour=0, minute=15, second=0)
            while True:
                t += timedelta(days=1)
                await sleep((t - self.app.now()).total_seconds())
                self.collect_statistics(_t=t)
        return cast('Task[None]', ensure_future(_run()))

    def _count_users(self, t: datetime) -> float:
        # pylint: disable=unused-argument; part of API
        return len(self.app.users)

    def _count_users_actual(self, t: datetime) -> float:
        # pylint: disable=unused-argument; part of API
        return sum(1 for user in self._actual_users())

    def _count_users_active(self, t: datetime) -> float:
        return sum(1 for user in self._actual_users()
                   if t - user.authenticate_time <= timedelta(days=30)) # type: ignore

    def _actual_users(self) -> Iterator[User]:
        return (user for user in self.app.users[:] # type: ignore
                if user.authenticate_time - user.create_time >= timedelta(days=1)) # type: ignore

class Statistic:
    """See :ref:`Statistic`.

    .. attribute:: topic

       Topic the statistic is about.

    .. attribute:: app

       Context application.
    """

    def __init__(self, topic: str, *, app: 'Application') -> None:
        self.topic = topic
        self.app = app
        self._key = 'analytics.statistics.{}'.format(self.topic)

    def get(self, *, user: Optional[User]) -> List['Point']:
        """See :http:get:`/api/analytics/statistics/(topic)`."""
        if not user in self.app.settings.staff: # type: ignore
            raise PermissionError()
        return [Point.parse(json.loads(p.decode())) for p # type: ignore
                in self.app.r.r.zrange(self._key, 0, -1)] # type: ignore

    def json(self, *, user: User = None) -> Dict[str, object]:
        """See :meth:`micro.JSONifiable.json`."""
        return {'items': [p.json() for p in self.get(user=user)]}

    def _add(self, p):
        self.app.r.r.zadd(self._key, {json.dumps(p.json()): p.t.timestamp()})

class Point:
    """See :ref:`Point`."""

    def __init__(self, t: datetime, v: float) -> None:
        self.t = t
        self.v = v

    @staticmethod
    def parse(data: Dict[str, object]) -> 'Point':
        """See :meth:`micro.JSONifiableWithParse.parse`."""
        v = data.get('v')
        if not isinstance(v, (float, int)):
            raise TypeError()
        return Point(parse_isotime(expect_type(str)(data.get('t')), aware=True), float(v))

    def json(self) -> Dict[str, object]:
        """See :meth:`micro.JSONifiable.json`."""
        return {'t': self.t.isoformat(), 'v': self.v}

    def __eq__(self, other: object) -> bool:
        return isinstance(other, Point) and self.t == other.t and self.v == other.v

class Referral(Object):
    """See :ref:`Referral`."""

    def __init__(self, *, id: str, app: 'Application', url: str, time: str) -> None:
        super().__init__(id=id, app=app)
        self.url = url
        self.time = parse_isotime(time, aware=True)

    def json(self, restricted: bool = False, include: bool = False) -> Dict[str, object]:
        return {
            **super().json(restricted=restricted, include=include),
            'url': self.url,
            'time': self.time.isoformat()
        }

class Referrals(Collection[Referral]):
    """See :ref:`Referrals`."""

    def __init__(self, *, app: 'Application') -> None:
        super().__init__(RedisSortedSet('analytics.referrals', app.r.r),
                         check=lambda key: self.app.check_user_is_staff(), app=app) # type: ignore

    def add(self, url: str, *, user: Optional[User]) -> Referral:
        """See :http:post:`/api/analytics/referrals`."""
        # pylint: disable=unused-argument; part of API
        if urlsplit(url).scheme not in {'http', 'https'}:
            raise error.ValueError('Bad url scheme {}'.format(url))
        referral = Referral(id=randstr(), app=self.app, url=url, time=self.app.now().isoformat())
        self.app.r.oset(referral.id, referral)
        self.app.r.r.zadd(self.ids.key, {referral.id.encode(): -referral.time.timestamp()})
        return referral
