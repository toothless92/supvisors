#!/usr/bin/python
#-*- coding: utf-8 -*-

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

import os

from supervisor.http import NOT_DONE_YET
from supervisor.options import split_namespec
from supervisor.xmlrpc import capped_int, Faults, RPCError

from supervisors.ttypes import (AddressStates, ApplicationStates,
    DeploymentStrategies, SupervisorsStates)
from supervisors.utils import supervisors_short_cuts

# get Supervisors version from file
here = os.path.abspath(os.path.dirname(__file__))
version_txt = os.path.join(here, 'version.txt')
API_VERSION  = open(version_txt).read().strip()


class RPCInterface(object):
    """ This class holds the XML-RPC extension provided by Supervisors. """

    def __init__(self, supervisors):
        self.supervisors = supervisors
        supervisors_short_cuts(self, ['context', 'info_source', 'logger', 'requester'])
        self.address = supervisors.address_mapper.local_address

    # RPC Status methods
    def get_api_version(self):
        """ Return the version of the RPC API used by Supervisors.
        @return string result\tThe version id.
        """
        return API_VERSION

    def get_supervisors_state(self):
        """ Return the state of Supervisors.
        @return struct result\tThe state of Supervisors as an integer and a string.
        """
        return {'statecode': self.supervisors.fsm.state,
            'statename': SupervisorsStates._to_string(self.supervisors.fsm.state)}

    def get_master_address(self):
        """ Get the address of the Supervisors Master.
        @return string result\tThe IPv4 address or host name.
        """
        return self.context.master_address

    def get_all_addresses_info(self):
        """ Get info about all remote supervisord managed in Supervisors.
        @return list result\tA list of structures containing data about all remote supervisord.
        """
        return [self.get_address_info(address) for address in self.context.addresses]

    def get_address_info(self, address):
        """ Get info about a remote supervisord managed in Supervisors and running on address.
        @param string address\tThe address of the supervisord.
        @return struct result\t\tA structure containing data about the remote supervisord.
        """
        try:
            status = self.context.addresses[address]
        except KeyError:
            raise RPCError(Faults.BAD_ADDRESS, 'address {} unknown in Supervisors'.format(address))
        return {'address_name': address, 'state': status.state_string(),
            'remote_time': capped_int(status.remote_time), 'local_time': capped_int(status.local_time),
            'loading': status.loading()}

    def get_all_applications_info(self):
        """ Get info about all applications managed in Supervisors.
        @return list result\tA list of structures containing data about all applications.
        """
        self._check_from_deployment()
        return [self.get_application_info(application_name) for application_name in self.context.applications.keys()]

    def get_application_info(self, application_name):
        """ Get info about an application named application_name.
        @param string application_name\tThe name of the application.
        @return struct result\tA structure containing data about the application.
        """
        self._check_from_deployment()
        application = self._get_application(application_name)
        return {'application_name': application.application_name, 'state': application.state_string(), 
            'major_failure': application.major_failure, 'minor_failure': application.minor_failure}

    def get_process_info(self, namespec):
        """ Get info about a process named namespec.
        It just complements supervisor ProcessInfo by telling where the process is running.
        @param string namespec\tThe process name (or ``group:name``, or ``group:*``).
        @return list result\tA list of structures containing data about the processes.
        """
        self._check_from_deployment()
        application, process = self._get_application_process(namespec)
        if process:
            return [self._get_internal_process_info(process)]
        return [self._get_internal_process_info(proc) for proc in application.processes.values()]

    def get_process_rules(self, namespec):
        """ Get the rules used to deploy the process named namespec.
        @param string namespec\tThe process name (or ``group:name``, or ``group:*``).
        @return list result\tA list of structures containing data about the deployment rules.
        """
        application, process = self._get_application_process(namespec)
        if process:
            return [self._get_internal_process_rules(process)]
        return [self._get_internal_process_rules(proc) for proc in application.processes.values()]

    def get_conflicts(self):
        """ Get the conflicting processes.
        @return list result\t\t\tA list of structures containing data about the conflicting processes.
        """
        return [self._get_internal_process_info(process) for application in self.context.applications.values()
            for process in application.processes.values() if process.conflicting()]

    # RPC Command methods
    def start_application(self, strategy, application_name, wait=True):
        """ Start the application named application_name iaw the strategy and the rules defined in the deployment file.
        @param DeploymentStrategies strategy\tThe strategy to use for choosing addresses.
        @param string application_name\tThe name of the application.
        @param boolean wait\tWait for application to be fully started.
        @return boolean result\tAlways True unless error or nothing to start.
        """
        self._check_operating()
        # check strategy
        if strategy not in DeploymentStrategies._values():
            raise RPCError(Faults.BAD_STRATEGY, '{}'.format(strategy))
        # check application is known
        if application_name not in self.context.applications.keys():
            raise RPCError(Faults.BAD_NAME, application_name)
        # check application is not already RUNNING
        application = self.context.applications[application_name]
        if application.state == ApplicationStates.RUNNING:
            raise RPCError(Faults.ALREADY_STARTED, application_name)
        # TODO: develop a predictive model to check if deployment can be achieved
        # if impossible due to a lack of resources, second try without optionals
        # return false if still impossible
        done = self.supervisors.starter.start_application(strategy, application)
        self.logger.debug('start_application {} done={}'.format(application_name, done))
        # wait until application fully RUNNING or (failed)
        if wait and not done:
            def onwait():
                # check starter
                if self.supervisors.starter.in_progress():
                    return NOT_DONE_YET
                if application.state != ApplicationStates.RUNNING:
                    raise RPCError(Faults.ABNORMAL_TERMINATION, application_name)
                return True
            onwait.delay = 0.5
            return onwait # deferred
        # if done is True, nothing to do (no deployment or impossible to deploy)
        return not done

    def stop_application(self, application_name, wait=True):
        """ Stop the application named application_name.
        @param string application_name\tThe name of the application.
        @param boolean wait\tWait for application to be fully stopped.
        @return boolean result\tAlways True unless error.
        """
        self._check_operating_conciliation()
        # check application is known
        if application_name not in self.context.applications.keys():
            raise RPCError(Faults.BAD_NAME, application_name)
        # do NOT check application state as there may be processes RUNNING although the application is declared STOPPED
        application = self.context.applications[application_name]
        done = self.supervisors.stopper.stop_application(application)
        self.logger.debug('stop_application {} done={}'.format(application_name, done))
        # wait until application fully STOPPED
        if wait and not done:
            def onwait():
                # check stopper
                if self.supervisors.stopper.in_progress():
                    return NOT_DONE_YET
                if application.state != ApplicationStates.STOPPED:
                    raise RPCError(Faults.ABNORMAL_TERMINATION, application_name)
                return True
            onwait.delay = 0.5
            return onwait # deferred
        # if done is True, nothing to do
        return not done

    def restart_application(self, strategy, application_name, wait=True):
        """ Restart the application named application_name iaw the strategy and the rules defined in the deployment file.
        @param DeploymentStrategies strategy\tThe strategy to use for choosing addresses.
        @param string application_name\tThe name of the application.
        @param boolean wait\tWait for application to be fully stopped.
        @return boolean result\tAlways True unless error.
        """
        self._check_operating()
        def onwait():
            # first wait for application to be stopped
            if onwait.waitstop:
                # job may be a boolean value if stop_application has nothing to do
                value = type(onwait.job) is bool or onwait.job()
                if value is True:
                    # done. request start application
                    onwait.waitstop = False
                    value = self.start_application(strategy, application_name, wait)
                    if type(value) is bool:
                        return value
                    # deferred job to wait for application to be started
                    onwait.job = value
                return NOT_DONE_YET
            return onwait.job()
        onwait.delay = 0.5
        onwait.waitstop = True
        # request stop application. job is for deferred result
        onwait.job = self.stop_application(application_name, True)
        return onwait # deferred

    def start_args(self, namespec, extra_args='', wait=True):
        """ Start a local process.
        The behaviour is different from 'supervisor.startProcess' as it sets the process state to FATAL
        instead of throwing an exception to the RPC client.
        This RPC makes it also possible to pass extra arguments to the program command line.
        @param string name\tThe process name.
        @param string extra_args\tExtra arguments to be passed to the command line of the program.
        @param boolean wait\tWait for process to be fully started.
        @return boolean result\tAlways true unless error.
        """
        # prevent usage of extra_args when required or auto_start
        application, process = self._get_application_process(namespec)
        if extra_args and not process.rules.accept_extra_arguments():
            raise RPCError(Faults.BAD_EXTRA_ARGUMENTS, 'rules for namespec {} are not compatible with extra arguments in command line'.format(namespec))
        # update command line in process config with extra_args
        try:
            self.info_source.update_extra_args(namespec, extra_args)
        except KeyError:
            # process is unknown to the local Supervisor
            # this should not happen as Supervisors checks the configuration before it sends this request
            self.logger.error('could not find {} in supervisord processes'.format(namespec))
            raise RPCError(Faults.BAD_NAME, 'namespec {} unknown in this Supervisor instance'.format(namespec))
        # start process with Supervisor internal RPC
        try:
            cb = self.info_source.supervisor_rpc_interface.startProcess(namespec, wait)
        except RPCError, why:
            self.logger.error('start_process {} failed: {}'.format(namespec, why))
            if why.code in [Faults.NO_FILE, Faults.NOT_EXECUTABLE]:
                self.logger.warn('force supervisord internal state of {} to FATAL'.format(namespec))
                # at this stage, process is known to the local Supervisor
                self.info_source.force_process_fatal(namespec, why.text)
            # else process is already started
            # this should not happen as Supervisors checks the process state before it sends this request
            # anyway raise exception again
            raise
        return cb

    def start_process(self, strategy, namespec, extra_args='', wait=True):
        """ Start a process named namespec iaw the strategy and some of the rules defined in the deployment file.
        WARN; the 'wait_exit' rule is not considered here.
        @param DeploymentStrategies strategy\tThe strategy to use for choosing addresses.
        @param string namespec\tThe process name (or ``group:name``, or ``group:*``).
        @param string extra_args\tExtra arguments to be passed to command line.
        @param boolean wait\tWait for process to be fully started.
        @return boolean result\tAlways true unless error.
        """
        self._check_operating()
        # check strategy
        if strategy not in DeploymentStrategies._values():
            raise RPCError(Faults.BAD_STRATEGY, '{}'.format(strategy))
        # check names
        application, process = self._get_application_process(namespec)
        processes = [process] if process else application.processes.values()
        # check processes are not already RUNNING
        for process in processes:
            if process.running():
                raise RPCError(Faults.ALREADY_STARTED, process.namespec())
        # start all processes
        done = True
        for process in processes:
            done &= self.supervisors.starter.start_process(strategy, process, extra_args)
        self.logger.debug('startProcess {} done={}'.format(process.namespec(), done))
        # wait until application fully RUNNING or (failed)
        if wait and not done:
            def onwait():
                # check starter
                if self.supervisors.starter.in_progress():
                    return NOT_DONE_YET
                for process in processes:
                    if process.stopped():
                        raise RPCError(Faults.ABNORMAL_TERMINATION, process.namespec())
                return True
            onwait.delay = 0.5
            return onwait # deferred
        # if done is True, nothing to do (no deployment or impossible to deploy)
        return not done

    def stop_process(self, namespec, wait=True):
        """ Stop the process named namespec where it is running.
        @param string namespec\tThe process name (or ``group:name``, or ``group:*``).
        @param boolean wait\tWait for process to be fully stopped.
        @return boolean result\tAlways True unless error.
        """
        self._check_operating_conciliation()
        # check names
        application, process = self._get_application_process(namespec)
        processes = [process] if process else application.processes.values()
        # stop all processes
        for process in processes:
            if process.running():
                for address in process.addresses:
                    self.logger.info('stopping process {} on {}'.format(process.namespec(), address))
                    self.supervisors.requester.stop_process(address, process.namespec(), False)
            else:
                self.logger.info('process {} already stopped'.format(process.namespec()))
        # wait until processes are in STOPPED_STATES
        if wait:
            def onwait():
                for process in processes:
                    if not process.stopped():
                        return NOT_DONE_YET
                return True
            onwait.delay = 0.5
            return onwait # deferred
        return True

    def restart_process(self, strategy, namespec, extra_args='', wait=True):
        """ Restart a process named namespec iaw the strategy and some of the rules defined in the deployment file.
        WARN; the 'wait_exit' rule is not considered here.
        @param DeploymentStrategies strategy\tThe strategy to use for choosing addresses.
        @param string namespec\tThe process name (or ``group:name``, or ``group:*``).
        @param string extra_args\tExtra arguments to be passed to command line.
        @param boolean wait\tWait for process to be fully stopped.
        @return boolean result\tAlways True unless error.
        """
        self._check_operating()
        def onwait():
            # first wait for process to be stopped
            if onwait.waitstop:
                value = onwait.job()
                if value is True:
                    # done. request start process
                    onwait.waitstop = False
                    value = self.start_process(strategy, namespec, extra_args, wait)
                    if type(value) is bool:
                        return value
                    # deferred job to wait for process to be started
                    onwait.job = value
                return NOT_DONE_YET
            return onwait.job()
        onwait.delay = 0.5
        onwait.waitstop = True
        # request stop process. job is for deferred result
        onwait.job = self.stop_process(namespec, True)
        return onwait # deferred

    def restart(self):
        """ Restart Supervisors through all remote supervisord.
        @return boolean result\tAlways True unless error.
        """
        return self._send_addresses_func(self.supervisors.requester.restart)

    def shutdown(self):
        """ Shut down Supervisors through all remote supervisord.
        @return boolean result\tAlways True unless error.
        """
        return self._send_addresses_func(self.supervisors.requester.shutdown)


    # utilities
    def _check_from_deployment(self):
        """ Raises a BAD_SUPERVISORS_STATE exception if Supervisors' state is in INITIALIZATION. """
        self._check_state([SupervisorsStates.DEPLOYMENT, SupervisorsStates.OPERATION, SupervisorsStates.CONCILIATION])

    def _check_operating_conciliation(self):
        """ Raises a BAD_SUPERVISORS_STATE exception if Supervisors' state is NOT in OPERATION or CONCILIATION. """
        self._check_state([SupervisorsStates.OPERATION, SupervisorsStates.CONCILIATION])

    def _check_operating(self):
        """ Raises a BAD_SUPERVISORS_STATE exception if Supervisors' state is NOT in OPERATION. """
        self._check_state([SupervisorsStates.OPERATION])

    def _check_state(self, states):
        """ Raises a BAD_SUPERVISORS_STATE exception if Supervisors' state is NOT in one of the states. """
        if self.supervisors.fsm.state not in states:
            raise RPCError(Faults.BAD_SUPERVISORS_STATE, 'Supervisors (state={}) not in state {} to perform request'.
                format(SupervisorsStates._to_string(self.supervisors.fsm.state), [SupervisorsStates._to_string(state) for state in states]))

    # almost equivalent to the method in supervisor.rpcinterface
    def _get_application_process(self, namespec):
        """ Return the ApplicationStatus and ProcessStatus corresponding to the namespec.
        A BAD_NAME exception is raised if the application or the process is not found. """
        application_name, process_name = split_namespec(namespec)
        return self._get_application(application_name), self._get_process(namespec) if process_name else None

    def _get_application(self, application_name):
        """ Return the ApplicationStatus corresponding to the application name.
        A BAD_NAME exception is raised if the application is not found. """
        try:
            application = self.context.applications[application_name]
        except KeyError:
            raise RPCError(Faults.BAD_NAME, 'application {} unknown in Supervisors'.format(application_name))
        return application

    def _get_process(self, namespec):
        """ Return the ProcessStatus corresponding to the namespec.
        A BAD_NAME exception is raised if the process is not found. """
        try:
            process = self.context.processes[namespec]
        except KeyError:
            raise RPCError(Faults.BAD_NAME, 'process {} unknown in Supervisors'.format(namespec))
        return process

    def _get_internal_process_info(self, process):
        """ Return a dictionary with the information of the process. """
        return {'namespec': process.namespec(), 'state': process.state_string(), 'address': list(process.addresses)}

    def _get_internal_process_rules(self, process):
        """ Return a dictionary with the rules of the process. """
        rules = process.rules
        return {'namespec': process.namespec(), 'addresses': rules.addresses,
            'start_sequence': rules.start_sequence, 'stop_sequence': rules.stop_sequence,
            'required': rules.required, 'wait_exit': rules.wait_exit, 'expected_loading': rules.expected_loading}

    def _send_addresses_func(self, func):
        """ Perfrom the action func on all addresses.
        The local address is the last to be performed. """
        # send func request to all locals (but self address)
        for status in self.context.addresses.values():
            if status.address != self.address:
                if status.state == AddressStates.RUNNING and status.address != self.address:
                    try:
                        func(status.address)
                        self.logger.warn('supervisord {} on {}'.format(func.__name__, status.address))
                    except RPCError:
                        self.logger.error('failed to {} supervisord on {}'.format(func.__name__, status.address))
                else:
                    self.logger.info('cannot {} supervisord on {}: Remote state is {}'.format(func.__name__, status.address, status.state_string()))
        # send request to self supervisord
        return func(self.address)

