# Windows Azure Linux Agent
#
# Copyright 2014 Microsoft Corporation
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
# Requires Python 2.4+ and Openssl 1.0+
#
import os
import traceback
import threading
import azurelinuxagent.logger as logger
import azurelinuxagent.utils.fileutil as fileutil
from azurelinuxagent.utils.osutil import OSUtil
from azurelinuxagent.protocol.common import *
from azurelinuxagent.protocol.v1 import ProtocolV1
from azurelinuxagent.protocol.v2 import ProtocolV2

WireServerAddrFile = "WireServer" 
WireProtocol = "WireProtocol"
MetaDataProtocol = "MetaDataProtocol"

def GetWireProtocolEndpoint():
    path = os.path.join(OSUtil.GetLibDir(), WireServerAddrFile)
    try:
        endpoint = fileutil.GetFileContents(path)
    except IOError as e:
        raise ProtocolNotFound("Wire server endpoint not found: {0}".format(e))

    if endpoint is None:
        raise ProtocolNotFound("Wire server endpoint is None")

    return endpoint

def DetectV1():
    endpoint = GetWireProtocolEndpoint() 

    OSUtil.GenerateTransportCert()
    protocol = ProtocolV1(endpoint)
    protocol.initialize()

    path = os.path.join(OSUtil.GetLibDir(), WireProtocol)
    fileutil.SetFileContents(path, "")
    return protocol

def DetectV2():
    raise ProtocolNotFound("Not implemented")

def DetectAvailableProtocols(probeFuncs=[DetectV1, DetectV2]):
    availableProtocols = []
    for probeFunc in probeFuncs:
        try:
            protocol = probeFunc()
            availableProtocols.append(protocol)
        except ProtocolNotFound as e:
            logger.Info(str(e))
    return availableProtocols

def DetectDefaultProtocol():
    availableProtocols = DetectAvailableProtocols()
    return ChooseDefaultProtocol(availableProtocols)

def ChooseDefaultProtocol(availableProtocols):
    if len(availableProtocols) > 0:
        return availableProtocols[-1]
    else:
        raise ProtocolNotFound("No available protocol detected.")

def GetV1():
    path = os.path.join(OSUtil.GetLibDir(), WireProtocol)
    if not os.path.isfile(path):
        raise ProtocolNotFound("Protocol V1 not found")
        
    endpoint = GetWireProtocolEndpoint() 
    return ProtocolV1(endpoint)

def GetV2():
    raise ProtocolNotFound("Protocol V2 not implemented")

def GetAvailableProtocols(getters=[GetV1, GetV2]):
    availableProtocols = []
    for getter in getters:
        try:
            protocol = getter()
            availableProtocols.append(protocol)
        except ProtocolNotFound as e:
            logger.Info(str(e))
    return availableProtocols

__DefaultProtocol__ = None
__InstanceLock__ = threading.Lock()

def GetDefaultProtocol():
    global __DefaultProtocol__
    global __InstanceLock__

    if __DefaultProtocol__ is None:
        __InstanceLock__.acquire()
        if __DefaultProtocol__ is None:
            availableProtocols = GetAvailableProtocols()
            __DefaultProtocol__ = ChooseDefaultProtocol(availableProtocols)
        __InstanceLock__.release()
    return __DefaultProtocol__

