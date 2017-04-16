from datetime import datetime
import dateutil.parser
import dateutil.relativedelta
import dateutil.tz


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
        self.started_at = dateutil.parser.parse(state_info.values()[0]['startedAt'])
        self.restart_count = status['restartCount']
        self.ready = status['ready']
        self.image = info['image']

    def __repr__(self):
        highlighter = self._config.highlight_ok if self.ready else self._config.highlight_error
        rstr = highlighter(self.ready)
        if self._config.wide:
            if self.restart_count > 0:
                rsts = self._config.highlight_warn(' restarts:{0}'.format(self.restart_count))
            else:
                rsts = ''
            return 'name:{0} ready:{1} state:{2} started:{3}{4} image:{5}'.format(
                self.name, rstr, self.state, self._started_at_humanized(), rsts, self.image
            )
        return 'name:%s ready:%s' % (self.name, rstr)

    def _started_at_humanized(self):
        now = datetime.now(dateutil.tz.tzlocal())
        rdate = dateutil.relativedelta.relativedelta(now, self.started_at)
        if rdate.years > 0 or rdate.months > 0 or rdate.weeks > 0 or rdate.days > 0:
            return self.started_at.astimezone(dateutil.tz.tzlocal()).isoformat()
        if rdate.hours > 0:
            return '{:0.1f}_hours_ago'.format(rdate.hours + (rdate.minutes / 60.0))
        return '{:0.1f}_min_ago'.format(rdate.minutes + (rdate.seconds / 60.0))
