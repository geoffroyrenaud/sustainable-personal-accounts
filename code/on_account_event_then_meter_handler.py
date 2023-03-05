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
from time import time
from uuid import uuid4

from logger import setup_logging, trap_exception
setup_logging()

from datastore import Datastore
from events import Events

datastore = Datastore.get_instance()


@trap_exception
def handle_account_event(event, context, session=None):
    logging.debug(json.dumps(event))

    input = Events.decode_account_event(event)
    logging.debug(input)

    if input.label == 'CreatedAccount':
        handle_created_event(input, session)

    elif input.label == 'ExpiredAccount':
        handle_expired_event(input, session)

    elif input.label == 'ReleasedAccount':
        handle_released_event(input, session)

    else:
        logging.debug(f"Do not handle event '{input.label}'")

    return f"[OK] {input.label} {input.account}"


def handle_created_event(input, session=None):
    key = f"OnBoarding {input.account}"
    logging.info(f"Starting transaction '{key}'")
    transaction = {'begin': time(),
                   'identifier': str(uuid4())}
    datastore.assign(key, value=transaction)


def handle_expired_event(input, session=None):
    key = f"Maintenance {input.account}"
    logging.info(f"Starting transaction '{key}'")
    transaction = {'begin': time(),
                   'identifier': str(uuid4())}
    datastore.assign(key, value=transaction)


def handle_released_event(input, session=None):
    update_maintenance_transaction(input, session)
    update_onboarding_transaction(input, session)


def update_maintenance_transaction(input, session=None):
    key = f"Maintenance {input.account}"
    transaction = datastore.retrieve(key)
    if transaction:
        logging.info(f"Updating transaction '{key}'")
        datastore.assign(key, None)
        logging.debug(transaction)
        transaction['end'] = time()
        transaction['duration'] = transaction['end'] - transaction['begin']
        logging.debug(transaction)
        Events.emit_spa_event(label='SuccessfulMaintenanceEvent',
                              payload=transaction,
                              session=session)


def update_onboarding_transaction(input, session=None):
    key = f"OnBoarding {input.account}"
    transaction = datastore.retrieve(key)
    if transaction:
        logging.info(f"Updating transaction '{key}'")
        datastore.assign(key, None)
        logging.debug(transaction)
        transaction['end'] = time()
        transaction['duration'] = transaction['end'] - transaction['begin']
        logging.debug(transaction)
        Events.emit_spa_event(label='SuccessfulOnBoardingEvent',
                              payload=transaction,
                              session=session)
