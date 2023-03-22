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

import boto3
from csv import DictWriter
from datetime import date, datetime, timedelta
import io
from itertools import chain
import logging
import os
from types import SimpleNamespace

from logger import setup_logging, trap_exception
setup_logging()

from events import Events
from key_value_store import KeyValueStore


@trap_exception
def handle_record(event, context=None):
    logging.debug(event)
    input = Events.decode_spa_event(event)
    logging.info(f"Remembering {input.label}")
    records = get_table()
    stamp = datetime.utcnow().isoformat()
    payload = input.payload
    payload['stamp'] = stamp
    logging.debug(input.payload)
    records.remember(hash=stamp[:10], range=stamp[11:], value=payload)
    return f"[OK] {input.label}"


@trap_exception
def handle_monthly_reporting(event=None, context=None, day=None):
    logging.info("Producing activity reports for previous month")
    day = day or date.today()
    last_day_of_previous_month = day.replace(day=1) - timedelta(days=1)
    reports = build_reports(records=get_records(last_day_of_previous_month))  # /!\ memory-bound
    for label, reporter in reports.items():
        store_report(label, reporter.buffer.getvalue())
    return "[OK]"


@trap_exception
def handle_daily_reporting(event=None, context=None, day=None):
    logging.info("Producing ongoing activity reports")
    reports = build_reports(records=get_records(day))  # /!\ memory-bound
    for label, reporter in reports.items():
        store_report(label, reporter.buffer.getvalue())
    return "[OK]"


def get_records(day=None):
    store = get_table()
    return chain(*[store.enumerate(hash) for hash in get_hashes(day)])


def get_hashes(day=None):
    day = day or date.today()
    return [day.replace(day=(x + 1)).isoformat()[:10] for x in range(day.day)]


def get_table():
    return KeyValueStore(table_name=os.environ.get('METERING_RECORDS_DATASTORE', 'SpaMeteringTable'),
                         ttl=os.environ.get('METERING_RECORDS_TTL', str(366 * 24 * 60 * 60)))


def build_reports(records):
    logging.info("Building activity reports for each cost center")
    reports = {}
    for record in records:
        item = record['value']
        label = item['cost-center']
        reporter = reports.get(label, get_reporter())
        row = {'Account': item['account'],
               'Cost Center': item['cost-center'],
               'Stamp': item['stamp'],
               'Transaction': item['transaction'],
               'Identifier': item['identifier'],
               'Duration': item['duration']}
        reporter.writer.writerow(row)
        reports[label] = reporter
    return reports


def get_reporter():
    reporter = SimpleNamespace()
    reporter.buffer = io.StringIO()
    reporter.writer = DictWriter(reporter.buffer, fieldnames=['Cost Center', 'Transaction', 'Stamp', 'Account', 'Identifier', 'Duration'])
    reporter.writer.writeheader()
    return reporter


def store_report(label, report):
    logging.info("Storing activity report")
    logging.debug(report)
    boto3.client("s3").put_object(Bucket=os.environ['REPORTS_BUCKET_NAME'],
                                  Key=get_report_key(label),
                                  Body=report)


def get_report_key(label, day=None):
    day = day or date.today()
    return '/'.join([os.environ["REPORTING_ACTIVITIES_PREFIX"],
                     label,
                     f"{day.year:04d}-{day.month:02d}-{label}-activities.csv"])
