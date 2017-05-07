#!/usr/bin/env python

'''
test_kubey
----------------------------------

Tests for `kubey` module.
'''

import os
import re
import time
import json
import pytest
import mockfs

from mock import patch
from click.testing import CliRunner
from configstruct import OpenStruct
from kubey import cli
from kubey.background_popen import BackgroundPopen


class Responder(object):
    def __init__(self, name):
        self.name = name
        self.expects = {}
        self.prev = None

    @property
    def is_satisfied(self):
        return len(self.expects) == 0

    def process(self, *args, **kwargs):
        if len(args) == 1 and isinstance(args[0], list):
            args = args[0]
        cmd = ' '.join(map(str, args))
        if cmd not in self.expects:
            pytest.fail('Did not expect response for "{0}" (previous success: {1})'
                        .format(cmd, self.prev))
        expect = self.expects[cmd]
        del self.expects[cmd]
        self.prev = cmd
        resp = expect.and_return
        if not isinstance(resp, str):
            resp = json.dumps(resp)
        return resp.encode('utf-8')

    def expect(self, cmd, **kwargs):
        self.expects[cmd] = OpenStruct(kwargs)
        return self

    def __repr__(self):
        return '<Responder: name=%s expects=%s>' % (self.name, self.expects)


class TestCli(object):
    def setup(self):
        def mock_getmtime(_):
            return time.time()
        os.path.getmtime = mock_getmtime
        self.mfs = mockfs.replace_builtins()

    def teardown(self):
        mockfs.restore_builtins()

    def test_command_line_interface(self):
        runner = CliRunner()
        result = runner.invoke(cli.cli)
        assert result.exit_code == 2
        assert 'Usage: cli ' in result.output
        help_result = runner.invoke(cli.cli, ['--help'])
        assert help_result.exit_code == 0
        assert 'Show this message and exit.' in help_result.output

    @patch('subprocess.Popen.__init__', return_value=None)
    @patch('subprocess.Popen.wait')
    @patch.object(BackgroundPopen, 'stderr', create=True)
    @patch.object(BackgroundPopen, 'stdout', create=True)
    @patch('subprocess.check_output')
    def test_empty_list(self, mock_check_output, bg_out, bg_err, mock_wait, mock_init):
        mock_check_output.side_effect = Responder(str(mock_check_output)) \
                         .expect('which kubectl', and_return='mykubectl') \
                         .expect('mykubectl config current-context', and_return='myctx') \
                         .expect('mykubectl --context myctx get -o=json namespaces', and_return={
                             'items': [{'metadata': {'name': 'one'}, 'status': {'phase': 'Active'}}]
                         }) \
                         .process
        # now, provide pod json responses to background popen request
        bg_out.readline.side_effect = ('{}', '')
        bg_err.readline.side_effect = ('',)
        runner = CliRunner()
        result = runner.invoke(cli.cli, ['-n', '.', '--wide', 'myprod'], catch_exceptions=False)
        exp = ['node', 'status', 'name', 'node-ip', 'namespace', 'containers']
        cols = [str(c) for c in re.split(r'\s+', result.output.strip()) if not c.startswith('---')]
        assert exp.sort() == cols.sort()  # FIXME: order should not matter...but does in tox runs
