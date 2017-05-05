import os
import re
import logging
import time

from . import timestamp
from .kubectl import KubeCtl
from .cache import Cache
from .pod import Pod
from .node import Node
from .event import Event


_logger = logging.getLogger(__name__)


# FIXME: this happened when running the following command and hitting cntrl-c:
# (kubey) > kubey -n collab-staging canary/collab tail -f
# ...logs and stuff for a minute...
# ^CTraceback (most recent call last):
#   File "/Users/brad/.virtualenvs/kubey/bin/kubey", line 11, in <module>
#     load_entry_point('kubey', 'console_scripts', 'kubey')()
#   File "/Users/brad/.virtualenvs/kubey/lib/python2.7/site-packages/click/core.py", line 722, in __call__
#     return self.main(*args, **kwargs)
#   File "/Users/brad/.virtualenvs/kubey/lib/python2.7/site-packages/click/core.py", line 697, in main
#     rv = self.invoke(ctx)
#   File "/Users/brad/.virtualenvs/kubey/lib/python2.7/site-packages/click/core.py", line 1066, in invoke
#     return _process_result(sub_ctx.command.invoke(sub_ctx))
#   File "/Users/brad/.virtualenvs/kubey/lib/python2.7/site-packages/click/core.py", line 895, in invoke
#     return ctx.invoke(self.callback, **ctx.params)
#   File "/Users/brad/.virtualenvs/kubey/lib/python2.7/site-packages/click/core.py", line 535, in invoke
#     return callback(*args, **kwargs)
#   File "/Users/brad/.virtualenvs/kubey/lib/python2.7/site-packages/click/decorators.py", line 27, in new_func
#     return f(get_current_context().obj, *args, **kwargs)
#   File "/Users/brad/work/kubey/kubey/cli.py", line 310, in tail
#     kubectl.wait()
#   File "/Users/brad/work/kubey/kubey/kubectl.py", line 92, in wait
#     self._check(cl, proc.wait())
#   File "/usr/local/Cellar/python/2.7.13/Frameworks/Python.framework/Versions/2.7/lib/python2.7/subprocess.py", line 1073, in wait
#     pid, sts = _eintr_retry_call(os.waitpid, self.pid, 0)
#   File "/usr/local/Cellar/python/2.7.13/Frameworks/Python.framework/Versions/2.7/lib/python2.7/subprocess.py", line 121, in _eintr_retry_call
#     return func(*args)
#   File "/Users/brad/work/kubey/kubey/cli.py", line 141, in handle_interrupt
#     ctx.obj.kubey.kubectl.kill(signal)
#   File "/Users/brad/work/kubey/kubey/kubectl.py", line 100, in kill
#     proc.send_signal(signal)
#   File "/usr/local/Cellar/python/2.7.13/Frameworks/Python.framework/Versions/2.7/lib/python2.7/subprocess.py", line 1243, in send_signal
#     os.kill(self.pid, sig)
# OSError: [Errno 3] No such process



