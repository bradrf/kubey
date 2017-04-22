from . import timestamp


class Container(object):
    class UnknownStateError(ValueError):
        pass

    def __init__(self, config, info, status):
        self._config = config
        self.name = info['name']
        state_info = status['state']
        if len(state_info) != 1:
            raise self.UnknownStateError(str(status))
        self.state = state_info.keys()[0]
        state_details = state_info.values()[0]
        self.started_at = timestamp.parse(state_details.get('startedAt'))
        self.restart_count = status['restartCount']
        self.ready = status['ready']
        self.image = info['image']

    def __repr__(self):
        return '<Container: {0} ready={1}>'.format(self.name, self.ready)

    def __str__(self):
        highlighter = self._config.highlight_ok if self.ready else self._config.highlight_error
        rstr = highlighter(self.ready)
        if self._config.wide:
            if self.restart_count > 0:
                rsts = self._config.highlight_warn(' restarts:{0}'.format(self.restart_count))
            else:
                rsts = ''
            return 'name={0} ready={1} state={2} started={3}{4} image={5}'.format(
                self.name, rstr, self.state,
                timestamp.in_words_from_now(self.started_at),
                rsts, self.image
            )
        return 'name=%s ready=%s' % (self.name, rstr)
