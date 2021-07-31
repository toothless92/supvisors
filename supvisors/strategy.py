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

from typing import Mapping, Sequence, Tuple

from .ttypes import AddressStates, NameList, ConciliationStrategies, StartingStrategies, RunningFailureStrategies


class AbstractStrategy(object):
    """ Base class for a common constructor. """

    def __init__(self, supvisors):
        """ Initialization of the attributes.

        :param supvisors: the global Supvisors instance
        """
        self.supvisors = supvisors
        self.logger = supvisors.logger


# Strategy management for Starting
class AbstractStartingStrategy(AbstractStrategy):
    """ Base class for a starting strategy. """

    # Annotation types
    LoadingValidity = Tuple[bool, int]
    LoadingValidityMap = Mapping[str, LoadingValidity]
    NodeLoadMap = Sequence[Tuple[str, int]]

    def is_loading_valid(self, node_name: str, expected_load: int) -> LoadingValidity:
        """ Return True and current load if remote Supvisors instance is active
        and can support the additional load.

        :param node_name: the node name tested
        :param expected_load: the load to add to the node
        :return: a tuple with a boolean telling if the additional load is possible on node and the current load
        """
        self.logger.trace('AbstractStartingStrategy.is_loading_valid: node_name={} expected_load={}'
                          .format(node_name, expected_load))
        if node_name in self.supvisors.context.nodes.keys():
            status = self.supvisors.context.nodes[node_name]
            self.logger.trace('AbstractStartingStrategy.is_loading_valid: node {} state={}'
                              .format(node_name, status.state.name))
            if status.state == AddressStates.RUNNING:
                load = status.get_load()
                self.logger.debug('AbstractStartingStrategy.is_loading_valid:node={} loading={} expected_load={}'
                                  .format(node_name, load, expected_load))
                return load + expected_load < 100, load
            self.logger.trace('AbstractStartingStrategy.is_loading_valid: node {} not RUNNING'.format(node_name))
        return False, 0

    def get_loading_and_validity(self, node_names: NameList, expected_load: int) -> LoadingValidityMap:
        """ Return the report of loading capability of all nodes iaw the additional load required.

        :param node_names: the nodes considered
        :param expected_load: the additional load to consider
        :return: the list of nodes that can hold the additional load
        """
        loading_validity_map = {node_name: self.is_loading_valid(node_name, expected_load)
                                for node_name in node_names}
        self.logger.trace('AbstractStartingStrategy.get_loading_and_validity: loading_validity_map={}'
                          .format(loading_validity_map))
        return loading_validity_map

    def sort_valid_by_loading(self, loading_validity_map: LoadingValidityMap) -> NodeLoadMap:
        """ Sort the loading report by loading value. """
        # returns nodes with validity and loading
        sorted_nodes = sorted([(x, y[1])
                               for x, y in loading_validity_map.items()
                               if y[0]], key=lambda t: t[1])
        self.logger.trace('AbstractStartingStrategy.sort_valid_by_loading: sorted_nodes={}'.format(sorted_nodes))
        return sorted_nodes


class ConfigStrategy(AbstractStartingStrategy):
    """ Strategy designed to choose the node using the order defined in the configuration file. """

    def get_node(self, node_names, expected_load):
        """ Choose the first node that can support the additional load requested. """
        self.logger.debug('ConfigStrategy.get_node: node_names={} expected_load={}'
                          .format(node_names, expected_load))
        loading_validity_map = self.get_loading_and_validity(node_names, expected_load)
        return next((node_name for node_name, (validity, _) in loading_validity_map.items() if validity), None)


class LessLoadedStrategy(AbstractStartingStrategy):
    """ Strategy designed to share the loading among all the nodes. """

    def get_node(self, node_names, expected_load):
        """ Choose the node having the lowest loading that can support the additional load requested. """
        self.logger.trace('LessLoadedStrategy.get_node: node_names={} expected_load={}'
                          .format(node_names, expected_load))
        loading_validity_map = self.get_loading_and_validity(node_names, expected_load)
        sorted_nodes = self.sort_valid_by_loading(loading_validity_map)
        return sorted_nodes[0][0] if sorted_nodes else None


