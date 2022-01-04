#!/usr/bin/python
# -*- coding: utf-8 -*-

# ======================================================================
# Copyright 2020 Julien LE CLEACH
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

import pytest

from random import shuffle
from supervisor.web import MeldView, StatusView
from unittest.mock import call, Mock

from supvisors.ttypes import ApplicationStates
from supvisors.viewhandler import ViewHandler
from supvisors.viewprocinstance import *
from supvisors.viewsupstatus import SupvisorsInstanceView
from supvisors.webutils import PROC_INSTANCE_PAGE

from .base import DummyHttpContext, ProcessInfoDatabase, process_info_by_name
from .conftest import create_application, create_process


@pytest.fixture
def http_context(supvisors):
    """ Fixture for a consistent mocked HTTP context provided by Supervisor. """
    http_context = DummyHttpContext('ui/proc_instance.html')
    http_context.supervisord.supvisors = supvisors
    supvisors.supervisor_data.supervisord = http_context.supervisord
    return http_context


@pytest.fixture
def view(http_context):
    """ Return the instance to test. """
    # apply the forced inheritance done in supvisors.plugin
    StatusView.__bases__ = (ViewHandler,)
    # create the instance to be tested
    return ProcInstanceView(http_context)


def test_init(view):
    """ Test the values set at construction of ProcInstanceView. """
    # test instance inheritance
    for klass in [SupvisorsInstanceView, StatusView, ViewHandler, MeldView]:
        assert isinstance(view, klass)
    # test default page name
    assert view.page_name == PROC_INSTANCE_PAGE


def test_write_contents(mocker, view):
    """ Test the ProcInstanceView.write_contents method. """
    mocked_stats = mocker.patch.object(view, 'write_process_statistics')
    mocked_table = mocker.patch.object(view, 'write_process_table')
    mocked_total = mocker.patch.object(view, 'write_total_status')
    mocked_data = mocker.patch.object(view, 'get_process_data',
                                      side_effect=(([{'namespec': 'dummy'}], []),
                                                   ([{'namespec': 'dummy'}], [{'namespec': 'dummy_proc'}]),
                                                   ([{'namespec': 'dummy'}], [{'namespec': 'dummy_proc'}]),
                                                   ([{'namespec': 'dummy_proc'}], [{'namespec': 'dummy'}])))
    # patch context
    view.view_ctx = Mock(parameters={PROCESS: None}, local_identifier='10.0.0.1',
                         **{'get_process_status.return_value': None})
    # patch the meld elements
    mocked_root = Mock()
    # test call with no process selected
    view.write_contents(mocked_root)
    assert mocked_data.call_args_list == [call()]
    assert mocked_table.call_args_list == [call(mocked_root, [{'namespec': 'dummy'}])]
    assert mocked_total.call_args_list == [call(mocked_root, [{'namespec': 'dummy'}], [])]
    assert mocked_stats.call_args_list == [call(mocked_root, {})]
    mocker.resetall()
    # test call with process selected and no corresponding status
    # process set in excluded_list but not passed to write_process_statistics because unselected due to missing status
    view.view_ctx.parameters[PROCESS] = 'dummy_proc'
    view.write_contents(mocked_root)
    assert mocked_data.call_args_list == [call()]
    assert mocked_table.call_args_list == [call(mocked_root, [{'namespec': 'dummy'}])]
    assert mocked_total.call_args_list == [call(mocked_root, [{'namespec': 'dummy'}], [{'namespec': 'dummy_proc'}])]
    assert view.view_ctx.parameters[PROCESS] == ''
    assert mocked_stats.call_args_list == [call(mocked_root, {})]
    mocker.resetall()
    # test call with process selected but not running on considered node
    # process set in excluded_list
    view.view_ctx.parameters[PROCESS] = 'dummy_proc'
    view.view_ctx.get_process_status.return_value = Mock(running_identifiers={'10.0.0.2'})
    view.write_contents(mocked_root)
    assert mocked_data.call_args_list == [call()]
    assert mocked_table.call_args_list == [call(mocked_root, [{'namespec': 'dummy'}])]
    assert mocked_total.call_args_list == [call(mocked_root, [{'namespec': 'dummy'}], [{'namespec': 'dummy_proc'}])]
    assert view.view_ctx.parameters[PROCESS] == ''
    assert mocked_stats.call_args_list == [call(mocked_root, {})]
    mocker.resetall()
    # test call with process selected and running
    view.view_ctx.parameters[PROCESS] = 'dummy'
    view.view_ctx.get_process_status.return_value = Mock(running_identifiers={'10.0.0.1'})
    view.write_contents(mocked_root)
    assert mocked_data.call_args_list == [call()]
    assert mocked_table.call_args_list == [call(mocked_root, [{'namespec': 'dummy_proc'}])]
    assert mocked_total.call_args_list == [call(mocked_root, [{'namespec': 'dummy_proc'}], [{'namespec': 'dummy'}])]
    assert view.view_ctx.parameters[PROCESS] == 'dummy'
    assert mocked_stats.call_args_list == [call(mocked_root, {'namespec': 'dummy'})]


