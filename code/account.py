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

from enum import Enum, unique
import json
import logging
import os
from types import SimpleNamespace
import re

from boto3.session import Session

from session import make_session


@unique
class State(Enum):  # value is given to tag 'account:state'
    VANILLA = 'vanilla'
    ASSIGNED = 'assigned'
    RELEASED = 'released'
    EXPIRED = 'expired'


class Account:
    VALID_EMAIL = re.compile(r'([A-Za-z0-9]+[.-_])*[A-Za-z0-9]+@[A-Za-z0-9-]+(\.[A-Z|a-z]{2,})+')

    @classmethod
    def get_session(cls):
        role = os.environ.get('ROLE_ARN_TO_MANAGE_ACCOUNTS')
        return make_session(role_arn=role) if role else Session()

    @classmethod
    def validate_tags(cls, account, session=None):
        tags = cls.list_tags(account, session=session)
        if 'account:owner' not in tags.keys():
            raise ValueError(f"Missing tag 'account:owner' on account '{account}' - this account can not be assigned")
        if not cls.validate_owner(tags['account:owner']):
            raise ValueError(f"Invalid value for tag 'account:owner' on account '{account}' - this account can not be assigned")
        if 'account:state' not in tags.keys():
            raise ValueError(f"Missing tag 'account:state' on account '{account}' - this account can not be assigned")
        if not cls.validate_state(tags['account:state']):
            raise ValueError(f"Invalid value for tag 'account:state' on account '{account}' - this account can not be assigned")

    @classmethod
    def validate_owner(cls, text):
        return re.fullmatch(cls.VALID_EMAIL, text)

    @classmethod
    def validate_state(cls, text):
        return text in [state.value for state in State]

    @classmethod
    def list_tags(cls, account, session=None):
        tags = {}
        for item in cls.iterate_tags(account, session):
            tags[item.get('Key')] = item.get('Value')
        return tags

    @classmethod
    def iterate_tags(cls, account, session=None):
        session = session or cls.get_session()

        token = None
        while True:
            logging.debug(f"Listing tags for account '{account}'")
            parameters = dict(ResourceId=account)
            if token:
                parameters['NextToken'] = token
            chunk = session.client('organizations').list_tags_for_resource(**parameters)

            for item in chunk['Tags']:
                logging.debug(json.dumps(item))
                yield item

            token = chunk.get('NextToken')
            if not token:
                break

    @classmethod
    def move(cls, account, state: State, session=None):
        if not isinstance(state, State):
            raise ValueError(f"Unexpected state type {state}")

        logging.info(f"Tagging account '{account}' with state '{state.value}'...")
        if os.environ.get("DRY_RUN") == "FALSE":
            session = session or cls.get_session()
            session.client('organizations').tag_resource(
                ResourceId=account,
                Tags=[dict(Key='account:state', Value=state.value)])
            logging.info("Done")
        else:
            logging.warning("Dry-run mode - account has not been tagged")

    @classmethod
    def list(cls, parent, session=None):
        session = session or cls.get_session()
        token = None
        while True:
            logging.debug(f"Listing accounts in parent '{parent}'")
            parameters = dict(ParentId=parent,
                              MaxResults=50)
            if token:
                parameters['NextToken'] = token
            chunk = session.client('organizations').list_accounts_for_parent(**parameters)

            for item in chunk['Accounts']:
                logging.debug(json.dumps(item))
                yield item['Id']

            token = chunk.get('NextToken')
            if not token:
                break

    @classmethod
    def describe(cls, id, session=None):
        session = session or cls.get_session()
        item = SimpleNamespace(id=id)
        attributes = session.client('organizations').describe_account(AccountId=id)['Account']
        item.arn = attributes['Arn']
        item.email = attributes['Email']
        item.name = attributes['Name']
        item.is_active = True if attributes['Status'] == 'ACTIVE' else False
        item.tags = cls.list_tags(account=id, session=session)
        return item