class MostLoadedStrategy(AbstractStartingStrategy):
    """ Strategy designed to maximize the loading of a node. """

    def get_node(self, node_names, expected_load):
        """ Choose the node having the highest loading that can support the additional load requested. """
        self.logger.trace('MostLoadedStrategy: node_names={} expected_load={}'.format(node_names, expected_load))
        loading_validity_map = self.get_loading_and_validity(node_names, expected_load)
        sorted_nodes = self.sort_valid_by_loading(loading_validity_map)
        return sorted_nodes[-1][0] if sorted_nodes else None


class LocalStrategy(AbstractStartingStrategy):
    """ Strategy designed to start the process on the local node. """

    def get_node(self, node_names, expected_load):
        """ Choose the local node provided that it can support the additional load requested. """
        self.logger.trace('LocalStrategy: node_names={} expected_load={}'.format(node_names, expected_load))
        loading_validity_map = self.get_loading_and_validity(node_names, expected_load)
        local_node_name = self.supvisors.address_mapper.local_node_name
        return local_node_name if loading_validity_map.get(local_node_name, (False,))[0] else None


def get_node(supvisors, strategy, node_rules, expected_load):
    """ Creates a strategy and let it find a node to start a process having a defined load. """
    instance = None
    if strategy == StartingStrategies.CONFIG:
        instance = ConfigStrategy(supvisors)
    if strategy == StartingStrategies.LESS_LOADED:
        instance = LessLoadedStrategy(supvisors)
    if strategy == StartingStrategies.MOST_LOADED:
        instance = MostLoadedStrategy(supvisors)
    if strategy == StartingStrategies.LOCAL:
        instance = LocalStrategy(supvisors)
    # apply strategy result
    return instance.get_node(node_rules, expected_load) if instance else None


# Strategy management for Conciliation
class SenicideStrategy(AbstractStrategy):
    """ Strategy designed to stop the oldest processes. """

    def conciliate(self, conflicts):
        """ Conciliate the conflicts by finding the process that started the most recently and stopping the others """
        for process in conflicts:
            # determine running node with lower uptime (the youngest)
            # uptime is used as there is guarantee that nodes are time synchronized
            # so comparing start dates may be irrelevant
            saved_node = min(process.running_nodes, key=lambda x: process.info_map[x]['uptime'])
            self.logger.warn('SenicideStrategy.conciliate: keep {} at {}'.format(process.namespec, saved_node))
            # stop other processes. work on copy as it may change during iteration
            # Stopper can't be used here as it would stop all processes
            running_nodes = process.running_nodes.copy()
            running_nodes.remove(saved_node)
            for node_name in running_nodes:
                self.logger.debug('SenicideStrategy.conciliate: {} running on {}'.format(process.namespec, node_name))
                self.supvisors.zmq.pusher.send_stop_process(node_name, process.namespec)


class InfanticideStrategy(AbstractStrategy):
    """ Strategy designed to stop the youngest processes. """

    def conciliate(self, conflicts):
        """ Conciliate the conflicts by finding the process that started the least recently and stopping the others """
        for process in conflicts:
            # determine running node with lower uptime (the youngest)
            saved_node = max(process.running_nodes, key=lambda x: process.info_map[x]['uptime'])
            self.logger.warn('InfanticideStrategy.conciliate: keep {} at {}'.format(process.namespec, saved_node))
            # stop other processes. work on copy as it may change during iteration
            # Stopper can't be used here as it would stop all processes
            running_nodes = process.running_nodes.copy()
            running_nodes.remove(saved_node)
            for node_name in running_nodes:
                self.logger.debug('InfanticideStrategy.conciliate: {} running on {}'
                                  .format(process.namespec, node_name))
                self.supvisors.zmq.pusher.send_stop_process(node_name, process.namespec)