def test_get_process_data(mocker, view):
    """ Test the ProcInstanceView.get_process_data method. """
    mocker.patch.object(view, 'sort_data', side_effect=lambda x: (sorted(x, key=lambda info: info['namespec']), []))
    # test with empty context
    view.view_ctx = Mock(local_identifier='10.0.0.1',
                         **{'get_process_stats.side_effect': [(2, 'stats #1'), (1, None), (4, 'stats #3')]})
    assert view.get_process_data() == ([], [])
    # patch context
    instance_status = view.sup_ctx.instances['10.0.0.1']
    for application_name in ['sample_test_1', 'crash', 'firefox']:
        view.sup_ctx.applications[application_name] = create_application(application_name, view.supvisors)
    for process_name, load in [('xfontsel', 8), ('segv', 17), ('firefox', 26)]:
        # create process
        info = process_info_by_name(process_name)
        process = create_process(info, view.supvisors)
        process.rules.expected_load = load
        process.add_info('10.0.0.1', info)
        # add to application
        view.sup_ctx.applications[process.application_name].processes[process.namespec] = process
        # add to supvisors instance status
        instance_status.processes[process.namespec] = process
    # test normal behavior
    sorted_data, excluded_data = view.get_process_data()
    # test intermediate list
    data1 = {'application_name': 'sample_test_1', 'process_name': 'xfontsel', 'namespec': 'sample_test_1:xfontsel',
             'single': False, 'identifier': '10.0.0.1',
             'statename': 'RUNNING', 'statecode': 20, 'gravity': 'RUNNING',
             'description': 'pid 80879, uptime 0:01:19',
             'expected_load': 8, 'nb_cores': 2, 'proc_stats': 'stats #1'}
    data2 = {'application_name': 'crash', 'process_name': 'segv', 'namespec': 'crash:segv',
             'single': False, 'identifier': '10.0.0.1',
             'statename': 'BACKOFF', 'statecode': 30, 'gravity': 'BACKOFF',
             'description': 'Exited too quickly (process log may have details)',
             'expected_load': 17, 'nb_cores': 1, 'proc_stats': None}
    data3 = {'application_name': 'firefox', 'process_name': 'firefox', 'namespec': 'firefox',
             'single': True, 'identifier': '10.0.0.1',
             'statename': 'EXITED', 'statecode': 100, 'gravity': 'EXITED',
             'description': 'Sep 14 05:18 PM',
             'expected_load': 26, 'nb_cores': 4, 'proc_stats': 'stats #3'}
    assert sorted_data == [data2, data3, data1]
    assert excluded_data == []


