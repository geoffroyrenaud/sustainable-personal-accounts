#!/usr/bin/env python3
"""
Copyright Reply.com or its affiliates. All Rights Reserved.
SPDX-License-Identifier: Apache-2.0
Permission is hereby granted, free of charge, to any person obtaining a copy of this
software and associated documentation files (the "Software"), to deal in the Software
without restriction, including without limitation the rights to use, copy, modify,
merge, publish, distribute, sublicense, and/or sell copies of the Software, and to
permit persons to whom the Software is furnished to do so.
THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED,
INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A
PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT
HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION
OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE
SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
"""

import json
import logging

from logger import setup_logging, trap_exception
setup_logging()

from account import Account, State
from session import get_organizational_units


@trap_exception
def handle_event(event, context, session=None):
    logging.debug(json.dumps(event))

    units = get_organizational_units()
    for unit in units.keys():
        for account in Account.list(parent=unit, session=session):

            item = Account.describe(account)

            if not item.is_active:
                logging.debug(f"Ignoring inactive account '{account}'")
                continue

            if item.tags.get('account:state') != State.RELEASED:
                logging.debug(f"Ignoring account '{account}' that has not been released")
                continue

            logging.info(f"Expiring account '{account}'")
            Account.move(account=account, state=State.EXPIRED)
