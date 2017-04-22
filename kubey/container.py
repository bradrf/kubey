from . import timestamp
from .item import Item


class Container(Item):
    class UnknownStateError(ValueError):
        pass

    PRIMARY_ATTRIBUTES = ('name', 'ready')
    ATTRIBUTES = PRIMARY_ATTRIBUTES + ('state', 'started_at', 'restart_count', 'image')

    def __init__(self, config, info, status):
        super(self.__class__, self).__init__(config, info)
        state_info = status['state']
        if len(state_info) != 1:
            raise self.UnknownStateError(str(status))
        self.state = state_info.keys()[0]
        state_details = state_info.values()[0]
        self.started_at = timestamp.parse(state_details.get('startedAt'))
        self.restart_count = status['restartCount']
        self.ready = status['ready']
        self.image = info['image']

    def __str__(self):
        highlighter = self._config.highlight_ok if self.ready else self._config.highlight_error
        rstr = highlighter(self.ready)
        if self._config.wide:
            if self.restart_count > 9:
                rsts = self._config.highlight_error(' restarts:{0}'.format(self.restart_count))
            elif self.restart_count > 0:
                rsts = self._config.highlight_warn(' restarts:{0}'.format(self.restart_count))
            else:
                rsts = ''
            return 'name={0} ready={1} state={2} started={3}{4} image={5}'.format(
                self.name, rstr, self.state,
                timestamp.in_words_from_now(self.started_at),
                rsts, self.image
            )
        return 'name=%s ready=%s' % (self.name, rstr)
