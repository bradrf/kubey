import subprocess

from threading import Thread


class BackgroundPopen(subprocess.Popen):
    @staticmethod
    def prefix_handler(prefix, io):
        return lambda line: io.write(prefix + line)

    @staticmethod
    def _proxy_lines(pipe, handler):
        with pipe:
            for line in pipe:
                handler(line)

    def __init__(self, out_handler, err_handler, *args, **kwargs):
        kwargs['stdout'] = subprocess.PIPE
        kwargs['stderr'] = subprocess.PIPE
        super(self.__class__, self).__init__(*args, **kwargs)
        Thread(target=self._proxy_lines, args=[self.stdout, out_handler]).start()
        Thread(target=self._proxy_lines, args=[self.stderr, err_handler]).start()
