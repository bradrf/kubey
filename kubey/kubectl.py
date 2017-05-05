import sys
import logging
import subprocess
import json
from configstruct import OpenStruct

from .background_popen import BackgroundPopen
from .table_row_popen import TableRowPopen


_logger = logging.getLogger(__name__)


class KubeCtl(object):
    def __init__(self, context=None, config=None):
        val = subprocess.check_output('which kubectl', shell=True).strip()
        self._kubectl = val.decode('utf-8')
        self._context = context
        self._config = config
        self._processes = []
        self._threads = []
        self.final_rc = 0

    @property
    def context(self):
        if self._context is None:
            ctx = subprocess.check_output(self._commandline('config', 'current-context')).strip()
            self._context = ctx.decode('utf-8')  # returns a bytestring
        return self._context

    @property
    def config(self):
        if self._config is None:
            self._config = OpenStruct(self.call_json('config', 'view'))
        return self._config

    def call(self, cmd, *args):
        self.call_async(cmd, *args)
        return self.wait()

    def call_capture(self, cmd, *args):
        cl = self._commandline(cmd, *args)
        val = subprocess.check_output(cl)
        return val.decode('utf-8')

    def call_json(self, cmd, *args):
        return json.loads(self.call_capture(cmd, '--output=json', *args))

    def call_async(self, cmd, *args):
        cl = self._commandline(cmd, *args)
        proc = subprocess.Popen(cl)
        self._processes.append((cl, proc))
        return 0

    def call_prefix(self, prefix, cmd, *args):
        out_handler = BackgroundPopen.prefix_handler(prefix, sys.stdout)
        err_handler = BackgroundPopen.prefix_handler('[ERR] ' + prefix, sys.stderr)
        cl = self._commandline(cmd, *args)
        proc = BackgroundPopen(out_handler, err_handler, cl)
        self._processes.append((cl, proc))
        return 0

    def call_table_rows(self, row_handler, cmd, *args):
        cl = self._commandline(cmd, *args)
        proc = TableRowPopen(row_handler, cl)
        self._processes.append((cl, proc))
        return 0

    def wait(self):
        procs = self._processes
        self._process = []
        for cl, proc in procs:
            self._check(cl, proc.wait())
        return self.final_rc

    def kill(self, signal=None):
        procs = self._processes
        self._process = []
        for cl, proc in procs:
            if signal:
                proc.send_signal(signal)
            else:
                proc.kill()
            proc.wait()

    def _commandline(self, command, *args):
        commandline = [self._kubectl]
        if self._context:
            commandline.extend(['--context', self._context])
        commandline.append(command)
        commandline.extend(args)
        _logger.debug(' '.join(map(str, commandline)))
        return commandline

    def _check(self, cl, rc):
        if rc != 0:
            self.final_rc = rc
            _logger.warn('%s => exit status: %d' % (' '.join(cl), rc))
        return rc
