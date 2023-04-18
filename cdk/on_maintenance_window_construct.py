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
from aws_cdk.aws_events import Rule, Schedule
from aws_cdk.aws_events_targets import LambdaFunction
from aws_cdk.aws_lambda import Function
from aws_cdk.aws_logs import LogGroup, RetentionDays


class OnMaintenanceWindow(Construct):

    def __init__(self, scope: Construct, id: str, parameters={}) -> None:
        super().__init__(scope, id)
        self.functions = [self.on_schedule(parameters=parameters)]

    def on_schedule(self, parameters) -> Function:

        function_name = toggles.environment_identifier + "OnMaintenanceWindow"

        LogGroup(self, function_name + "Log",
                 log_group_name=f"/aws/lambda/{function_name}",
                 retention=RetentionDays.THREE_MONTHS,
                 removal_policy=RemovalPolicy.DESTROY)

        function = Function(
            self, "FromSchedule",
            function_name=function_name,
            description="Change state of expired accounts",
            handler="on_maintenance_window_handler.handle_schedule_event",
            **parameters)

        Rule(self, "TriggerRule",
             description="Trigger account maintenance window on scheduling expression",
             schedule=Schedule.expression(toggles.automation_maintenance_window_expression),
             targets=[LambdaFunction(function)])

        return function