def test_sort_data(mocker, view):
    """ Test the ProcInstanceView.sort_data method. """
    mocker.patch.object(view, 'get_application_summary',
                        side_effect=[{'application_name': 'crash', 'process_name': None},
                                     {'application_name': 'sample_test_1', 'process_name': None},
                                     {'application_name': 'sample_test_2', 'process_name': None}] * 2)
    view.view_ctx = Mock(local_identifier='10.0.0.1', **{'get_process_stats.return_value': (2, 'stats #1')})
    # test empty parameter. supervisord always added
    supervisord_info = {'application_name': 'supervisord', 'process_name': 'supervisord', 'namespec': 'supervisord',
                        'single': True, 'description': 'Supervisor 10.0.0.1', 'identifier': '10.0.0.1',
                        'statecode': 20, 'statename': 'RUNNING', 'gravity': 'RUNNING', 'expected_load': 0,
                        'nb_cores': 2, 'proc_stats': 'stats #1'}
    assert view.sort_data([]) == ([supervisord_info], [])
    # build process list
    processes = [{'application_name': info['group'], 'process_name': info['name'],
                  'single': info['group'] == info['name']}
                 for info in ProcessInfoDatabase]
    shuffle(processes)
    # patch context
    view.view_ctx.get_application_shex.side_effect = [(True, 0), (True, 0), (True, 0),
                                                      (True, 0), (False, 0), (False, 0)]
    # test ordering
    actual, excluded = view.sort_data(processes)
    assert actual == [{'application_name': 'crash', 'process_name': None},
                      {'application_name': 'crash', 'process_name': 'late_segv', 'single': False},
                      {'application_name': 'crash', 'process_name': 'segv', 'single': False},
                      {'application_name': 'firefox', 'process_name': 'firefox', 'single': True},
                      {'application_name': 'sample_test_1', 'process_name': None},
                      {'application_name': 'sample_test_1', 'process_name': 'xclock', 'single': False},
                      {'application_name': 'sample_test_1', 'process_name': 'xfontsel', 'single': False},
                      {'application_name': 'sample_test_1', 'process_name': 'xlogo', 'single': False},
                      {'application_name': 'sample_test_2', 'process_name': None},
                      {'application_name': 'sample_test_2', 'process_name': 'sleep', 'single': False},
                      {'application_name': 'sample_test_2', 'process_name': 'yeux_00', 'single': False},
                      {'application_name': 'sample_test_2', 'process_name': 'yeux_01', 'single': False},
                      supervisord_info]
    assert excluded == []
    # test with some shex on applications
    actual, excluded = view.sort_data(processes)
    assert actual == [{'application_name': 'crash', 'process_name': None},
                      {'application_name': 'crash', 'process_name': 'late_segv', 'single': False},
                      {'application_name': 'crash', 'process_name': 'segv', 'single': False},
                      {'application_name': 'firefox', 'process_name': 'firefox', 'single': True},
                      {'application_name': 'sample_test_1', 'process_name': None},
                      {'application_name': 'sample_test_2', 'process_name': None},
                      supervisord_info]
    sorted_excluded = sorted(excluded, key=lambda x: x['process_name'])
    assert sorted_excluded == [{'application_name': 'sample_test_2', 'process_name': 'sleep', 'single': False},
                               {'application_name': 'sample_test_1', 'process_name': 'xclock', 'single': False},
                               {'application_name': 'sample_test_1', 'process_name': 'xfontsel', 'single': False},
                               {'application_name': 'sample_test_1', 'process_name': 'xlogo', 'single': False},
                               {'application_name': 'sample_test_2', 'process_name': 'yeux_00', 'single': False},
                               {'application_name': 'sample_test_2', 'process_name': 'yeux_01', 'single': False}]


