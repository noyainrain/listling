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

"""Toolkit for social micro web apps.

micro is based on Redis and thus any method may raise a :exc:`RedisError` if there is a problem
communicating with the Redis server.
"""

import os

from micro.micro import (
    Application, Object, Gone, Editable, Trashable, Collection, Orderable, User, Settings, Activity,
    Event, AuthRequest, Location, InputError, EmailError, WithContent)

DOC_PATH = os.path.join(os.path.dirname(__file__), 'doc')
