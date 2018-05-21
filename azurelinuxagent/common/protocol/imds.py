# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the Apache License, Version 2.0 (the "License");
import json
import re

import azurelinuxagent.common.utils.restutil as restutil
from azurelinuxagent.common.exception import HttpError
from azurelinuxagent.common.future import ustr
from azurelinuxagent.common.protocol.restapi import DataContract, set_properties
from azurelinuxagent.common.utils.flexible_version import FlexibleVersion

IMDS_ENDPOINT = '169.254.169.254'
APIVERSION = '2017-12-01'
BASE_URI = "http://{0}/metadata/instance/{1}?api-version={2}"

IMDS_IMAGE_ORIGIN_UNKNOWN = 0
IMDS_IMAGE_ORIGIN_CUSTOM = 1
IMDS_IMAGE_ORIGIN_ENDORSED = 2
IMDS_IMAGE_ORIGIN_PLATFORM = 3


def get_imds_client():
    return ImdsClient()


# A *slightly* future proof list of endorsed distros.
#  -> e.g. I have predicted the future and said that 20.04-LTS will exist
#     and is endored.
#
# See https://docs.microsoft.com/en-us/azure/virtual-machines/linux/endorsed-distros for
# more details.
#
# This is not an exhaustive list. This is a best attempt to mark images as
# endorsed or not.  Image publishers do not encode all of the requisite information
# in their publisher, offer, sku, and version to definitively mark something as
# endorsed or not.  This is not perfect, but it is approximately 98% perfect.
ENDORSED_IMAGE_INFO_MATCHER_JSON = """{
    "CANONICAL": {
        "UBUNTUSERVER": {
            "14.04.0-LTS": { "Match": ".*" },
            "14.04.1-LTS": { "Match": ".*" },
            "14.04.2-LTS": { "Match": ".*" },
            "14.04.3-LTS": { "Match": ".*" },
            "14.04.4-LTS": { "Match": ".*" },
            "14.04.5-LTS": { "Match": ".*" },
            "14.04.6-LTS": { "Match": ".*" },
            "14.04.7-LTS": { "Match": ".*" },
            "14.04.8-LTS": { "Match": ".*" },
            
            "16.04-LTS": { "Match": ".*" },
            "16.04.0-LTS": { "Match": ".*" },
            
            "18.04-LTS": { "Match": ".*" },
            "20.04-LTS": { "Match": ".*" },
            "22.04-LTS": { "Match": ".*" }
        }
    },
    "COREOS": {
        "COREOS": {
            "STABLE": { "Minimum": "494.4.0" }
        }
    },
    "CREDATIV": {
        "DEBIAN": { "Minimum": "7" }
    },
    "OPENLOGIC": {
        "CENTOS": {
            "Minimum": "6.3",
            "7-LVM": { "Match": ".*" },
            "7-RAW": { "Match": ".*" }
        },
        "CENTOS-HPC": { "Minimum": "6.3" }
    },
    "REDHAT": {
        "RHEL": { 
            "Minimum": "6.7",
            "7-LVM": { "Match": ".*" },
            "7-RAW": { "Match": ".*" }
        },
        "RHEL-HANA": { "Minimum": "6.7" },
        "RHEL-SAP": { "Minimum": "6.7" },
        "RHEL-SAP-APPS": { "Minimum": "6.7" },
        "RHEL-SAP-HANA": { "Minimum": "6.7" }
    },
    "SUSE": {
        "SLES": {
            "11-SP4": { "Match": ".*" },
            "11-SP5": { "Match": ".*" },
            "11-SP6": { "Match": ".*" },
            "12-SP1": { "Match": ".*" },
            "12-SP2": { "Match": ".*" },
            "12-SP3": { "Match": ".*" },
            "12-SP4": { "Match": ".*" },
            "12-SP5": { "Match": ".*" },
            "12-SP6": { "Match": ".*" }
        },
        "SLES-BYOS": {
            "11-SP4": { "Match": ".*" },
            "11-SP5": { "Match": ".*" },
            "11-SP6": { "Match": ".*" },
            "12-SP1": { "Match": ".*" },
            "12-SP2": { "Match": ".*" },
            "12-SP3": { "Match": ".*" },
            "12-SP4": { "Match": ".*" },
            "12-SP5": { "Match": ".*" },
            "12-SP6": { "Match": ".*" }
        },
        "SLES-SAP": {
            "11-SP4": { "Match": ".*" },
            "11-SP5": { "Match": ".*" },
            "11-SP6": { "Match": ".*" },
            "12-SP1": { "Match": ".*" },
            "12-SP2": { "Match": ".*" },
            "12-SP3": { "Match": ".*" },
            "12-SP4": { "Match": ".*" },
            "12-SP5": { "Match": ".*" },
            "12-SP6": { "Match": ".*" }
        }
    }
}"""


