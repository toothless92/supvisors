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

from supervisor.http import NOT_DONE_YET
from supervisor.xmlrpc import RPCError

from supvisors.ttypes import StartingStrategies
from supvisors.viewcontext import *
from supvisors.viewhandler import ViewHandler
from supvisors.webutils import *


class ApplicationView(ViewHandler):
    """ Supvisors Application page. """

    def __init__(self, context):
        """ Call of the superclass constructors. """
        ViewHandler.__init__(self, context)
        self.page_name = APPLICATION_PAGE
        # init parameters
        self.application_name = ''
        self.application = None

    def handle_parameters(self):
        """ Retrieve the parameters selected on the web page. """
        ViewHandler.handle_parameters(self)
        # check if application name is available
        self.application_name = self.view_ctx.parameters[APPLI]
        if self.application_name:
            # store application
            self.application = self.sup_ctx.applications[self.application_name]
        else:
            self.view_ctx.message(error_message('No application'))

    def write_navigation(self, root):
        """ Rendering of the navigation menu with selection
        of the current application. """
        self.write_nav(root, appli=self.application_name)

    def write_header(self, root):
        """ Rendering of the header part of the Supvisors Application page. """
        # set address name
        elt = root.findmeld('application_mid')
        elt.content(self.application_name)
        # set application state
        elt = root.findmeld('state_mid')
        elt.content(self.application.state_string())
        # set LED iaw major/minor failures
        elt = root.findmeld('state_led_mid')
        if self.application.running():
            if self.application.major_failure:
                elt.attrib['class'] = 'status_red'
            elif self.application.minor_failure:
                elt.attrib['class'] = 'status_yellow'
            else:
                elt.attrib['class'] = 'status_green'
        else:
            elt.attrib['class'] = 'status_empty'
        # write periods of statistics
        self.write_starting_strategy(root)
        self.write_periods(root)
        # write actions related to application
        self.write_application_actions(root)

    def write_starting_strategy(self, root):
        """ Write applicable starting strategies. """
        # get the current strategy
        strategy = self.supvisors.starter.strategy
        # set hyperlinks for strategy actions
        # CONFIG strategy
        elt = root.findmeld('config_a_mid')
        if strategy == StartingStrategies.CONFIG:
            elt.attrib['class'] = 'button off active'
        else:
            url = self.view_ctx.format_url('', self.page_name,
                                           **{ACTION: 'config'})
            elt.attributes(href=url)
        # MOST_LOADED strategy
        elt = root.findmeld('most_a_mid')
        if strategy == StartingStrategies.MOST_LOADED:
            elt.attrib['class'] = 'button off active'
        else:
            url = self.view_ctx.format_url('', self.page_name,
                                           **{ACTION: 'most'})
            elt.attributes(href=url)
        # LESS_LOADED strategy
        elt = root.findmeld('less_a_mid')
        if strategy == StartingStrategies.LESS_LOADED:
            elt.attrib['class'] = 'button off active'
        else:
            url = self.view_ctx.format_url('', self.page_name,
                                           **{ACTION: 'less'})
            elt.attributes(href=url)

    def write_application_actions(self, root):
        """ Write actions related to the application. """
        # set hyperlinks for global actions
        elt = root.findmeld('refresh_a_mid')
        url = self.view_ctx.format_url('', self.page_name,
                                       **{ACTION: 'refresh'})
        elt.attributes(href=url)
        elt = root.findmeld('startapp_a_mid')
        url = self.view_ctx.format_url('', self.page_name,
                                       **{ACTION: 'startapp'})
        elt.attributes(href=url)
        elt = root.findmeld('stopapp_a_mid')
        url = self.view_ctx.format_url('', self.page_name,
                                       **{ACTION: 'stopapp'})
        elt.attributes(href=url)
        elt = root.findmeld('restartapp_a_mid')
        url = self.view_ctx.format_url('', self.page_name,
                                       **{ACTION: 'restartapp'})
        elt.attributes(href=url)

    def write_contents(self, root):
        """ Rendering of the contents part of the page. """
        self.write_process_table(root)
        # check selected Process Statistics
        namespec = self.view_ctx.parameters[PROCESS]
        if namespec:
            status = self.view_ctx.get_process_status(namespec)
            if not status or status.application_name != self.application_name:
                self.logger.warn('unselect Process Statistics for {}'
                                 .format(namespec))
                # form parameter is not consistent. remove it
                self.view_ctx.parameters[PROCESS] = ''
            else:
                # additional information for title
                elt = root.findmeld('address_fig_mid')
                elt.content(next(iter(status.addresses), ''))
        # write selected Process Statistics
        self.write_process_statistics(root)

    def get_process_data(self):
        """ Collect sorted data on processes. """
        data = [{'application_name': process.application_name,
                 'process_name': process.process_name,
                 'namespec': process.namespec(),
                 'running_list': list(process.addresses),
                 'statename': process.state_string(),
                 'statecode': process.state,
                 'loading': process.rules.expected_loading}
                for process in self.application.processes.values()]
        # re-arrange data
        return self.sort_processes_by_config(data)

    def write_process_name(self, tr_elt, info):
        """ Rendering of the cell corresponding to the process name. """
        elt = tr_elt.findmeld('name_a_mid')
        # tail action is NOT allowed if process is stopped
        process_name = info['process_name']
        address = next(iter(info['running_list']), None)
        if address:
            namespec = info['namespec']
            url = self.view_ctx.format_url(address, TAIL_PAGE,
                                           **{PROCESS: namespec})
            elt.attributes(href=url)
            elt.content(process_name)
        else:
            elt.replace(process_name)

    def write_process_addresses(self, tr_elt, info):
        """ Rendering of the cell corresponding to the running addresses of
        the process. """
        running_list = info['running_list']
        if running_list:
            running_li_mid = tr_elt.findmeld('running_li_mid')
            for li_elt, address in running_li_mid.repeat(running_list):
                elt = li_elt.findmeld('running_a_mid')
                url = self.view_ctx.format_url(address, PROC_ADDRESS_PAGE)
                elt.attributes(href=url)
                elt.content(address)
        else:
            elt = tr_elt.findmeld('running_ul_mid')
            elt.replace('')

    def write_process_table(self, root):
        """ Rendering of the application processes managed through
        Supervisor. """
        data = self.get_process_data()
        if data:
            # loop on all processes
            iterator = root.findmeld('tr_mid').repeat(data)
            shaded_tr = False  # used to invert background style
            for tr_elt, item in iterator:
                # get first item in running list
                running_list = item['running_list']
                address = next(iter(running_list), None)
                # write common status(shared between this application view
                # and address view)
                selected_tr = self.write_common_process_status(tr_elt, item)
                # print process name and running addresses
                self.write_process_name(tr_elt, item)
                self.write_process_addresses(tr_elt, item)
                # set line background and invert
                if selected_tr:
                    tr_elt.attrib['class'] = 'selected'
                elif shaded_tr:
                    tr_elt.attrib['class'] = 'shaded'
                shaded_tr = not shaded_tr
        else:
            table = root.findmeld('table_mid')
            table.replace('No programs to manage')

    def make_callback(self, namespec, action):
        """ Triggers processing iaw action requested. """
        if action == 'refresh':
            return self.refresh_action()
        if action == 'config':
            return self.set_starting_strategy(StartingStrategies.CONFIG)
        if action == 'most':
            return self.set_starting_strategy(StartingStrategies.MOST_LOADED)
        if action == 'less':
            return self.set_starting_strategy(StartingStrategies.LESS_LOADED)
        # get current strategy
        strategy = self.supvisors.starter.strategy
        if action == 'startapp':
            return self.start_application_action(strategy)
        if action == 'stopapp':
            return self.stop_application_action()
        if action == 'restartapp':
            return self.restart_application_action(strategy)
        if namespec:
            if self.view_ctx.get_process_status(namespec) is None:
                return delayed_error('No such process named %s' % namespec)
            if action == 'start':
                return self.start_process_action(strategy, namespec)
            if action == 'stop':
                return self.stop_process_action(namespec)
            if action == 'restart':
                return self.restart_process_action(strategy, namespec)

    def refresh_action(self):
        """ Refresh web page. """
        return delayed_info('Page refreshed')

    def set_starting_strategy(self, strategy):
        """ Update starting strategy. """
        self.supvisors.starter.strategy = strategy
        return delayed_info('Starting strategy set to {}'
                            .format(StartingStrategies._to_string(strategy)))

    # Common processing for starting and stopping actions
    def start_action(self, strategy, rpc_name, arg_name, arg_type):
        """ Start/Restart an application or a process iaw the strategy. """
        try:
            rpc_intf = self.info_source.supvisors_rpc_interface
            cb = getattr(rpc_intf, rpc_name)(strategy, arg_name)
        except RPCError as e:
            return delayed_error('{}: {}'.format(rpc_name, e.text))
        if callable(cb):
            def onwait():
                try:
                    result = cb()
                except RPCError as e:
                    return error_message('{}: {}'.format(rpc_name, e.text))
                if result is NOT_DONE_YET:
                    return NOT_DONE_YET
                if result:
                    return info_message('{} {} started'
                                        .format(arg_type, arg_name))
                return warn_message('{} {} NOT started'
                                    .format(arg_type, arg_name))

            onwait.delay = 0.1
            return onwait
        if cb:
            return delayed_info('{} {} started'.format(arg_type, arg_name))
        return delayed_warn('{} {} NOT started'.format(arg_type, arg_name))

    def stop_action(self, rpc_name, arg_name, arg_type):
        """ Stop an application or a process. """
        try:
            rpc_intf = self.info_source.supvisors_rpc_interface
            cb = getattr(rpc_intf, rpc_name)(arg_name)
        except RPCError as e:
            return delayed_error('{}: {}'.format(rpc_name, e.text))
        if callable(cb):
            def onwait():
                try:
                    result = cb()
                except RPCError as e:
                    return error_message('{}: {}'.format(rpc_name, e.text))
                if result is NOT_DONE_YET:
                    return NOT_DONE_YET
                return info_message('{} {} stopped'
                                    .format(arg_type, arg_name))

            onwait.delay = 0.1
            return onwait
        if cb:
            return delayed_info('{} {} stopped'.format(arg_type, arg_name))
        return delayed_warn('{} {} NOT stopped'.format(arg_type, arg_name))

    # Application actions
    def start_application_action(self, strategy):
        """ Start the application iaw the strategy. """
        return self.start_action(strategy, 'start_application',
                                 self.application_name, 'Application')

    def restart_application_action(self, strategy):
        """ Restart the application iaw the strategy. """
        return self.start_action(strategy, 'restart_application',
                                 self.application_name, 'Application')

    def stop_application_action(self):
        """ Stop the application. """
        return self.stop_action('stop_application',
                                self.application_name, 'Application')

    # Process actions
    def start_process_action(self, strategy, namespec):
        """ Start the process named namespec iaw the strategy. """

        return self.start_action(strategy, 'start_process',
                                 namespec, 'Process')

    def restart_process_action(self, strategy, namespec):
        """ Restart the process named namespec iaw the strategy. """
        return self.start_action(strategy, 'restart_process',
                                 namespec, 'Process')

    def stop_process_action(self, namespec):
        """ Stop the process named namespec. """
        return self.stop_action('stop_process', namespec, 'Process')

    def get_process_stats(self, namespec):
        """ Get process statistics of running process. """
        return self.view_ctx.get_process_stats(namespec, True)
