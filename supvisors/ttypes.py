#!/usr/bin/python
# -*- coding: utf-8 -*-

# ======================================================================
# Copyright 2016 Julien LE CLEACH
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
# ======================================================================

from enum import Enum
from typing import Any, Dict, List, Set, TypeVar

from supervisor.events import Event


# all enumerations
class AddressStates(Enum):
    """ Enumeration class for the state of remote Supvisors instance """
    UNKNOWN, CHECKING, RUNNING, SILENT, ISOLATING, ISOLATED = range(6)


class ApplicationStates(Enum):
    """ Class holding the possible enumeration values for an application state. """
    STOPPED, STARTING, RUNNING, STOPPING = range(4)


class StartingStrategies(Enum):
    """ Applicable strategies that can be applied to start processes. """
    CONFIG, LESS_LOADED, MOST_LOADED, LOCAL = range(4)


class ConciliationStrategies(Enum):
    """ Applicable strategies that can be applied during a conciliation. """
    SENICIDE, INFANTICIDE, USER, STOP, RESTART, RUNNING_FAILURE = range(6)
    # TODO: change to STOP+RESTART PROCESS and add STOP+RESTART APPLICATION ?


class StartingFailureStrategies(Enum):
    """ Applicable strategies that can be applied on a failure of a starting application. """
    ABORT, STOP, CONTINUE = range(3)


class RunningFailureStrategies(Enum):
    """ Applicable strategies that can be applied on a failure of a running application. """
    CONTINUE, RESTART_PROCESS, STOP_APPLICATION, RESTART_APPLICATION = range(4)


class SupvisorsStates(Enum):
    """ Internal state of Supvisors. """
    INITIALIZATION, DEPLOYMENT, OPERATION, CONCILIATION, RESTARTING, SHUTTING_DOWN, SHUTDOWN = range(7)


def enum_values(enum_klass) -> List[int]:
    """ Return the possible integer values corresponding to the enumeration type.
    Equivalent to the protected Enum._value2member_map_.keys()

    :param enum_klass: the enumeration class
    :return: the possible enumeration values
    """
    return list(map(lambda x: x.value, enum_klass))


def enum_names(enum_klass) -> List[str]:
    """ Return the possible string values corresponding to the enumeration type.
    Equivalent to the protected Enum._member_names_

    :param enum_klass: the enumeration class
    :return: the possible enumeration literals
    """
    return list(map(lambda x: x.name, enum_klass))


# Exceptions
class InvalidTransition(Exception):
    """ Exception used for an invalid transition in state machines. """

    def __init__(self, value):
        self.value = value

    def __str__(self):
        return self.value


# Supvisors related faults
FAULTS_OFFSET = 100


class SupvisorsFaults(Enum):
    SUPVISORS_CONF_ERROR, BAD_SUPVISORS_STATE, NOT_MANAGED = range(FAULTS_OFFSET, FAULTS_OFFSET + 3)


# Additional events
class ProcessEvent(Event):

    def __init__(self, process):
        self.process = process

    def payload(self):
        groupname = ''
        if self.process.group:
            groupname = self.process.group.config.name
        return 'processname:{} groupname:{} '.format(self.process.config.name, groupname)


class ProcessAddedEvent(ProcessEvent):
    pass


class ProcessRemovedEvent(ProcessEvent):
    pass


# Types for annotations
EnumClassType = TypeVar('EnumClassType', bound='Type[Enum]')
EnumType = TypeVar('EnumType', bound='Enum')
Payload = Dict[str, Any]
PayloadList = List[Payload]
NameList = List[str]
NameSet = Set[str]
