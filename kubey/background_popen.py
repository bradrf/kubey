import subprocess

from threading import Thread


class BackgroundPopen(subprocess.Popen):
    @staticmethod
    def prefix_handler(prefix, io):
        return lambda line: io.write(prefix + line)

    def __init__(self, out_handler, err_handler, *args, **kwargs):
        if out_handler:
            kwargs['stdout'] = subprocess.PIPE
        if err_handler:
            kwargs['stderr'] = subprocess.PIPE
        super(BackgroundPopen, self).__init__(*args, **kwargs)
        if out_handler:
            self._stdout_thread = Thread(target=self._proxy_lines, args=[self.stdout, out_handler])
            self._stdout_thread.start()
        else:
            self._stdout_thread = None
        if err_handler:
            self._stderr_thread = Thread(target=self._proxy_lines, args=[self.stderr, err_handler])
            self._stderr_thread.start()
        else:
            self._stderr_thread = None

    def wait(self):
        result = super(BackgroundPopen, self).wait()
        if self._stdout_thread:
            self._stdout_thread.join()
            self._stdout_thread = None
        if self._stderr_thread:
            self._stderr_thread.join()
            self._stderr_thread = None
        return result

    def _proxy_lines(self, io, handler):
        with io:
            while True:
                line = io.readline()
                if not line:
                    break
                handler(line)
