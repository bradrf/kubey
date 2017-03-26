import os
import re
import logging
import jmespath

from .kubectl import KubeCtl
from .cache import Cache
from .container import Container


_logger = logging.getLogger(__name__)


class Kubey(object):
    class UnknownNamespace(ValueError):
        pass

    ANY = '.'

    COLUMN_MAP = {
        'name': 'metadata.name',
        'namespace': 'metadata.namespace',
        'node': 'spec.nodeName',
        'node-ip': 'status.hostIP',
        'status': 'status.phase',
        # 'conditions': 'status.conditions[*].[type,status,message]',
        'containers': 'status.containerStatuses[*].[name,ready,state,image]',
    }

    def __init__(self, config):
        self._config = config
        self._kubectl = KubeCtl(config.context)
        self._split_match()
        self._namespaces = self._cache('namespaces')
        self._nodes = self._cache('nodes')
        self._pods = self._cache('pods', '--all-namespaces')
        self._set_namespace()

    def __repr__(self):
        return "<Kubey: context=%s namespace=%s match=%s/%s/%s>" % (
            self._kubectl.context, self._namespace,
            self._node_re.pattern, self._pod_re.pattern, self._container_re.pattern)

    def each(self, columns=['namespace', 'name', 'containers']):
        container_index = self._container_index_of(columns)
        cols = ['node', 'name', 'containers'] + columns
        # FIXME: use set and indices map: {v: i for i, v enumerate(cols)}
        count = 0
        for pod in self.each_pod(cols):
            (node_name, pod_name, container_info), col_values = pod[:3], pod[3:]  # FIXME: duplication
            if not self._node_re.search(node_name):
                continue
            if not self._pod_re.search(pod_name):
                continue
            containers = []
            for (name, ready, state, image) in container_info:
                if not self._container_re.search(name):
                    continue
                containers.append(Container(self._config, name, ready, state, image))
            if not containers:
                continue
            if container_index:
                col_values[container_index] = containers
            count += 1
            if self._config.limit and self._config.limit < count:
                _logger.debug('Prematurely stopping at match limit of ' + str(self._config.limit))
                break
            yield(col_values)

    def each_pod(self, columns):
        query = self._namespace_query + '.[' + ','.join([self.COLUMN_MAP[c] for c in columns]) + ']'
        pods = self._pods.obj()
        for pod in jmespath.search(query, pods):
            yield pod

    # Private:

    @staticmethod
    def _container_index_of(columns):
        return columns.index('containers') if 'containers' in columns else None

    def _set_namespace(self):
        if self._config.namespace == self.ANY:
            self._namespace_query = 'items[*]'
        else:
            self._namespace_query = 'items[?contains(metadata.namespace,\'%s\')]' % (
                self._config.namespace)
        if (self._config.namespace == self.ANY):
            return
        validation_query = 'items[?contains(metadata.name,\'%s\')].status.phase' % (
            self._config.namespace)
        if not jmespath.search(validation_query, self._namespaces.obj()):
            raise UnknownNamespace(self._namespace)

    def _split_match(self):
        match_items = self._config.match.split('/', 2)
        node = match_items.pop(0) if len(match_items) > 2 else ''
        pod = match_items.pop(0)
        container = match_items.pop(0) if len(match_items) > 0 else ''
        self._node_re = re.compile(node, re.IGNORECASE)
        self._pod_re = re.compile(pod, re.IGNORECASE)
        self._container_re = re.compile(container, re.IGNORECASE)

    def _cache(self, name, *args):
        cache_fn = os.path.join(
            self._config.cache_path, '.%s_%s_%s' % (__name__, self._kubectl.context, name)
        )
        return Cache(
            cache_fn, self._config.cache_seconds, self._kubectl.call_json, 'get', name, *args
        )