def test_get_application_summary(view):
    """ Test the ProcInstanceView.get_application_summary method. """
    # patch the context
    view.view_ctx = Mock(local_identifier='10.0.0.1')
    view.sup_ctx.applications['dummy_appli'] = Mock(state=ApplicationStates.RUNNING,
                                                    **{'get_operational_status.return_value': 'good'})
    # prepare parameters
    proc_1 = {'statecode': ProcessStates.RUNNING, 'expected_load': 5, 'nb_cores': 8, 'proc_stats': [[10], [5]]}
    proc_2 = {'statecode': ProcessStates.STARTING, 'expected_load': 15, 'nb_cores': 8, 'proc_stats': [[], []]}
    proc_3 = {'statecode': ProcessStates.BACKOFF, 'expected_load': 7, 'nb_cores': 8, 'proc_stats': [[8], [22]]}
    proc_4 = {'statecode': ProcessStates.FATAL, 'expected_load': 25, 'nb_cores': 8, 'proc_stats': None}
    # test with empty list of processes
    expected = {'application_name': 'dummy_appli', 'process_name': None, 'namespec': None,
                'identifier': '10.0.0.1', 'statename': 'RUNNING', 'statecode': 2,
                'description': 'good', 'nb_processes': 0,
                'expected_load': 0, 'nb_cores': 0, 'proc_stats': None}
    assert view.get_application_summary('dummy_appli', []) == expected
    # test with non-running processes
    expected.update({'nb_processes': 1})
    assert view.get_application_summary('dummy_appli', [proc_4]) == expected
    # test with a mix of running and non-running processes
    expected.update({'nb_processes': 4, 'expected_load': 27, 'nb_cores': 8, 'proc_stats': [[18], [27]]})
    assert view.get_application_summary('dummy_appli', [proc_1, proc_2, proc_3, proc_4]) == expected


def test_write_process_table(mocker, view):
    """ Test the ProcInstanceView.write_process_table method. """
    mocked_appli = mocker.patch.object(view, 'write_application_status')
    mocked_common = mocker.patch.object(view, 'write_common_process_status')
    mocked_supervisord = mocker.patch.object(view, 'write_supervisord_status')
    # patch the meld elements
    table_mid = Mock()
    tr_elt_0 = Mock(attrib={'class': ''}, **{'findmeld.return_value': Mock()})
    tr_elt_1 = Mock(attrib={'class': ''}, **{'findmeld.return_value': Mock()})
    tr_elt_2 = Mock(attrib={'class': ''}, **{'findmeld.return_value': Mock()})
    tr_elt_3 = Mock(attrib={'class': ''}, **{'findmeld.return_value': Mock()})
    tr_elt_4 = Mock(attrib={'class': ''}, **{'findmeld.return_value': Mock()})
    tr_elt_5 = Mock(attrib={'class': ''}, **{'findmeld.return_value': Mock()})
    tr_mid = Mock(**{'repeat.return_value': [(tr_elt_0, {'process_name': 'info_0', 'single': True}),
                                             (tr_elt_1, {'process_name': None}),
                                             (tr_elt_2, {'process_name': 'info_2', 'single': False}),
                                             (tr_elt_3, {'process_name': 'info_3', 'single': False}),
                                             (tr_elt_4, {'process_name': None}),
                                             (tr_elt_5, {'process_name': 'supervisord', 'single': True})]})
    mocked_root = Mock(**{'findmeld.side_effect': [table_mid, tr_mid]})
    # test call with no data
    view.write_process_table(mocked_root, {})
    assert table_mid.replace.call_args_list == [call('No programs to manage')]
    assert not mocked_common.called
    assert not mocked_appli.called
    assert not tr_elt_0.findmeld.return_value.replace.called
    assert not tr_elt_1.findmeld.return_value.replace.called
    assert not tr_elt_2.findmeld.return_value.replace.called
    assert not tr_elt_3.findmeld.return_value.replace.called
    assert not tr_elt_4.findmeld.return_value.replace.called
    assert not tr_elt_5.findmeld.return_value.replace.called
    assert tr_elt_0.attrib['class'] == ''
    assert tr_elt_1.attrib['class'] == ''
    assert tr_elt_2.attrib['class'] == ''
    assert tr_elt_3.attrib['class'] == ''
    assert tr_elt_4.attrib['class'] == ''
    assert tr_elt_5.attrib['class'] == ''
    table_mid.replace.reset_mock()
    # test call with data and line selected
    view.write_process_table(mocked_root, [{}])
    assert not table_mid.replace.called
    assert mocked_common.call_args_list == [call(tr_elt_0, {'process_name': 'info_0', 'single': True}),
                                            call(tr_elt_2, {'process_name': 'info_2', 'single': False}),
                                            call(tr_elt_3, {'process_name': 'info_3', 'single': False})]
    assert mocked_supervisord.call_args_list == [call(tr_elt_5, {'process_name': 'supervisord', 'single': True})]
    assert mocked_appli.call_args_list == [call(tr_elt_1, {'process_name': None}, True),
                                           call(tr_elt_4, {'process_name': None}, False)]
    assert not tr_elt_0.findmeld.return_value.replace.called
    assert not tr_elt_1.findmeld.return_value.replace.called
    assert tr_elt_2.findmeld.return_value.replace.call_args_list == [call('')]
    assert tr_elt_3.findmeld.return_value.replace.call_args_list == [call('')]
    assert not tr_elt_4.findmeld.return_value.replace.called
    assert not tr_elt_5.findmeld.return_value.replace.called
    assert tr_elt_0.attrib['class'] == 'brightened'
    assert tr_elt_1.attrib['class'] == 'shaded'
    assert tr_elt_2.attrib['class'] == 'brightened'
    assert tr_elt_3.attrib['class'] == 'shaded'
    assert tr_elt_4.attrib['class'] == 'brightened'
    assert tr_elt_5.attrib['class'] == 'shaded'


