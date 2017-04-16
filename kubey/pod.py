import dateutil.parser
from .condition import Condition
from .container import Container


class Pod(object):
    def __init__(self, config, info, container_selector):
        self._config = config
        metadata = info['metadata']
        status = info['status']
        spec = info['spec']
        self.name = metadata['name']
        self.namespace = metadata['namespace']
        self.node_name = spec.get('nodeName')
        self.phase = status['phase']
        self.host_ip = status.get('hostIP')
        self.pod_ip = status.get('podIP')
        self.start_time = dateutil.parser.\
            parse(status['startTime']) if 'startTime' in status else None
        self._extract_conditions(status['conditions'])
        self._extract_containers(spec['containers'],
                                 status.get('containerStatuses', []),
                                 container_selector)

    def __repr__(self):
        return '<Pod: {0} namespace={1}>'.format(self.name, self.namespace)

    def _extract_conditions(self, info):
        self.conditions = [Condition(self._config, o['type'], o['status']) for o in info]

    def _extract_containers(self, info, status_info, selector):
        self.containers = []
        for info in info:
            name = info['name']
            if selector(name):
                status = self._status_for(name, status_info)
                self.containers.append(Container(self._config, info, status))

    @staticmethod
    def _status_for(name, statuses):
        try:
            return next(s for s in statuses if s['name'] == name)
        except StopIteration:
            raise ValueError('Status not found: ' + name)
