import dateutil.parser
from .condition import NodeCondition


class Node(object):
    ATTRIBUTES = ('name', 'status', 'cpu_cores', 'cpu_percent', 'memory_bytes', 'memory_percent',
                  'creation_time', 'conditions', 'pods')

    def __init__(self, config, info, all_pods, top_info):
        self._config = config
        self._all_pods = all_pods
        self._pods = None
        metadata = info['metadata']
        status = info['status']
        spec = info['spec']
        self.name = metadata['name']
        self.creation_time = dateutil.parser.parse(metadata['creationTimestamp'])
        self.schedulable = not spec.get('unschedulable', False)
        self.status = 'Ready' if self.schedulable else \
            self._config.highlight_warn('SchedulingDisabled')
        self.conditions = [NodeCondition(self._config, o) for o in status['conditions']]
        self._consider(top_info)

    @property
    def pods(self):
        if self._pods is None:
            self._pods = [p for p in self._all_pods if p.node_name == self.name]
        return self._pods

    def __repr__(self):
        return '<Node: {0} schedulable={1}>'.format(
            self.name, self.schedulable)

    def _consider(self, top_info):
        info = top_info.get(self.name)
        self.cpu_cores = info[0] if info else None
        self.cpu_percent = info[1] if info else None
        self.memory_bytes = info[2] if info else None
        self.memory_percent = info[3] if info else None
