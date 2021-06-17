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

# pylint: disable=missing-docstring; test module

from __future__ import annotations

import asyncio
from collections.abc import Callable
from tempfile import mkdtemp
from timeit import timeit

from micro.core import context

from listling import List, Listling

ITERATIONS = 100

def test_performance(name: str, f: Callable[[], object]) -> None:
    t = timeit(f, number=ITERATIONS)
    print(f'{name}: {t / ITERATIONS * 1000:.1f} ms ({ITERATIONS / t:.0f} / s)')

async def prepare_list(*, items: int = 0) -> List:
    app = Listling(redis_url='15', files_path=mkdtemp())
    app.r.flushdb()
    app.update()
    context.user.set(app.devices.sign_in().user)

    lst = app.lists.create('meeting-agenda')
    for i in range(items):
        await lst.items.create(f'Topic {i + 1}', value=i)
    return lst

async def main() -> None:
    lst = await prepare_list(items=100)
    test_performance('List.Items.json() for 10 item slc',
         lambda: lst.items.json(restricted=True, include=True, slc=slice(10)))

    lst = await prepare_list(items=100)
    test_performance('List.Items.json() for 100 item slc',
         lambda: lst.items.json(restricted=True, include=True, slc=slice(None)))

    lst = await prepare_list(items=10)
    test_performance('List.update_value_summary() for 10 items', lst.update_value_summary)

    lst = await prepare_list(items=1000)
    test_performance('List.update_value_summary() for 1000 items', lst.update_value_summary)

if __name__ == '__main__':
    asyncio.run(main())