def test_write_application_status(mocker, view):
    """ Test the ProcInstanceView.write_application_status method. """
    mocked_common = mocker.patch.object(view, 'write_common_status')
    # patch the context
    view.view_ctx = Mock(**{'get_application_shex.side_effect': [(False, '010'), (True, '101')],
                            'format_url.return_value': 'an url'})
    # patch the meld elements
    shex_a_mid = Mock(attrib={})
    shex_td_mid = Mock(attrib={}, **{'findmeld.return_value': shex_a_mid})
    name_a_mid = Mock(attrib={})
    start_td_mid = Mock(attrib={})
    stop_td_mid = Mock(attrib={})
    restart_td_mid = Mock(attrib={})
    clear_td_mid = Mock(attrib={})
    tailout_td_mid = Mock(attrib={})
    tailerr_td_mid = Mock(attrib={})
    mid_list = [shex_td_mid, name_a_mid, start_td_mid, clear_td_mid,
                stop_td_mid, restart_td_mid, tailout_td_mid, tailerr_td_mid]
    mocked_root = Mock(**{'findmeld.side_effect': mid_list * 2})
    # prepare parameters
    info = {'application_name': 'dummy_appli', 'nb_processes': 4}
    # test call with application processes hidden
    view.write_application_status(mocked_root, info, True)
    assert mocked_common.call_args_list == [call(mocked_root, info)]
    assert 'rowspan' not in shex_td_mid.attrib
    assert 'class' not in shex_td_mid.attrib
    assert shex_a_mid.content.call_args_list == [call('[+]')]
    assert shex_a_mid.attributes.call_args_list == [call(href='an url')]
    assert view.view_ctx.format_url.call_args_list == [call('', 'proc_instance.html', shex='010'),
                                                       call('', 'application.html', appliname='dummy_appli')]
    assert name_a_mid.content.call_args_list == [call('dummy_appli')]
    assert name_a_mid.attributes.call_args_list == [call(href='an url')]
    for mid in [start_td_mid, clear_td_mid]:
        assert mid.attrib['colspan'] == '3'
        assert mid.content.call_args_list == [call('')]
    for mid in [stop_td_mid, restart_td_mid, tailout_td_mid, tailerr_td_mid]:
        assert mid.replace.call_args_list == [call('')]
    # reset context
    mocked_common.reset_mock()
    shex_a_mid.content.reset_mock()
    shex_a_mid.attributes.reset_mock()
    for mid in mid_list:
        mid.content.reset_mock()
        mid.attributes.reset_mock()
        mid.replace.reset_mock()
        mid.attrib = {}
    view.view_ctx.format_url.reset_mock()
    # test call with application processes displayed
    view.write_application_status(mocked_root, info, False)
    assert mocked_common.call_args_list == [call(mocked_root, info)]
    assert shex_td_mid.attrib['rowspan'] == '5'
    assert shex_td_mid.attrib['class'] == 'brightened'
    assert shex_a_mid.content.call_args_list == [call('[\u2013]')]
    assert shex_a_mid.attributes.call_args_list == [call(href='an url')]
    assert view.view_ctx.format_url.call_args_list == [call('', 'proc_instance.html', shex='101'),
                                                       call('', 'application.html', appliname='dummy_appli')]
    assert name_a_mid.content.call_args_list == [call('dummy_appli')]
    assert name_a_mid.attributes.call_args_list == [call(href='an url')]
    for mid in [start_td_mid, clear_td_mid]:
        assert mid.attrib['colspan'] == '3'
        assert mid.content.call_args_list == [call('')]
    for mid in [stop_td_mid, restart_td_mid, tailout_td_mid, tailerr_td_mid]:
        assert mid.replace.call_args_list == [call('')]