class UserStrategy(AbstractStrategy):
    """ Strategy designed to let the user do the job. """

    def conciliate(self, conflicts):
        """ Does nothing. """
        pass


class StopStrategy(AbstractStrategy):
    """ Strategy designed to stop all conflicting processes. """

    def conciliate(self, conflicts):
        """ Conciliate the conflicts by stopping all processes. """
        for process in conflicts:
            self.logger.warn('StopStrategy.conciliate: {}'.format(process.namespec))
            self.supvisors.stopper.stop_process(process)


class RestartStrategy(AbstractStrategy):
    """ Strategy designed to stop all conflicting processes and to restart a single instance. """

    def conciliate(self, conflicts):
        """ Conciliate the conflicts by notifying the failure handler to restart the process. """
        # add all processes to be restarted to the failure handler,
        # as it is in its design to restart a process
        for process in conflicts:
            self.logger.warn('RestartStrategy.conciliate: {}'.format(process.namespec))
            self.supvisors.failure_handler.add_job(RunningFailureStrategies.RESTART_PROCESS, process)
        # trigger the jobs of the failure handler directly (could wait for next tick)
        self.supvisors.failure_handler.trigger_jobs()


class FailureStrategy(AbstractStrategy):
    """ Strategy designed to stop all conflicting processes and to apply the running failure strategy
    related to the process. """

    def conciliate(self, conflicts):
        """ Conciliate the conflicts by notifying the failure handler to apply the running failure strategy
        related to the process. """
        # stop all processes and add them to the failure handler
        for process in conflicts:
            self.supvisors.stopper.stop_process(process)
            self.logger.warn('FailureStrategy.conciliate: {}'.format(process.namespec))
            self.supvisors.failure_handler.add_default_job(process)
        # trigger the jobs of the failure handler directly (could wait for next tick)
        self.supvisors.failure_handler.trigger_jobs()


def conciliate_conflicts(supvisors, strategy, conflicts):
    """ Creates a strategy and let it conciliate the conflicts. """
    instance = None
    if strategy == ConciliationStrategies.SENICIDE:
        instance = SenicideStrategy(supvisors)
    elif strategy == ConciliationStrategies.INFANTICIDE:
        instance = InfanticideStrategy(supvisors)
    elif strategy == ConciliationStrategies.USER:
        instance = UserStrategy(supvisors)
    elif strategy == ConciliationStrategies.STOP:
        instance = StopStrategy(supvisors)
    elif strategy == ConciliationStrategies.RESTART:
        instance = RestartStrategy(supvisors)
    elif strategy == ConciliationStrategies.RUNNING_FAILURE:
        instance = FailureStrategy(supvisors)
    # apply strategy to conflicts
    if instance:
        instance.conciliate(conflicts)


