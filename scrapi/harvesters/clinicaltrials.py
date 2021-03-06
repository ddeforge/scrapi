"""
API harvester for ClinicalTrials.gov for the SHARE Notification Service
"""

#!/usr/bin/env python
from __future__ import unicode_literals

import time
import logging
import datetime

from lxml import etree

from dateutil.parser import *

from scrapi import requests
from scrapi.base import XMLHarvester
from scrapi.linter.document import RawDocument
from scrapi.base.schemas import default_name_parser

logger = logging.getLogger(__name__)


class ClinicalTrialsHarvester(XMLHarvester):

    short_name = 'clinicaltrials'
    long_name = 'ClinicalTrials.gov'
    url = 'https://clinicaltrials.gov/'

    DEFAULT_ENCODING = 'UTF-8'
    record_encoding = None

    schema = {
        "contributors": ('//overall_official/last_name/node()', lambda x: default_name_parser(x) if isinstance(x, list) else default_name_parser([x])),
        "uris": {
            "canonicalUri": "//required_header/url/node()"
        },
        "providerUpdatedDateTime": ("lastchanged_date/node()", lambda x: unicode(parse(x).replace(tzinfo=None).isoformat())),
        "title": ('//official_title/node()', '//brief_title/node()', lambda x, y: x or y or ''),
        "description": ('//brief_summary/textblock/node()', '//brief_summary/textblock/node()', lambda x, y: x or y or ''),
        # "otherProperties": {
        #     'oversightAuthority': '//oversight_info/authority/node()',
        #     "serviceID": "//nct_id/node()",
        #     "tags": ("//keyword/node()", lambda tags: [unicode(tag.lower()) for tag in tags]),
        #     'studyDesign': '//study_design/node()',
        #     'numberOfArms': '//number_of_arms/node()',
        #     'source': '//source/node()',
        #     'verificationDate': '//verification_date/node()',
        #     'lastChanged': '//lastchanged_date/node()',
        #     'condition': '//condition/node()',
        #     'verificationDate': '//verification_date/node()',
        #     'lastChanged': '//lastchanged_date/node()',
        #     'status': '//status/node()',
        #     'locationCountries': '//location_countries/country/node()',
        #     'isFDARegulated': '//is_fda_regulated/node()',
        #     'isSection801': '//is_section_801/node()',
        #     'hasExpandedAccess': '//has_expanded_access/node()',
        #     'sponsors': {
        #         'agency': '//lead_sponsor/agency/node()',
        #         'agencyClass': '//lead_sponsor/agency_class/node()'
        #     },
        #     'primaryOutcome': {
        #         'measure': '//primary_outcome/measure/node()',
        #         'timeFrame': '//primary_outcome/time_frame/node()',
        #         'safetyIssue': '//primary_outcome/safety_issue/node()'
        #     },
        #     'secondaryOutcomes': '//secondary_outcome/node()',
        #     'enrollment': '//enrollment/node()',
        #     'armGroup': '//arm_group/node()',
        #     'intervention': '//intervention/node()',
        #     'eligibility': '//elligibility/node()',
        #     'link': '//link/node()',
        #     'responsible_party': '//responsible_party'
        # }
    }

    @property
    def namespaces(self):
        return None

    def copy_to_unicode(self, element):
        encoding = self.record_encoding or self.DEFAULT_ENCODING
        element = ''.join(element)
        if isinstance(element, unicode):
            return element
        else:
            return unicode(element, encoding=encoding)

    def harvest(self, days_back=1):
        """ First, get a list of all recently updated study urls,
        then get the xml one by one and save it into a list
        of docs including other information """

        today = datetime.date.today()
        start_date = today - datetime.timedelta(days_back)

        month = today.strftime('%m')
        day = today.strftime('%d')
        year = today.strftime('%Y')

        y_month = start_date.strftime('%m')
        y_day = start_date.strftime('%d')
        y_year = start_date.strftime('%Y')

        base_url = 'http://clinicaltrials.gov/ct2/results?lup_s='
        url_end = '{}%2F{}%2F{}%2F&lup_e={}%2F{}%2F{}&displayxml=true'.\
            format(y_month, y_day, y_year, month, day, year)

        url = base_url + url_end

        # grab the total number of studies
        initial_request = requests.get(url)
        record_encoding = initial_request.encoding
        initial_request_xml = etree.XML(initial_request.content)
        count = int(initial_request_xml.xpath('//search_results/@count')[0])
        xml_list = []
        if int(count) > 0:
            # get a new url with all results in it
            url = url + '&count=' + str(count)
            total_requests = requests.get(url)
            initial_doc = etree.XML(total_requests.content)

            # make a list of urls from that full list of studies
            study_urls = []
            for study in initial_doc.xpath('//clinical_study'):
                study_urls.append(study.xpath('url/node()')[0] + '?displayxml=true')

            # grab each of those urls for full content
            logger.info("There are {} urls to harvest - be patient...".format(len(study_urls)))
            count = 0
            official_count = 0
            for study_url in study_urls:
                try:
                    content = requests.get(study_url)
                except requests.exceptions.ConnectionError as e:
                    logger.info('Connection error: {}, wait a bit...'.format(e))
                    time.sleep(30)
                    continue
                doc = etree.XML(content.content)
                record = etree.tostring(doc, encoding=record_encoding)
                doc_id = doc.xpath('//nct_id/node()')[0]
                xml_list.append(RawDocument({
                    'doc': record,
                    'source': self.short_name,
                    'docID': self.copy_to_unicode(doc_id),
                    'filetype': 'xml',
                }))
                official_count += 1
                count += 1
                if count % 100 == 0:
                    logger.info("You've requested {} studies, keep going!".format(official_count))
                    count = 0

        return xml_list
