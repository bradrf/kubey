from . import timestamp
from .item import Item


class Event(Item):
    PRIMARY_ATTRIBUTES = ('last_time', 'name', 'count', 'info')
    ATTRIBUTES = PRIMARY_ATTRIBUTES + ('namespace', 'first_time', 'level', 'reason', 'message')

    def __init__(self, config, info):
        super(Event, self).__init__(config, info)
        self.level = info['type']
        self.count = info['count']
        self.reason = info['reason']
        self.message = info['message']
        self.first_time = timestamp.parse(info['firstTimestamp'])
        self.last_time = timestamp.parse(info['lastTimestamp'])

    @property
    def info(self):
        rstr = self.reason if self.level == 'Normal' else self._config.highlight_warn(self.reason)
        return '{0}: {1}'.format(rstr, self.message)
