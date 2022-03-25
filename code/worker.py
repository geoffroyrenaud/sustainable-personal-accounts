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
import os
import time

from botocore.exceptions import ClientError
from boto3.session import Session

from session import make_session


class Worker:

    CODEBUILD_EVENT_PATTERN = {
        "source": ["aws.codebuild"],
        "detail-type": ["CodeBuild Build State Change"],
        "detail": {
            "build-status": ["SUCCEEDED", "FAILED", "STOPPED"]
        }
    }

    PROJECT_NAME_FOR_ACCOUNT_PREPARATION = "SpaProjectForAccountPreparation"
    PROJECT_NAME_FOR_ACCOUNT_PURGE = "SpaProjectForAccountPurge"

    @classmethod
    def prepare(cls, account, organizational_units, buildspec, event_bus_arn, session=None):
        session = session or cls.get_session(account.id)

        logging.info(f"Preparing account '{account.id}'...")
        logging.debug(f"account: {account.__dict__}")
        logging.debug(f"organizational_units: {organizational_units}")
        cls.forward_codebuild_events_to_central_bus(event_bus_arn=event_bus_arn, session=session)
        cls.deploy_project(name=cls.PROJECT_NAME_FOR_ACCOUNT_PREPARATION,
                           description="This project prepares an AWS account before being released to cloud engineer",
                           buildspec=buildspec,
                           role=cls.deploy_role_for_codebuild(session=session),
                           variables=cls.make_preparation_variables(account, organizational_units),
                           session=session)
        cls.run_project(name=cls.PROJECT_NAME_FOR_ACCOUNT_PREPARATION,
                        session=session)
        logging.info(f"Account '{account.id}' is being prepared")

    @classmethod
    def purge(cls, account, organizational_units, buildspec, event_bus_arn, session=None):
        session = session or cls.get_session(account.id)

        logging.info(f"Purging account '{account.id}'...")
        cls.forward_codebuild_events_to_central_bus(event_bus_arn=event_bus_arn, session=session)
        cls.deploy_project(name=cls.PROJECT_NAME_FOR_ACCOUNT_PURGE,
                           description="This project purges an AWS account of cloud resources",
                           buildspec=buildspec,
                           role=cls.deploy_role_for_codebuild(session=session),
                           variables=cls.make_purge_variables(account, organizational_units),
                           session=session)
        cls.run_project(name=cls.PROJECT_NAME_FOR_ACCOUNT_PURGE,
                        session=session)
        logging.info(f"Account '{account.id}' is being purged")

    @classmethod
    def forward_codebuild_events_to_central_bus(cls, event_bus_arn, session=None):
        role_arn = cls.deploy_role_for_events(event_bus_arn=event_bus_arn,
                                              session=session)
        cls.deploy_events_rule(event_bus_arn=event_bus_arn,
                               role_arn=role_arn,
                               session=session)

    @staticmethod
    def make_preparation_variables(account, organizational_units) -> dict:
        configuration = organizational_units.get(account.unit, {})
        variables = dict(BUDGET_AMOUNT=str(configuration.get('cost_budget', 200)),
                         BUDGET_EMAIL=account.email)
        variables.update(configuration.get('preparation_variables', {}))
        if value := os.environ.get('ENVIRONMENT_IDENTIFIER'):
            variables['ENVIRONMENT_IDENTIFIER'] = value
        if value := os.environ.get('TOPIC_ARN'):
            variables['TOPIC_ARN'] = value
        return variables

    @staticmethod
    def make_purge_variables(account, organizational_units) -> dict:
        configuration = organizational_units.get(account.unit, {})
        variables = dict(PURGE_EMAIL=account.email)
        variables.update(configuration.get('purge_variables', {}))
        if value := os.environ.get('ENVIRONMENT_IDENTIFIER'):
            variables['ENVIRONMENT_IDENTIFIER'] = value
        if value := os.environ.get('TOPIC_ARN'):
            variables['TOPIC_ARN'] = value
        return variables

    @classmethod
    def deploy_events_rule(cls, event_bus_arn, role_arn, name="SpaEventsRuleForCodebuild", description="", session=None):
        session = session or Session()
        events = session.client('events')

        logging.info(f"Deploying rule '{name}' for events detection")

        events.put_rule(
            Name=name,
            EventPattern=json.dumps(cls.CODEBUILD_EVENT_PATTERN),
            Description=description,
            Tags=[dict(Key='owner', Value='SPA')])

        events.put_targets(
            Rule=name,
            Targets=[dict(Id='SpaPhoneHome',
                          Arn=event_bus_arn,
                          RoleArn=role_arn)])

        logging.info(f"Rule '{name}' has been updated")

    @classmethod
    def deploy_role_for_codebuild(cls,
                                  name="SpaRoleForCodebuild",
                                  policy="AdministratorAccess",
                                  session=None):
        session = session or Session()
        iam = session.client('iam')

        logging.info(f"Deploying role '{name}' for codebuild projects")

        try:
            iam.create_role(
                RoleName=name,
                AssumeRolePolicyDocument=cls.get_trusting_policy_document(service="codebuild.amazonaws.com"),
                Description='Set permissions for Codebuild project',
                MaxSessionDuration=12 * 60 * 60,
                Tags=[dict(Key='owner', Value='SPA')])
            logging.debug(f"Role '{name}' has been created")
        except ClientError as error:
            if error.response['Error']['Code'] == 'EntityAlreadyExists':
                logging.debug(f"Role '{name}' already exists")
            else:
                logging.error(error)
                return

        try:
            iam.attach_role_policy(
                RoleName=name,
                PolicyArn=f"arn:aws:iam::aws:policy/{policy}")
            logging.debug(f"Policy '{policy}' has been attached to role {name}")
        except ClientError as error:
            logging.error(error)
            return

        waiter = iam.get_waiter('role_exists')
        waiter.wait(RoleName=name)

        role = iam.get_role(RoleName=name)
        return role['Role']['Arn']

    @classmethod
    def deploy_role_for_events(cls,
                               event_bus_arn,
                               name="SpaRoleForEvents",
                               session=None):
        session = session or Session()
        iam = session.client('iam')

        logging.info(f"Deploying role '{name}' for events rule")

        try:
            iam.create_role(
                RoleName=name,
                AssumeRolePolicyDocument=cls.get_trusting_policy_document(service="events.amazonaws.com"),
                Description='Set permissions for EventBridge rule',
                MaxSessionDuration=12 * 60 * 60,
                Tags=[dict(Key='owner', Value='SPA')])
            logging.debug(f"Role '{name}' has been created")
        except ClientError as error:
            if error.response['Error']['Code'] == 'EntityAlreadyExists':
                logging.debug(f"Role '{name}' already exists")
            else:
                logging.error(error)
                return

        policy_name = 'SpaPermissionToPutEvents'
        try:
            logging.debug(f"Creating policy '{policy_name}' for sending events back home")
            response = iam.create_policy(
                PolicyName=policy_name,
                PolicyDocument=cls.get_put_events_policy_document(event_bus_arn=event_bus_arn))
            policy_arn = response['Policy']['Arn']

            logging.debug(f"Attaching policy '{policy_name}' to the role '{name}'")
            iam.attach_role_policy(
                RoleName=name,
                PolicyArn=policy_arn)

        except ClientError as error:
            if error.response['Error']['Code'] == 'EntityAlreadyExists':
                logging.debug(f"Policy '{policy_name}' already exists")
            else:
                raise

        waiter = iam.get_waiter('role_exists')
        waiter.wait(RoleName=name)

        role = iam.get_role(RoleName=name)
        return role['Role']['Arn']

    @classmethod
    def deploy_project(cls, name, description, buildspec, role, variables={}, session=None):
        session = session or Session()
        client = session.client('codebuild')
        environment_variables = [dict(name=k, value=variables[k], type="PLAINTEXT") for k in variables.keys()]
        retries = 0
        while retries < 5:  # we may have to wait for IAM role to be really available
            logging.debug("Deploying Codebuild project")
            try:
                client.create_project(
                    name=name,
                    description=description,
                    source=dict(type='NO_SOURCE',
                                buildspec=buildspec),
                    artifacts=dict(type='NO_ARTIFACTS'),
                    cache=dict(type='NO_CACHE'),
                    environment=dict(type='ARM_CONTAINER',
                                     image='aws/codebuild/amazonlinux2-aarch64-standard:2.0',
                                     computeType='BUILD_GENERAL1_SMALL',
                                     environmentVariables=environment_variables),
                    serviceRole=role,
                    timeoutInMinutes=480,
                    tags=[dict(key='origin', value='SustainablePersonalAccounts')],
                    logsConfig=dict(cloudWatchLogs=dict(status='ENABLED')),
                    concurrentBuildLimit=1)
                logging.debug("Done")
                break

            except client.exceptions.ResourceAlreadyExistsException as error:
                logging.debug(f"Project '{name}' already exists, deleting it")
                client.delete_project(name=name)
                retries += 1
                time.sleep(retries * 5)

            except client.exceptions.InvalidInputException as error:  # we could have to wait for IAM to be ready
                logging.debug("Sleeping...")
                retries += 1
                time.sleep(retries * 5)

    @classmethod
    def run_project(cls, name, session=None):
        session = session or Session()
        client = session.client('codebuild')
        logging.info(f"Starting project build {name}")
        result = client.start_build(projectName=name)
        logging.debug(result.get('build'))
        logging.debug("Done")

    @classmethod
    def get_session(cls, account, session=None):
        arn = os.environ.get('ROLE_ARN_TO_MANAGE_ACCOUNTS')
        master = make_session(role_arn=arn, session=session) if arn else Session()

        name = os.environ.get('ROLE_NAME_TO_MANAGE_CODEBUILD', 'AWSControlTowerExecution')
        target = make_session(role_arn=f'arn:aws:iam::{account}:role/{name}',
                              session=master)
        identity = target.client('sts').get_caller_identity()
        logging.debug(f"Using identity {identity}")
        return target

    @classmethod
    def get_trusting_policy_document(cls, service):
        policy = {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Effect": "Allow",
                    "Principal": {
                        "Service": service
                    },
                    "Action": "sts:AssumeRole"
                }
            ]
        }
        logging.debug(f"Trusting policy: {json.dumps(policy)}")
        return json.dumps(policy)

    @classmethod
    def get_put_events_policy_document(cls, event_bus_arn):
        policy = {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Effect": "Allow",
                    "Action": "events:PutEvents",
                    "Resource": event_bus_arn
                }
            ]
        }
        logging.debug(f"Put events policy: {json.dumps(policy)}")
        return json.dumps(policy)
