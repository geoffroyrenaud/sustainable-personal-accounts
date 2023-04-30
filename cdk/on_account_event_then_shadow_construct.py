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

from constructs import Construct
from aws_cdk import RemovalPolicy
from aws_cdk.aws_dynamodb import AttributeType, BillingMode, Table, TableEncryption
from aws_cdk.aws_events import EventPattern, Rule, Schedule
from aws_cdk.aws_events_targets import LambdaFunction
from aws_cdk.aws_lambda import Function
from aws_cdk.aws_logs import LogGroup, RetentionDays

from lambdas import Events


class OnAccountEventThenShadow(Construct):

    def __init__(self, scope: Construct, id: str, parameters={}) -> None:
        super().__init__(scope, id)

        self.table_name = toggles.environment_identifier + toggles.metering_shadows_datastore
        self.table = Table(
            self, "ShadowsTable",
            table_name=self.table_name,
            partition_key={'name': 'Identifier', 'type': AttributeType.STRING},
            sort_key={'name': 'Order', 'type': AttributeType.STRING},
            billing_mode=BillingMode.PAY_PER_REQUEST,
            encryption=TableEncryption.AWS_MANAGED,
            removal_policy=RemovalPolicy.DESTROY,
            time_to_live_attribute="Expiration")

        parameters['environment']['METERING_SHADOWS_DATASTORE'] = self.table_name
        parameters['environment']['METERING_SHADOWS_TTL'] = str(toggles.metering_shadows_ttl_in_seconds)
        parameters['environment']['REPORTING_INVENTORIES_PREFIX'] = toggles.reporting_inventories_prefix
        self.functions = [self.on_event(parameters=parameters),
                          self.on_signin(parameters=parameters),
                          self.on_schedule(parameters=parameters)]

        for function in self.functions:
            self.table.grant_read_write_data(grantee=function)

    def on_event(self, parameters) -> Function:

        function_name = toggles.environment_identifier + "OnAccountEventsThenShadow"

        LogGroup(self, function_name + "Log",
                 log_group_name=f"/aws/lambda/{function_name}",
                 retention=RetentionDays.THREE_MONTHS,
                 removal_policy=RemovalPolicy.DESTROY)

        function = Function(self, "FromEvent",
                            function_name=function_name,
                            description="Persist last event for each account",
                            handler="on_account_event_then_shadow_handler.handle_account_event",
                            **parameters)

        Rule(self, "EventRule",
             description="Route events from SPA to listening lambda function",
             event_pattern=EventPattern(
                 source=['SustainablePersonalAccounts'],
                 detail={"Environment": [toggles.environment_identifier]},
                 detail_type=Events.ACCOUNT_EVENT_LABELS),
             targets=[LambdaFunction(function)])

        return function

    def on_signin(self, parameters, name="UpdateShadowOnSignin") -> Function:

        function_name = toggles.environment_identifier + name

        LogGroup(self, function_name + "Log",
                 log_group_name=f"/aws/lambda/{function_name}",
                 retention=RetentionDays.THREE_MONTHS,
                 removal_policy=RemovalPolicy.DESTROY)

        function = Function(self, name,
                            function_name=function_name,
                            description="Update shadow record on signin event",
                            handler="on_account_event_then_shadow_handler.handle_signin_event",
                            **parameters)

        Rule(self, "SigninRule",
             description="Trigger Lambda function on signin event",
             event_pattern=EventPattern(
                 detail={"eventSource": ["signin.amazonaws.com"], "eventName": ["ConsoleLogin"]}),
             targets=[LambdaFunction(function)])

        return function

    def on_schedule(self, parameters) -> Function:

        function_name = toggles.environment_identifier + "OnInventoryReport"

        LogGroup(self, function_name + "Log",
                 log_group_name=f"/aws/lambda/{function_name}",
                 retention=RetentionDays.THREE_MONTHS,
                 removal_policy=RemovalPolicy.DESTROY)

        function = Function(self, "FromSchedule",
                            function_name=function_name,
                            description="Report inventories, from shadows",
                            handler="on_account_event_then_shadow_handler.handle_report",
                            **parameters)

        Rule(self, "TriggerRule",
             rule_name="{}OnInventoryReportTriggerRule".format(toggles.environment_identifier),
             description="Trigger periodic reporting on shadows",
             schedule=Schedule.cron(week_day="SAT", hour="3", minute="23"),
             targets=[LambdaFunction(function)])

        return function
