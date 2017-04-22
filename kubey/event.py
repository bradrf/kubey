from . import timestamp


class Event(object):
    PRIMARY_ATTRIBUTES = ('last_time', 'name', 'count', 'info')
    ATTRIBUTES = PRIMARY_ATTRIBUTES + ('first_time', 'level', 'reason', 'message')

    def __init__(self, config, info):
        self._config = config
        metadata = info['metadata']
        self.level = info['type']
        self.name = metadata['name']
        self.namespace = metadata['namespace']
        self.count = info['count']
        self.reason = info['reason']
        self.message = info['message']
        self.first_time = timestamp.parse(info['firstTimestamp'])
        self.last_time = timestamp.parse(info['lastTimestamp'])

    def __repr__(self):
        return '<Event: {0} {1}>'.format(self.reason, self.message)

    @property
    def info(self):
        rstr = self.reason if self.level == 'Normal' else self._config.highlight_warn(self.reason)
        return '{0}: {1}'.format(rstr, self.message)