# Strategy management for a Running Failure
class RunningFailureHandler(AbstractStrategy):
    """ Handler of running failures.
    The strategies are linked to the RunningFailureStrategies enumeration.

    Any Supvisors instance may hold application processes with different running failure strategies.
    If the Supvisors instance becomes inactive, as seen from another Supvisors instance, it could lead
    to have all possible strategies to apply on the same application and related processes, which makes no sense.

    So it has been chosen to give a priority to the strategies.
    The highest priority is for the most restricting strategy, consisting in stopping the application.
    Then, the priority goes to the strategy having the highest impact, i.e. restarting the application.
    The lowest priority is for the most simple strategy consisting in restarting only the involved process.

    Attributes are:

        - stop_application_jobs: the set of application names to be stopped,
        - restart_application_jobs: the set of application names to be restarted,
        - restart_process_jobs: the set of processes to be restarted.
        - continue_process_jobs: the set of processes to be ignored (only for log).
        - start_application_jobs: the set of application to be started (deferred job).
        - start_process_jobs: the set of processes to be started (deferred job).
    """

    def __init__(self, supvisors):
        AbstractStrategy.__init__(self, supvisors)
        # the initial jobs
        self.stop_application_jobs = set()
        self.restart_application_jobs = set()
        self.restart_process_jobs = set()
        self.continue_process_jobs = set()
        # the deferred jobs
        self.start_application_jobs = set()
        self.start_process_jobs = set()

    def abort(self):
        """ Clear all sets. """
        self.stop_application_jobs = set()
        self.restart_application_jobs = set()
        self.restart_process_jobs = set()
        self.continue_process_jobs = set()
        self.start_application_jobs = set()
        self.start_process_jobs = set()

    def add_job(self, strategy, process):
        """ Add a process or the related application name in the relevant set,
        iaw the strategy set in parameter and the priorities defined above. """
        self.logger.trace('RunningFailureHandler.add_job: START stop_application_jobs={} restart_application_jobs={}'
                          ' restart_application_jobs={} restart_process_jobs={} continue_process_jobs={}'
                          ' start_application_jobs={} start_process_jobs={}'
                          .format(self.stop_application_jobs, self.restart_application_jobs,
                                  self.restart_application_jobs, self.restart_process_jobs, self.continue_process_jobs,
                                  self.start_application_jobs, self.start_process_jobs))
        application_name = process.application_name
        if strategy == RunningFailureStrategies.STOP_APPLICATION:
            self.logger.info('RunningFailureHandler.add_job: adding {} to stop_application_jobs'
                             .format(application_name))
            self.stop_application_jobs.add(application_name)
            self.restart_application_jobs.discard(application_name)
            self.restart_process_jobs = set(filter(lambda x: x.application_name != application_name,
                                                   self.restart_process_jobs))
            self.continue_process_jobs = set(filter(lambda x: x.application_name != application_name,
                                                    self.continue_process_jobs))
        elif strategy == RunningFailureStrategies.RESTART_APPLICATION:
            if application_name not in self.stop_application_jobs:
                self.logger.info('RunningFailureHandler.add_job: adding {} to restart_application_jobs'
                                 .format(application_name))
                self.restart_application_jobs.add(application_name)
                self.restart_process_jobs = set(filter(lambda x: x.application_name != application_name,
                                                       self.restart_process_jobs))
                self.continue_process_jobs = set(filter(lambda x: x.application_name != application_name,
                                                        self.continue_process_jobs))
            else:
                self.logger.info('RunningFailureHandler.add_job: {} not added to restart_application_jobs'
                                 ' because already in stop_application_jobs'.format(application_name))
        elif strategy == RunningFailureStrategies.RESTART_PROCESS:
            if process.application_name not in (self.stop_application_jobs | self.restart_application_jobs):
                self.logger.info('RunningFailureHandler.add_job: adding {} to restart_process_jobs'
                                 .format(process.namespec))
                self.restart_process_jobs.add(process)
                self.continue_process_jobs.discard(process)
            else:
                self.logger.info('RunningFailureHandler.add_job: {} not added to restart_process_jobs'
                                 ' because already in stop_application_jobs or restart_application_jobs'
                                 .format(application_name))
        elif strategy == RunningFailureStrategies.CONTINUE:
            if process.application_name not in (self.stop_application_jobs | self.restart_application_jobs) and \
                    process not in self.restart_process_jobs:
                self.logger.info('RunningFailureHandler.add_job: adding {} to continue_process_jobs'
                                 .format(process.namespec))
                self.continue_process_jobs.add(process)
            else:
                self.logger.info('RunningFailureHandler.add_job: {} not added to continue_process_jobs'
                                 ' because already in stop_application_jobs or restart_application_jobs'
                                 ' or restart_process_jobs'.format(application_name))
        self.logger.trace('RunningFailureHandler.add_job: END stop_application_jobs={} restart_application_jobs={}'
                          ' restart_application_jobs={} restart_process_jobs={} continue_process_jobs={}'
                          ' start_application_jobs={} start_process_jobs={}'
                          .format(self.stop_application_jobs, self.restart_application_jobs,
                                  self.restart_application_jobs, self.restart_process_jobs, self.continue_process_jobs,
                                  self.start_application_jobs, self.start_process_jobs))

    def add_default_job(self, process):
        """ Add a process or the related application name in the relevant set,
        iaw the strategy set in process rules and the priorities defined above. """
        self.add_job(process.rules.running_failure_strategy, process)

    def get_job_applications(self) -> bool:
        """ Get all application names involved in Commanders.

        :return: the list of application names
        """
        return self.supvisors.starter.get_job_applications() | self.supvisors.stopper.get_job_applications()

    def trigger_jobs(self):
        """ Trigger the configured strategy when a process of a running application crashes. """
        job_applications = self.get_job_applications()
        # consider applications to stop
        if self.stop_application_jobs:
            for application_name in self.stop_application_jobs.copy():
                application = self.supvisors.context.applications[application_name]
                if application_name in job_applications:
                    self.logger.debug('RunningFailureHandler.trigger_jobs: stop application {} deferred'
                                      .format(application_name))
                else:
                    self.logger.info('RunningFailureHandler.trigger_jobs: stop application {}'
                                     .format(application_name))
                    self.stop_application_jobs.remove(application_name)
                    self.supvisors.stopper.stop_application(application)
        # consider applications to restart
        if self.restart_application_jobs:
            for application_name in self.restart_application_jobs.copy():
                application = self.supvisors.context.applications[application_name]
                if application_name in job_applications:
                    self.logger.debug('RunningFailureHandler.trigger_jobs: restart application {} deferred'
                                      .format(application_name))
                else:
                    self.logger.warn('RunningFailureHandler.trigger_jobs: restart application {}'
                                     .format(application_name))
                    self.restart_application_jobs.remove(application_name)
                    # first stop the application
                    self.supvisors.stopper.stop_application(application)
                    # defer the application starting
                    self.start_application_jobs.add(application)
        # consider processes to restart
        if self.restart_process_jobs:
            for process in self.restart_process_jobs.copy():
                if process.application_name in job_applications:
                    self.logger.debug('RunningFailureHandler.trigger_jobs: restart process {} deferred'
                                      .format(process.namespec))
                else:
                    self.logger.info('RunningFailureHandler.trigger_jobs: restart process {}'
                                     .format(process.namespec))
                    self.restart_process_jobs.remove(process)
                    self.supvisors.stopper.stop_process(process)
                    # defer the process starting
                    self.start_process_jobs.add(process)
        # consider applications to start
        if self.start_application_jobs:
            for application in self.start_application_jobs.copy():
                if application.stopped() and application.application_name not in job_applications:
                    self.logger.info('RunningFailureHandler.trigger_jobs: start application {}'
                                     .format(application.application_name))
                    self.start_application_jobs.remove(application)
                    self.supvisors.starter.default_start_application(application)
                else:
                    self.logger.debug('RunningFailureHandler.trigger_jobs: start application {} deferred'
                                      .format(application.application_name))
        # consider processes to start
        if self.start_process_jobs:
            for process in self.start_process_jobs.copy():
                if process.stopped() and process.application_name not in job_applications:
                    self.logger.warn('RunningFailureHandler.trigger_jobs: start process {}'
                                     .format(process.namespec))
                    self.start_process_jobs.remove(process)
                    self.supvisors.starter.default_start_process(process)
                else:
                    self.logger.debug('RunningFailureHandler.trigger_jobs: start process {} deferred'
                                      .format(process.namespec))
        # log only the continuation jobs
        if self.continue_process_jobs:
            for process in self.continue_process_jobs:
                self.logger.info('RunningFailureHandler.trigger_jobs: continue despite of crashed process {}'
                                 .format(process.namespec))
            self.continue_process_jobs = set()