class ImageInfoMatcher(object):
    def __init__(self, doc):
        self.doc = json.loads(doc)

    def is_match(self, publisher, offer, sku, version):
        def _is_match_walk(doci, keys):
            key = keys.pop(0).upper()
            if key is None:
                return False

            if key not in doci:
                return False

            if 'Match' in doci[key] and re.match(doci[key]['Match'], keys[0]):
                return True

            if 'Minimum' in doci[key]:
                try:
                    return FlexibleVersion(keys[0]) >= FlexibleVersion(doci[key]['Minimum'])
                except ValueError:
                    pass

            return _is_match_walk(doci[key], keys)

        return _is_match_walk(self.doc, [ publisher, offer, sku, version ])


class ComputeInfo(DataContract):
    __matcher = ImageInfoMatcher(ENDORSED_IMAGE_INFO_MATCHER_JSON)

    def __init__(self,
                 location=None,
                 name=None,
                 offer=None,
                 osType=None,
                 placementGroupId=None,
                 platformFaultDomain=None,
                 placementUpdateDomain=None,
                 publisher=None,
                 resourceGroupName=None,
                 sku=None,
                 subscriptionId=None,
                 tags=None,
                 version=None,
                 vmId=None,
                 vmSize=None):
        self.location = location
        self.name = name
        self.offer = offer
        self.osType = osType
        self.placementGroupId = placementGroupId
        self.platformFaultDomain = platformFaultDomain
        self.platformUpdateDomain = placementUpdateDomain
        self.publisher = publisher
        self.resourceGroupName = resourceGroupName
        self.sku = sku
        self.subscriptionId = subscriptionId
        self.tags = tags
        self.version = version
        self.vmId = vmId
        self.vmSize = vmSize


    @property
    def image_info(self):
        return "{0}:{1}:{2}:{3}".format(self.publisher, self.offer, self.sku, self.version)

    @property
    def image_origin(self):
        """
        An integer value describing the origin of the image.

          0 -> unknown
          1 -> custom - user created image
          2 -> endorsed - See https://docs.microsoft.com/en-us/azure/virtual-machines/linux/endorsed-distros
          3 -> platform - non-endorsed image that is available in the Azure Marketplace.
        """

        try:
            if self.publisher == "":
                return IMDS_IMAGE_ORIGIN_CUSTOM

            if ComputeInfo.__matcher.is_match(self.publisher, self.offer, self.sku, self.version):
                return IMDS_IMAGE_ORIGIN_ENDORSED
            else:
                return IMDS_IMAGE_ORIGIN_PLATFORM

        except Exception as e:
            return IMDS_IMAGE_ORIGIN_UNKNOWN


class ImdsClient(object):
    def __init__(self, version=APIVERSION):
        self._api_version = version
        self._headers = {
            'User-Agent': restutil.HTTP_USER_AGENT,
            'Metadata': True,
        }
        pass

    @property
    def compute_url(self):
        return BASE_URI.format(IMDS_ENDPOINT, 'compute', self._api_version)

    def get_compute(self):
        """
        Fetch compute information.

        :return: instance of a ComputeInfo
        :rtype: ComputeInfo
        """

        resp = restutil.http_get(self.compute_url, headers=self._headers)

        if restutil.request_failed(resp):
            raise HttpError("{0} - GET: {1}".format(resp.status, self.compute_url))

        data = resp.read()
        data = json.loads(ustr(data, encoding="utf-8"))

        compute_info = ComputeInfo()
        set_properties('compute', compute_info, data)

        return compute_info
