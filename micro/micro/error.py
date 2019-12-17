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

"""micro errors."""

import builtins
from typing import Dict, Tuple, cast

from . import webapi

class Error(Exception):
    """Base for micro errors."""

    def json(self) -> Dict[str, object]:
        """Return a JSON representation of the error."""
        return {'__type__': type(self).__name__, 'message': str(self)}

class ValueError(builtins.ValueError, Error):
    """See :ref:`ValueError`.

    The first item of *args* is also available as *code*.
    """

    @property
    def code(self) -> object:
        # pylint: disable=missing-docstring; already documented
        return (cast(Tuple[object, ...], self.args)[0] if cast(Tuple[object, ...], self.args)
                else None)

    def json(self) -> Dict[str, object]:
        # Compatibility for code (deprecated since 0.27.0)
        return {**super().json(), 'code': self.code}

class CommunicationError(Error):
    """See :ref:`CommunicationError`.

    .. deprecated:: 0.28.0

       Use :exc:`webapi.CommunicationError` instead.
    """
# Compatibility for micro CommunicationError (deprecated since 0.28.0)
webapi.CommunicationError = CommunicationError # type: ignore
