import sys
import logging
import subprocess
import json

from .background_popen import BackgroundPopen
from .table_row_popen import TableRowPopen


_logger = logging.getLogger(__name__)


class KubeCtl(object):
    def __init__(self, context=None):
        self._kubectl = subprocess.check_output('which kubectl', shell=True).strip()
        self._context = context
        self._processes = []
        self._threads = []
        self.final_rc = 0

    @property
    def context(self):
        if not self._context:
            self._context = subprocess.check_output(
                self._commandline('config', 'current-context')).strip()
        return self._context

    def call(self, cmd, *args):
        self.call_async(cmd, *args)
        return self.wait()

    def call_capture(self, cmd, *args):
        cl = self._commandline(cmd, *args)
        return subprocess.check_output(cl)

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
