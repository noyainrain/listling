# Open Listling
# Copyright (C) 2017 Open Listling contributors
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

"""Open Listling core."""

from micro import Application, Settings

class Listling(Application):
    """See :ref:`Listling`."""

    def create_settings(self):
        return Settings(
            id='Settings', trashed=False, app=self, authors=[], title='My Open Listling', icon=None,
            favicon=None, provider_name=None, provider_url=None, provider_description={},
            feedback_url=None, staff=[])
