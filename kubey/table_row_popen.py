import subprocess
import re

from threading import Thread


class TableRowPopen(subprocess.Popen):
    def __init__(self, row_handler, *args, **kwargs):
        self._row_handler = row_handler
        kwargs['stdout'] = subprocess.PIPE
        super(TableRowPopen, self).__init__(*args, **kwargs)
        self._stdout_thread = Thread(target=self._parse_table)
        self._stdout_thread.start()

    def wait(self):
        result = super(TableRowPopen, self).wait()
        self._stdout_thread.join()
        return result

    def _parse_table(self):
        line_number = 0
        with self.stdout as io:
            while True:
                line = io.readline().rstrip().decode('utf-8')
                if not line:
                    break
                line_number += 1
                row = self._title_row_from(line) if line_number == 1 else self._row_from(line)
                self._row_handler(line_number, row)

    def _title_row_from(self, line):
        '''Splits the first line of output expecting the first char in each header to indicate the
        start of items in following rows for the column data (i.e. left-aligned)
        '''
        row = re.split(r'  +|\t', line)  # expects either more than two spaces or tabs as separation
        self._column_offsets = []
        beg = 0
        for col in row:
            offset = line.index(col, beg)
            self._column_offsets.append(offset)
            beg += len(col)
        return row

    def _row_from(self, line):
        row = []
        beg = self._column_offsets[0]
        for end in self._column_offsets[1:]:
            row.append(line[beg:end].strip())
            beg = end
        row.append(line[beg:].strip())
        return row
