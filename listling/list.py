# Open Listling
# Copyright (C) 2021 Open Listling contributors
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

"""List functionality."""

from time import time
from typing import Dict, Optional, cast

from micro import Activity, Application, Collection, Event, Object, User, error
from micro.core import RewriteFunc, context
from micro.jsonredis import RedisSortedSet, script
from micro.util import randstr

class Owners(Collection[User]):
    """See Owners.

    .. attribute:: object

       Related object.

    .. attribute:: post_grant_script

       Subclass API: Redis script that is executed after :meth:`grant` with the corresponding
       *user_id*. *key* is the :attr:`RedisSequence.key`, *object_id* is the :attr:`Object.id` and
       *now* is the current time. May be ``None``.
    """

    post_grant_script: Optional[str] = None

    def __init__(self, obj: Object) -> None:
        super().__init__(RedisSortedSet(f'{obj.id}.owners', obj.app.r.r), app=obj.app)
        self.object = obj

    def grant(self, user: User) -> None:
        """See :http:post:`/api/(owners-url)`."""
        current_user = context.user.get()
        if not (current_user and current_user in self):
            raise error.PermissionError()

        f = script(self.app.r.r, f"""
            local key, user_id, object_id, now = KEYS[1], ARGV[1], ARGV[2], tonumber(ARGV[3])
            local n = redis.call("ZADD", key, "NX", -now, user_id)
            if n == 0 then
                return "owners"
            end
            {self.post_grant_script or ''}
            return "ok"
        """)
        if f([self.ids.key], [user.id, self.object.id, time()]).decode() == 'owners':
            raise error.ValueError(f'user {user.id} already in owners of object {self.object.id}')

        activity = getattr(self.object, 'activity')
        assert isinstance(activity, Activity)
        activity.publish(
            OwnersEvent(
                id=f'OwnersEvent:{randstr()}', type='object-owners-grant', object=self.object.id,
                user=current_user.id, time=self.app.now().isoformat(), detail={}, owner_id=user.id,
                app=self.app))

    def revoke(self, user: User) -> None:
        """See :http:delete:`/api/(owners-url)/(id)`."""
        current_user = context.user.get()
        if not (current_user and current_user in self):
            raise error.PermissionError()

        f = script(self.app.r.r, """
            local key, user_id = KEYS[1], ARGV[1]
            if redis.call("ZCARD", key) <= 1 then
                return "owners"
            end
            if redis.call("ZREM", key, user_id) == 0 then
                return "key"
            end
            return "ok"
        """)
        status = f([self.ids.key], [user.id]).decode()
        if status == 'owners':
            raise error.ValueError(f'Single owners of object {self.object.id}')
        if status == 'key':
            raise KeyError(user)

        activity = getattr(self.object, 'activity')
        assert isinstance(activity, Activity)
        activity.publish(
            OwnersEvent(
                id=f'OwnersEvent:{randstr()}', type='object-owners-revoke', object=self.object.id,
                user=current_user.id, time=self.app.now().isoformat(), detail={}, owner_id=user.id,
                app=self.app))

    def json(self, restricted: bool = False, include: bool = False, *, rewrite: RewriteFunc = None,
             slc: slice = None) -> Dict[str, object]:
        return {
            **super().json(restricted=restricted, include=include, rewrite=rewrite, slc=slc),
            **({'user_owner': context.user.get() in self} if include else {})
        }

class OwnersEvent(Event):
    """See OwnersEvent."""

    def __init__(self, *, app: Application, **data: object) -> None:
        super().__init__(
            id=cast(str, data['id']), type=cast(str, data['type']),
            object=cast(str, data['object']), user=cast(str, data['user']),
            time=cast(str, data['time']), detail=cast(Dict[str, object], data['detail']), app=app)
        self.owner_id = cast(str, data['owner_id'])

    @property
    def owner(self) -> User:
        # pylint: disable=missing-function-docstring; already documented
        return self.app.users[self.owner_id]

    def json(self, restricted: bool = False, include: bool = False, *,
             rewrite: RewriteFunc = None) -> Dict[str, object]:
        return {
            **super().json(restricted=restricted, include=include, rewrite=rewrite),
            'owner_id': self.owner_id,
            **(
                {'owner': self.owner.json(restricted=restricted, include=include, rewrite=rewrite)}
                if include else {})
        }