def test_write_supervisord_status(mocker, view):
    """ Test the write_supervisord_status method. """
    mocked_button = mocker.patch.object(view, 'write_supervisord_button')
    mocked_common = mocker.patch.object(view, 'write_common_status')
    # patch the view context
    view.view_ctx = Mock(**{'format_url.return_value': 'an url'})
    # patch the meld elements
    shex_elt = Mock(attrib={'class': ''})
    name_elt = Mock(attrib={'class': ''})
    start_elt = Mock(attrib={'class': ''})
    tailerr_elt = Mock(attrib={'class': ''})
    mid_map = {'shex_td_mid': shex_elt, 'name_a_mid': name_elt, 'start_a_mid': start_elt, 'tailerr_a_mid': tailerr_elt}
    tr_elt = Mock(attrib={}, **{'findmeld.side_effect': lambda x: mid_map[x]})
    # test call while not Master
    view.sup_ctx._is_master = False
    info = {'namespec': 'supervisord', 'process_name': 'supervisord'}
    view.write_supervisord_status(tr_elt, info)
    assert mocked_common.call_args_list == [call(tr_elt, info)]
    assert tr_elt.findmeld.call_args_list == [call('name_a_mid'), call('start_a_mid'), call('tailerr_a_mid')]
    assert shex_elt.attrib == {'class': ''}
    assert name_elt.content.call_args_list == [call('supervisord')]
    assert view.view_ctx.format_url.call_args_list == [call('', 'maintail.html', processname='supervisord')]
    assert name_elt.attributes.call_args_list == [call(href='an url', target="_blank")]
    assert mocked_button.call_args_list == [call(tr_elt, 'stop_a_mid', 'proc_instance.html', action='shutdownsup'),
                                            call(tr_elt, 'restart_a_mid', 'proc_instance.html', action='restartsup'),
                                            call(tr_elt, 'clear_a_mid', 'proc_instance.html', action='mainclearlog'),
                                            call(tr_elt, 'tailout_a_mid', MAIN_STDOUT_PAGE)]
    assert start_elt.content.call_args_list == [call('')]
    assert tailerr_elt.content.call_args_list == [call('')]
    mocker.resetall()
    tr_elt.reset_mock()
    for elt in mid_map.values():
        elt.reset_mock()
    view.view_ctx.format_url.reset_mock()
    # test call while Master
    view.sup_ctx._is_master = True
    info = {'namespec': 'supervisord', 'process_name': 'supervisord'}
    view.write_supervisord_status(tr_elt, info)
    assert mocked_common.call_args_list == [call(tr_elt, info)]
    assert tr_elt.findmeld.call_args_list == [call('shex_td_mid'), call('name_a_mid'), call('start_a_mid'),
                                              call('tailerr_a_mid')]
    assert shex_elt.attrib == {'class': 'master'}
    assert name_elt.content.call_args_list == [call('supervisord')]
    assert view.view_ctx.format_url.call_args_list == [call('', 'maintail.html', processname='supervisord')]
    assert name_elt.attributes.call_args_list == [call(href='an url', target="_blank")]
    assert mocked_button.call_args_list == [call(tr_elt, 'stop_a_mid', 'proc_instance.html', action='shutdownsup'),
                                            call(tr_elt, 'restart_a_mid', 'proc_instance.html', action='restartsup'),
                                            call(tr_elt, 'clear_a_mid', 'proc_instance.html', action='mainclearlog'),
                                            call(tr_elt, 'tailout_a_mid', MAIN_STDOUT_PAGE)]
    assert start_elt.content.call_args_list == [call('')]
    assert tailerr_elt.content.call_args_list == [call('')]