class Kubey(object):
    class UnknownNamespace(ValueError):
        pass

    ANY = '.'

    def __init__(self, config):
        self._config = config
        self.kubectl = KubeCtl(config.context)
        self._split_match()
        self._set_namespace()
        self._pods = None
        self._nodes = None

    def __repr__(self):
        return "<Kubey: context=%s namespace=%s match=%s/%s/%s>" % (
            self.kubectl.context, self._config.namespace,
            self._node_re.pattern, self._pod_re.pattern, self._container_re.pattern)

    def each_pod(self, limit=None):
        if self._pods:
            for pod in self._pods:
                yield pod
            return
        collectors = []
        if self._config.namespace == self.ANY:
            collectors.append(self.kubectl.call_async_json('get', '--all-namespaces', 'pods'))
        else:
            for ns in self._selected_namespaces:
                collectors.append(self.kubectl.call_async_json('get', '-n', ns, 'pods'))
        self.kubectl.wait()
        self._pods = []
        for collector in collectors:
            for info in collector.as_json().get('items', []):
                if not self._pod_matches(info):
                    continue
                pod = Pod(self._config, info, self._container_re.search)
                self._pods.append(pod)
                yield pod
                if self._exceeded_max(len(self._pods), limit):
                    break

    def each_node(self, limit=None, include_top_info=False):
        if self._nodes:
            for node in self._nodes:
                yield node
            return
        pods = list(self.each_pod())
        top_info = self._get_top_node_info() if include_top_info else {}
        self._nodes = []
        for info in self.kubectl.call_json('get', 'nodes').get('items', []):
            if not self._node_matches(info):
                continue
            node = Node(self._config, info, pods, top_info)
            if self._config.namespace != self.ANY and len(node.pods) == 0:
                continue  # no matching pods found
            self._nodes.append(node)
            yield node
            if self._exceeded_max(len(self._nodes), limit):
                break

    def each_event(self, limit=None, watch_seconds=10):
        count = 0
        args = ['events', '--all-namespaces', '--sort-by=lastTimestamp']
        last_ts = youngest_ts = timestamp.epoch
        while True:
            json = self.kubectl.call_json('get', *args)
            for info in json['items']:
                if not self._event_matches(info):
                    continue
                last_ts = timestamp.parse(info['lastTimestamp'])
                if last_ts <= youngest_ts:
                    continue
                event = Event(self._config, info)
                yield event
                count += 1
                if self._exceeded_max(count, limit):
                    break
            # update after processing all items at least once (avoids dropping items w/ same ts)
            youngest_ts = last_ts
            time.sleep(watch_seconds)

    # Private

    @staticmethod
    def _exceeded_max(count, limit):
        if limit and limit <= count:
            _logger.debug('Prematurely stopping at match maximum of {0}'.format(limit))
            return True
        return False

    def _set_namespace(self):
        ns = '' if self._config.namespace == self.ANY else self._config.namespace
        self._namespace_re = re.compile(ns)
        self._selected_namespaces = []
        ns_cache = self._cache('namespaces')
        for info in ns_cache.obj()['items']:
            name = info['metadata']['name']
            if not self._namespace_re.search(name):
                continue
            phase = info['status']['phase']
            if phase != 'Active':
                _logger.warn("Skiping {0} namespace: phase={1}".format(name, phase))
                continue
            self._selected_namespaces.append(name)
        if not self._selected_namespaces:
            raise self.UnknownNamespace(self._config.namespace)

    def _split_match(self):
        match_items = self._config.match.split('/', 2)
        node = match_items.pop(0) if len(match_items) > 2 else ''
        pod = match_items.pop(0)
        container = match_items.pop(0) if len(match_items) > 0 else ''
        if node == self.ANY:
            node = ''
        if pod == self.ANY:
            pod = ''
        if container == self.ANY:
            container = ''
        self._node_re = re.compile(node, re.IGNORECASE)
        self._pod_re = re.compile(pod, re.IGNORECASE)
        self._container_re = re.compile(container, re.IGNORECASE)

    def _cache(self, name, *args):
        cache_fn = os.path.join(
            self._config.cache_path, '.%s_%s_%s' % (__name__, self.kubectl.context, name)
        )
        return Cache(
            cache_fn, 3600, self.kubectl.call_json, 'get', name, *args
        )

    def _pod_matches(self, info):
        return (self._namespace_re.search(info['metadata']['namespace']) and
                self._node_re.search(info['spec'].get('nodeName', '')) and
                self._pod_re.search(info['metadata']['name']))

    def _node_matches(self, info):
        return self._node_re.search(info['metadata']['name'])

    def _event_matches(self, info):
        return (self._namespace_re.search(info['metadata']['namespace']) and
                self._node_re.search(info['source'].get('host', '')) and
                self._pod_re.search(info['metadata']['name']))

    def _get_top_node_info(self):
        info = {}

        def add_info(i, row):
            if i == 1:
                return
            info[row[0]] = row[1:]

        self.kubectl.call_table_rows(add_info, 'top', 'node')
        self.kubectl.wait()
        return info
