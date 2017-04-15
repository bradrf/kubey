import subprocess

from threading import Thread


class BackgroundPopen(subprocess.Popen):
    @staticmethod
    def prefix_handler(prefix, io):
        return lambda line: io.write(prefix + line)

    def __init__(self, out_handler, err_handler, *args, **kwargs):
        kwargs['stdout'] = subprocess.PIPE
        kwargs['stderr'] = subprocess.PIPE
        super(self.__class__, self).__init__(*args, **kwargs)
        self._stdout_thread = Thread(target=self._proxy_lines, args=[self.stdout, out_handler])
        self._stderr_thread = Thread(target=self._proxy_lines, args=[self.stderr, err_handler])
        self._stdout_thread.start()
        self._stderr_thread.start()

    def wait(self):
        result = super(self.__class__, self).wait()
        self._stdout_thread.join()
        self._stderr_thread.join()
        return result

    def _proxy_lines(self, io, handler):
        with io:
            while True:
                line = io.readline()
                if not line:
                    break
                handler(line)