def test_write_supervisord_button(view):
    """ Test the ProcInstanceView.write_supervisord_button method. """
    # patch the view context
    view.view_ctx = Mock(**{'format_url.return_value': 'an url'})
    # patch the meld elements
    a_elt = Mock(attrib={'class': ''})
    tr_elt = Mock(attrib={}, **{'findmeld.return_value': a_elt})
    # test call with action parameters
    view.write_supervisord_button(tr_elt, 'any_a_mid', 'proc_instance.html', **{ACTION: 'any_action'})
    assert tr_elt.findmeld.call_args_list == [call('any_a_mid')]
    assert view.view_ctx.format_url.call_args_list == [call('', 'proc_instance.html', action='any_action')]
    assert a_elt.attrib == {'class': 'button on'}
    assert a_elt.attributes.call_args_list == [call(href='an url')]
    tr_elt.findmeld.reset_mock()
    view.view_ctx.format_url.reset_mock()
    a_elt.attributes.reset_mock()
    a_elt.attrib['class'] = 'active'
    # test call without action parameters
    view.write_supervisord_button(tr_elt, 'any_a_mid', 'proc_instance.html')
    assert tr_elt.findmeld.call_args_list == [call('any_a_mid')]
    assert view.view_ctx.format_url.call_args_list == [call('', 'proc_instance.html')]
    assert a_elt.attrib == {'class': 'active button on'}
    assert a_elt.attributes.call_args_list == [call(href='an url')]


