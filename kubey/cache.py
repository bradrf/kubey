import os
import io
import json
import time

# Python 3 compatibility (no longer includes `unicode`):
try:
    unicode
except NameError:
    unicode = str


class Cache(object):
    def __init__(self, path, seconds, retriever, *retriever_args):
        parent = os.path.dirname(path)
        if not os.path.exists(parent):
            os.makedirs(parent)
        self.path = path
        self.seconds = seconds
        self.retriever = retriever
        self.retriever_args = retriever_args
        self._obj = None
        self._expiry = None

    def obj(self):
        self._consider_update()
        return self._obj

    def _consider_update(self):
        if self._is_stale():
            self._update()
        elif not self._obj:
            with io.open(self.path, 'r', encoding='utf-8') as f:
                self._obj = json.load(f)

    def _is_stale(self):
        if not self._expiry:
            if not os.path.exists(self.path):
                return True
            if os.path.getsize(self.path) < 1:
                return True
            self._set_expiry()
        return self._expiry < time.time()

    def _update(self):
        self._obj = self.retriever(*self.retriever_args)
        with io.open(self.path, 'w', encoding='utf-8') as f:
            f.write(unicode(json.dumps(self._obj, ensure_ascii=False)))
        self._set_expiry()

    def _set_expiry(self):
        self._expiry = os.path.getmtime(self.path) + self.seconds
