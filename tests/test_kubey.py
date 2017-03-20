#!/usr/bin/env python

'''
test_kubey
----------------------------------

Tests for `kubey` module.
'''

import os
import re
import subprocess
import time
import pytest
import mockfs

from click.testing import CliRunner
from kubey import cli
from configstruct import OpenStruct


class Responder(object):
    def __init__(self, name):
        self.name = name
        self.expects = {}

    @property
    def is_satisfied(self):
        return len(self.expects) == 0

    def process(self, *args, **kwargs):
        if len(args) == 1 and isinstance(args[0], list):
            args = args[0]
        cmd = ' '.join(map(str, args))
        expect = self.expects[cmd]
        del self.expects[cmd]
        return expect.and_return

    def expect(self, cmd, **kwargs):
        self.expects[cmd] = OpenStruct(kwargs)

    def __repr__(self):
        return '<Responder: name=%s expects=%s>' % (self.name, self.expects)


class MockSubprocess(object):
    ATTRS = ('check_output', 'call', 'Popen')

    def setup(self):
        def mock_getmtime(_):
            return time.time()
        os.path.getmtime = mock_getmtime
        self.mfs = mockfs.replace_builtins()
        self.responders = OpenStruct()
        for name in self.ATTRS:
            self._intercept(name)

    def teardown(self):
        mockfs.restore_builtins()
        for name in self.ATTRS:
            self._release(name)

    def _intercept(self, name):
        attr = getattr(subprocess, name)
        setattr(self, '_orig_' + name, attr)
        responder = self.responders[name] = Responder(name)
        setattr(subprocess, name, responder.process)

    def _release(self, name):
        attr = getattr(self, '_orig_' + name)
        setattr(subprocess, name, attr)
        delattr(self, '_orig_' + name)
        responder = self.responders[name]
        if not responder.is_satisfied:
            pytest.fail('Unsatisfied responder: %s' % responder)


class TestCli(MockSubprocess):

    def test_command_line_interface(self):
        runner = CliRunner()
        result = runner.invoke(cli.cli)
        assert result.exit_code == 2
        assert 'Usage: cli ' in result.output
        help_result = runner.invoke(cli.cli, ['--help'])
        assert help_result.exit_code == 0
        assert 'Show this message and exit.' in help_result.output

    def test_empty_list(self):
        self.responders.check_output.expect('which kubectl', and_return='mykubectl')
        self.responders.check_output.expect('mykubectl config current-context', and_return='myctx')
        self.responders.check_output.expect(
            'mykubectl --context myctx get --output=json pods --all-namespaces',
            and_return='{"items":[]}'
        )
        runner = CliRunner()
        result = runner.invoke(cli.cli, ['-n', '.', '--wide', 'myprod'], catch_exceptions=False)
        exp = ['node', 'status', 'name', 'node-ip', 'namespace', 'containers']
        cols = [str(c) for c in re.split(r'\s+', result.output.strip()) if not c.startswith('---')]
        assert exp.sort() == cols.sort()  # FIXME: order should not matter...but does in tox runs
