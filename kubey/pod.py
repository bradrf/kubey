from . import timestamp
from .item import Item
from .condition import Condition
from .container import Container


class Pod(Item):
    PRIMARY_ATTRIBUTES = ('name', 'phase', 'conditions', 'containers')
    ATTRIBUTES = PRIMARY_ATTRIBUTES + ('labels', 'namespace', 'node_name', 'node',
                                       'host_ip', 'pod_ip', 'start_time')

    _TERMINATED_STATUS = {
        'ready': False,
        'restartCount': -1,
        'state': {'terminated': {'startedAt': timestamp.epoch.isoformat()}}
    }

    class Phase(object):
        def __init__(self, config, info):
            self._config = config
            if isinstance(info, dict):
                self._phase = info['phase']
                self._message = info.get('message')
                self._reason = info.get('reason')
            else:
                self._phase = info
                self._reason = None
                self._message = None
            self.running = self._phase == 'Running'

        def __repr__(self):
            return '<Phase: {0} reason={1} message={2}>'.format(
                self._phase, self._reason, self._message)

        def __str__(self):
            if self._reason:
                return '{0}:{1}:{2}'.format(
                    self._phase, self._config.highlight_error(self._reason), self._message)
            if self.running:
                return self._phase
            highlighter = self._config.highlight_error if self._phase == 'Failed' else \
                self._config.highlight_warn
            return highlighter(self._phase)

    def __init__(self, config, info, container_selector):
        super(Pod, self).__init__(config, info)
        status = info['status']
        spec = info['spec']
        self.node_name = spec.get('nodeName')
        self._node = None
        self.phase = self.Phase(self._config, status)
        self.host_ip = status.get('hostIP')
        self.pod_ip = status.get('podIP')
        self.start_time = timestamp.parse(status.get('startTime'))
        self._extract_conditions(status.get('conditions', []))
        self._extract_containers(spec['containers'],
                                 status.get('containerStatuses', []),
                                 container_selector)

    def __str__(self, namespaced=False):
        pstr = '' if self.phase.running else ':' + str(self.phase)
        if namespaced:
            return '{0}/{1}{2}'.format(self.namespace, self.name, pstr)
        return '{0}{1}'.format(self.name, pstr)

    @property
    def node(self):
        return [self.node_name, self.host_ip]

    def _extract_conditions(self, info):
        self.conditions = [Condition(self._config, o) for o in info]

    def _extract_containers(self, info, status_info, selector):
        self.containers = []
        for info in info:
            name = info['name']
            if selector(name):
                status = self._status_for(name, status_info)
                if not status:
                    term = info.get('terminationMessagePath')
                    if not term:
                        raise ValueError('Status not found: ' + name)
                    status = self._TERMINATED_STATUS
                self.containers.append(Container(self._config, info, status))

    @staticmethod
    def _status_for(name, statuses):
        try:
            return next(s for s in statuses if s['name'] == name)
        except StopIteration:
            return None