def test_write_total_status(mocker, view):
    """ Test the ProcInstanceView.write_total_status method. """
    mocked_sum = mocker.patch.object(view, 'sum_process_info', return_value=(50, 2, None))
    # patch the meld elements
    load_elt = Mock(attrib={'class': ''})
    mem_elt = Mock(attrib={'class': ''})
    cpu_elt = Mock(attrib={'class': ''})
    mid_map = {'load_total_th_mid': load_elt, 'mem_total_th_mid': mem_elt, 'cpu_total_th_mid': cpu_elt}
    tr_elt = Mock(attrib={}, **{'findmeld.side_effect': lambda x: mid_map[x]})
    root_elt = Mock(attrib={}, **{'findmeld.return_value': None})
    # test call with total element removed
    sorted_data = [1, 2]
    excluded_data = [3, 4]
    view.write_total_status(root_elt, sorted_data, excluded_data)
    assert root_elt.findmeld.call_args_list == [call('total_mid')]
    assert not tr_elt.findmeld.called
    assert not mocked_sum.called
    for elt in mid_map.values():
        assert not elt.content.called
    root_elt.findmeld.reset_mock()
    # test call with total element present
    root_elt.findmeld.return_value = tr_elt
    # test call with no process stats
    view.write_total_status(root_elt, sorted_data, excluded_data)
    assert mocked_sum.call_args_list == [call([1, 2, 3, 4])]
    assert root_elt.findmeld.call_args_list == [call('total_mid')]
    assert tr_elt.findmeld.call_args_list == [call('load_total_th_mid')]
    assert load_elt.content.call_args_list == [call('50%')]
    assert not mem_elt.content.called
    assert not cpu_elt.content.called
    mocked_sum.reset_mock()
    root_elt.findmeld.reset_mock()
    tr_elt.findmeld.reset_mock()
    load_elt.content.reset_mock()
    # test call with process stats and irix mode
    mocked_sum.return_value = (50, 2, [[12], [25]])
    view.supvisors.options.stats_irix_mode = True
    view.write_total_status(root_elt, sorted_data, excluded_data)
    assert mocked_sum.call_args_list == [call([1, 2, 3, 4])]
    assert root_elt.findmeld.call_args_list == [call('total_mid')]
    assert tr_elt.findmeld.call_args_list == [call('load_total_th_mid'), call('mem_total_th_mid'),
                                              call('cpu_total_th_mid')]
    assert load_elt.content.call_args_list == [call('50%')]
    assert mem_elt.content.call_args_list == [call('25.00%')]
    assert cpu_elt.content.call_args_list == [call('12.00%')]
    mocked_sum.reset_mock()
    root_elt.findmeld.reset_mock()
    tr_elt.findmeld.reset_mock()
    load_elt.content.reset_mock()
    mem_elt.content.reset_mock()
    cpu_elt.content.reset_mock()
    # test call with process stats and solaris mode
    view.supvisors.options.stats_irix_mode = False
    view.write_total_status(root_elt, sorted_data, excluded_data)
    assert mocked_sum.call_args_list == [call([1, 2, 3, 4])]
    assert root_elt.findmeld.call_args_list == [call('total_mid')]
    assert tr_elt.findmeld.call_args_list == [call('load_total_th_mid'), call('mem_total_th_mid'),
                                              call('cpu_total_th_mid')]
    assert load_elt.content.call_args_list == [call('50%')]
    assert mem_elt.content.call_args_list == [call('25.00%')]
    assert cpu_elt.content.call_args_list == [call('6.00%')]


def test_make_callback(mocker, view):
    """ Test the ProcInstanceView.make_callback method. """
    mocked_parent = mocker.patch('supvisors.viewsupstatus.SupvisorsInstanceView.make_callback', return_value='default')
    mocked_action = mocker.patch.object(view, 'clear_log_action', return_value='clear')
    # test restart
    assert view.make_callback('namespec', 'mainclearlog') == 'clear'
    assert mocked_action.call_args_list == [call()]
    assert not mocked_parent.called
    mocked_action.reset_mock()
    # test restart
    assert view.make_callback('namespec', 'other') == 'default'
    assert mocked_parent.call_args_list == [call('namespec', 'other')]
    assert not mocked_action.called


def test_clear_log_action(mocker, view):
    """ Test the ProcInstanceView.clear_log_action method. """
    mocked_error = mocker.patch('supvisors.viewprocinstance.delayed_error', return_value='delayed error')
    mocked_info = mocker.patch('supvisors.viewprocinstance.delayed_info', return_value='delayed info')
    # test RPC error
    rpc_intf = view.supvisors.supervisor_data.supervisor_rpc_interface
    mocker.patch.object(rpc_intf, 'clearLog', side_effect=RPCError('failed RPC'))
    assert view.clear_log_action() == 'delayed error'
    assert mocked_error.called
    assert not mocked_info.called
    # reset mocks
    mocked_error.reset_mock()
    # test direct result
    rpc_intf.clearLog.side_effect = None
    rpc_intf.clearLog.return_value = True
    assert view.clear_log_action() == 'delayed info'
    assert not mocked_error.called
    assert mocked_info.called
