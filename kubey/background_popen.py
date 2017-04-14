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
        Thread(target=self._proxy_lines, args=[self.stdout, out_handler]).start()
        Thread(target=self._proxy_lines, args=[self.stderr, err_handler]).start()

    def _proxy_lines(self, io, handler):
        with io:
            while self.poll() is None:
                line = io.readline()
                if line != '':
                    handler(line)
