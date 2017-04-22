import re
from . import timestamp
from .kubey import Kubey


class ColumnSerializer(object):
    def __init__(self, config):
        self._config = config

    def match(self, _column):
        return True

    def serialize(self, obj):
        return str(obj)


class TimestampSerializer(ColumnSerializer):
    def match(self, column):
        return column.endswith('_time')

    def serialize(self, stamp):
        return timestamp.as_local(stamp)


class RelativeTimestampSerializer(TimestampSerializer):
    def serialize(self, stamp):
        return timestamp.in_words_from_now(stamp, ' ')


class LevelSerializer(ColumnSerializer):
    def match(self, column):
        return column == 'level'

    def serialize(self, level):
        if level == 'Normal':
            return self._config.highlight_ok(level)
        return self._config.highlight_warn(level)


class PodsSerializer(ColumnSerializer):
    def match(self, column):
        return column == 'pods'

    def serialize(self, pods):
        if self._config.namespace == Kubey.ANY:
            return [pod.__str__(True) for pod in pods]
        return pods


class PercentSerializer(ColumnSerializer):
    PERCENT_RE = re.compile(r'^(\d+)\s*%$')

    def match(self, column):
        return column.endswith('_percent')

    def serialize(self, value):
        if not value:
            return value
        m = self.PERCENT_RE.match(value)
        if not m:
            return value
        v = int(m.group(1))
        if v >= self._config.hard_percent_limit:
            return self._config.highlight_error(value)
        if v >= self._config.soft_percent_limit:
            return self._config.highlight_warn(value)
        return value


def default(config):
    return (RelativeTimestampSerializer(config), LevelSerializer(config),
            PodsSerializer(config), PercentSerializer(config))
