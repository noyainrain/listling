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

"""Server templates."""

MESSAGE_TEMPLATES = {
    'email_auth': """
        Subject: [{{ app.settings.title }}] Add email address

        Hi there!

        Here is the verification code to add your email address to {{ app.settings.title }}:

        {{ auth }}

        ---

        If you did not request to add an email address to {{ app.settings.title }}, someone else may
        have entered your email address by mistake. In that case, please ignore this message, we
        will not bother you again.
    """
}
