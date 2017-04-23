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


class Kubey(object):
    class UnknownNamespace(ValueError):
        pass

    ANY = '.'

    def __init__(self, config):
        self._config = config
        self.kubectl = KubeCtl(config.context)
        self._split_match()
        self._namespaces = self._cache('namespaces')
        self._nodes_cache = self._cache('nodes')
        self._pods_cache = self._cache('pods', '--all-namespaces')
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
        self._pods = []
        for info in self._pods_cache.obj()['items']:
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
        top_info = self._get_top_node_info() if include_top_info else {}
        self._nodes = []
        for info in self._nodes_cache.obj()['items']:
            if not self._node_matches(info):
                continue
            node = Node(self._config, info, self.each_pod(), top_info)
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
        if self._config.namespace == self.ANY:
            return
        # FIXME: namespace validation!
        # validation_query = 'items[?contains(metadata.name,\'%s\')].status.phase' % (
        #     self._config.namespace)
        # if not jmespath.search(validation_query, self._namespaces.obj()):
        #     raise self.UnknownNamespace(self._config.namespace)

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
            cache_fn, self._config.cache_seconds, self.kubectl.call_json, 'get', name, *args
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
