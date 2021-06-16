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

"""Open Listling script."""

import sys

from micro.util import make_command_line_parser, setup_logging

from .server import make_server

def main(args):
    """Run Open Listling with the given list of command line *args*."""
    args = make_command_line_parser().parse_args(args[1:])
    if 'video_service_keys' in args:
        values = iter(args.video_service_keys)
        args.video_service_keys = dict(zip(values, values))
    setup_logging(getattr(args, 'debug', False))
    make_server(**vars(args)).run()
    return 0

if __name__ == '__main__':
    sys.exit(main(sys.argv))
