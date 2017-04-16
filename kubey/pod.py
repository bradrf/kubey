from datetime import datetime
import dateutil.parser
import dateutil.tz
from .condition import Condition
from .container import Container


class Pod(object):
    ATTRIBUTES = ('name', 'namespace', 'node_name', 'phase', 'host_ip',
                  'pod_ip', 'start_time', 'conditions', 'containers')

    _TERMINATED_STATUS = {
        'ready': False,
        'restartCount': -1,
        'state': {
            'terminated': {
                'startedAt': datetime.fromtimestamp(0, tz=dateutil.tz.tzutc()).isoformat()
            }
        }
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

        def __repr__(self):
            if self._reason:
                return '{0}:{1}:{2}'.format(
                    self._phase, self._config.highlight_error(self._reason), self._message)
            if self._phase == 'Running':
                return self._phase
            highlighter = self._config.highlight_error if self._phase == 'Failed' else \
                self._config.highlight_warn
            return highlighter(self._phase)

    def __init__(self, config, info, container_selector):
        self._config = config
        metadata = info['metadata']
        status = info['status']
        spec = info['spec']
        self.name = metadata['name']
        self.namespace = metadata['namespace']
        self.node_name = spec.get('nodeName')
        self.phase = self.Phase(self._config, status['phase'])
        self.host_ip = status.get('hostIP')
        self.pod_ip = status.get('podIP')
        self.start_time = dateutil.parser.\
            parse(status['startTime']) if 'startTime' in status else None
        self._extract_conditions(status.get('conditions', []))
        self._extract_containers(spec['containers'],
                                 status.get('containerStatuses', []),
                                 container_selector)

    def __repr__(self):
        return '<Pod: {0} namespace={1} phase={2}>'.format(self.name, self.namespace, self.phase)

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
