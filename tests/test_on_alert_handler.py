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

import boto3
from unittest.mock import patch
from moto import mock_sns
import os
import pytest

from code.on_alert_handler import get_codebuild_message, handle_queue_event, publish_notification_on_microsoft_webhook

pytestmark = pytest.mark.wip


@pytest.fixture
def queued_message():

    return {
        "Records": [
            {
                "messageId": "testtest-test-test-test-testtesttest",
                "receiptHandle": "TEST",
                "body": "{\n  \"Type\" : \"Notification\",\n  \"MessageId\" : \"12345678-1234-1234-1234-123456789012\",\n  \"TopicArn\" : \"arn:aws:sns:eu-west-1:111111111111:SpaAlertTopic\",\n  \"Subject\" : \"some subject\",\n  \"Message\" : \"some message\",\n  \"Timestamp\" : \"2022-03-28T13:17:58.936Z\",\n  \"SignatureVersion\" : \"1\",\n  \"Signature\" : \"TEST\",\n  \"SigningCertURL\" : \"https://sns.eu-west-1.amazonaws.com/SimpleNotificationService-test.pem\",\n  \"UnsubscribeURL\" : \"https://sns.eu-west-1.amazonaws.com/?Action=Unsubscribe&SubscriptionArn=arn:aws:sns:eu-west-1:111111111111:SpaAlertTopic:12345678-ec7c-40bc-ae3c-123456789012\",\n  \"MessageAttributes\" : {\n    \"someName\" : {\"Type\":\"String\",\"Value\":\"someValue\"}\n  }\n}",
                "attributes": {
                    "ApproximateReceiveCount": "1",
                    "SentTimestamp": "1648473478965",
                    "SenderId": "AIDAITESTTESTTESTTEST",
                    "ApproximateFirstReceiveTimestamp": "1648473478972"
                },
                "messageAttributes": {},
                "md5OfBody": "0123456789012",
                "eventSource": "aws:sqs",
                "eventSourceARN": "arn:aws:sqs:eu-west-1:111111111111:SpaAlerts",
                "awsRegion": "eu-west-1"
            }
        ]
    }


def test_get_codebuild_message():
    result = get_codebuild_message(account='123456789012', project='someProject', status='FAILED')
    assert result == "You will find below details on failing CodeBuild project ran on account '123456789012':\n\n- account: 123456789012\n- project: someProject\n- status: FAILED"


@mock_sns
def test_handle_queue_event(queued_message, account_describe_mock):
    topic = boto3.client('sns').create_topic(Name="test-topic")
    with patch.dict(os.environ, dict(TOPIC_ARN=topic['TopicArn'])):
        result = handle_queue_event(event=queued_message, context=None, session=account_describe_mock)
        assert result == '[OK]'
    account_describe_mock.client.return_value.publish.assert_called_with(TopicArn='arn:aws:sns:eu-west-1:123456789012:test-topic',
                                                                         Message="You will find below a copy of the alert that has been sent automatically to the holder of account '111111111111 (a@b.com)':\n\n----\n\nsome message",
                                                                         Subject="Alert on account '111111111111 (a@b.com)'")


@patch.dict(os.environ, dict(MICROSOFT_WEBHOOK_ON_ALERTS='https://webhook/'))
@patch('pymsteams.connectorcard')
def test_publish_notification_on_microsoft_webhook(patched):
    notification = dict(Message='hello world',
                        Subject='some subject')
    publish_notification_on_microsoft_webhook(notification=notification)
    patched.assert_called_once_with('https://webhook/')
    message = patched('https://webhook/')
    message.title.assert_called_once_with('some subject')
    message.text.assert_called_once_with('hello world')
    message.send.assert_called_once()


"""
@mock_sqs
@mock_sns
def test_high_number_of_topics_per_queue():
    ''' unique test to ensure that up to 10,000 topics can subscribe to the same queue '''
    queue_url = boto3.client('sqs').create_queue(QueueName='queue')['QueueUrl']
    queue_arn = boto3.client('sqs').get_queue_attributes(QueueUrl=queue_url, AttributeNames=['QueueArn'])['Attributes']['QueueArn']
    print(f"creating queue {queue_arn}")
    for index in range(10000):
        topic = boto3.client('sns').create_topic(Name=f"topic-{index:05d}")
        print(f"creating topic {topic}")
        result = boto3.client('sns').subscribe(
            TopicArn=topic['TopicArn'],
            Protocol='sqs',
            Endpoint=queue_arn)

    assert 'it works!'
"""
