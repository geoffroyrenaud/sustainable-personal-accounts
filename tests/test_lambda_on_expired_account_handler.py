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

import logging
logging.getLogger('botocore').setLevel(logging.CRITICAL)
logging.getLogger('urllib3').setLevel(logging.CRITICAL)

from boto3.session import Session
import json
from unittest.mock import patch
from moto import mock_events, mock_ssm
import os
import pytest
from types import SimpleNamespace

from lambdas import Events, State
from lambdas.on_expired_account_handler import handle_tag_event

# pytestmark = pytest.mark.wip
from account import Account  # accessible from  monkeypatch
from worker import Worker    # accessible from monkeypatch


def given_some_context(prefix='/Fake/'):

    session = Session(aws_access_key_id='testing',
                      aws_secret_access_key='testing',
                      aws_session_token='testing',
                      region_name='eu-west-1')

    context = SimpleNamespace(session=session)

    context.settings_123456789012 = {
        'account_tags': {'CostCenter': 'abc', 'Sponsor': 'Foo Bar'},
        'identifier': '123456789012',
        'note': 'a specific account',
        'preparation': {
            'feature': 'enabled',
            'variables': {'HELLO': 'WORLD'}
        },
        'purge': {
            'feature': 'enabled',
            'variables': {'DRY_RUN': 'TRUE'}
        }
    }
    session.client('ssm').put_parameter(Name=prefix + 'Accounts/123456789012',
                                        Value=json.dumps(context.settings_123456789012),
                                        Type='String')

    context.settings_567890123456 = {
        'account_tags': {'CostCenter': 'abc', 'Sponsor': 'Foo Bar'},
        'identifier': '567890123456',
        'note': 'another specific account',
        'preparation': {
            'feature': 'disabled',
            'variables': {'HELLO': 'MOON'}
        },
        'purge': {
            'feature': 'disabled',
            'variables': {'DRY_RUN': 'TRUE'}
        }
    }
    session.client('ssm').put_parameter(Name=prefix + 'Accounts/567890123456',
                                        Value=json.dumps(context.settings_567890123456),
                                        Type='String')

    session.client('ssm').put_parameter(Name='buildspec',
                                        Value='some text',
                                        Type='String')

    return context


@pytest.mark.integration_tests
@patch.dict(os.environ, dict(ACCOUNTS_PARAMETER="Accounts",
                             AWS_DEFAULT_REGION='eu-west-1',
                             PURGE_BUILDSPEC_PARAMETER="buildspec",
                             ENVIRONMENT_IDENTIFIER='Fake',
                             EVENT_BUS_ARN='arn:aws',
                             ORGANIZATIONAL_UNITS_PARAMETER="OrganizationalUnits",
                             VERBOSITY='DEBUG'))
@mock_events
@mock_ssm
def test_handle_tag_event(monkeypatch):
    context = given_some_context(prefix="/{}/".format(os.environ['ENVIRONMENT_IDENTIFIER']))

    # purge has been enabled on "123456789012"
    processed = []

    def mock_worker_purge(account_id, *args, **kwargs):
        processed.append(account_id)

    monkeypatch.setattr(Worker, 'purge', mock_worker_purge)

    event = Events.load_event_from_template(template="fixtures/events/tag-account-template.json",
                                            context=dict(account="123456789012",
                                                         new_state=State.EXPIRED.value))
    result = handle_tag_event(event=event, context=None, session=context.session)
    assert result["DetailType"] == 'ExpiredAccount'
    assert processed == ["123456789012"]

    # purge has not been enabled on "567890123456"
    processed = []

    def mock_account_set_state(account, *args, **kwargs):
        processed.append(account)

    monkeypatch.setattr(Account, 'set_state', mock_account_set_state)

    event = Events.load_event_from_template(template="fixtures/events/tag-account-template.json",
                                            context=dict(account="567890123456",
                                                         new_state=State.EXPIRED.value))
    result = handle_tag_event(event=event, context=None, session=context.session)
    assert result["DetailType"] == 'ExpiredAccount'
    assert processed == ["567890123456"]


@pytest.mark.integration_tests
@patch.dict(os.environ, dict(ACCOUNTS_PARAMETER="Accounts",
                             ENVIRONMENT_IDENTIFIER='Fake',
                             EVENT_BUS_ARN='arn:aws',
                             ORGANIZATIONAL_UNITS_PARAMETER="OrganizationalUnits",
                             VERBOSITY='INFO'))
@mock_ssm
def test_handle_tag_event_on_unexpected_state(monkeypatch):
    context = given_some_context(prefix="/{}/".format(os.environ['ENVIRONMENT_IDENTIFIER']))

    event = Events.load_event_from_template(template="fixtures/events/tag-account-template.json",
                                            context=dict(account="123456789012",
                                                         new_state=State.VANILLA.value))
    result = handle_tag_event(event=event, context=None, session=context.session)
    assert result == "[DEBUG] Unexpected state 'vanilla' for this function"
