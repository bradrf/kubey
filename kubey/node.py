from . import timestamp
from .item import Item
from .condition import NodeCondition


class Node(Item):
    PRIMARY_ATTRIBUTES = ('identity', 'status', 'cpu_percent',
                          'memory_percent', 'conditions', 'pods')
    ATTRIBUTES = PRIMARY_ATTRIBUTES + ('name', 'labels', 'private_ip', 'external_ip', 'hostname',
                                       'cpu_cores', 'memory_bytes', 'creation_time')

    def __init__(self, config, info, all_pods, top_info):
        super(Node, self).__init__(config, info)
        self._all_pods = all_pods
        self._pods = None
        metadata = info['metadata']
        status = info['status']
        spec = info['spec']
        self.creation_time = timestamp.parse(metadata['creationTimestamp'])
        self.schedulable = not spec.get('unschedulable', False)
        self.status = 'Ready' if self.schedulable else \
            self._config.highlight_warn('SchedulingDisabled')
        self.conditions = [NodeCondition(self._config, o) for o in status['conditions']]
        self._extract_addresses(status['addresses'])
        self._consider(top_info)

    @property
    def identity(self):
        return [self.name] + \
            [a for a in (self.private_ip, self.external_ip, self.hostname) if a]

    @property
    def pods(self):
        if self._pods is None:
            self._pods = [p for p in self._all_pods if p.node_name == self.name]
        return self._pods

    def _extract_addresses(self, info):
        self.private_ip = self.external_ip = self.hostname = None
        for item in info:
            key = item['type']
            if key == 'InternalIP':
                self.private_ip = item['address']
            elif key == 'LegacyHostIP' and not self.private_ip:
                self.private_ip = item['address']
            elif key == 'ExternalIP':
                self.external_ip = item['address']
            elif key == 'Hostname':
                val = item['address']
                if val not in self.name:
                    self.hostname = val

    def _consider(self, top_info):
        info = top_info.get(self.name)
        self.cpu_cores = info[0] if info else None
        self.cpu_percent = info[1] if info else None
        self.memory_bytes = info[2] if info else None
        self.memory_percent = info[3] if info else None
