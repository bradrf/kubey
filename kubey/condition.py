import re
from copy import copy


class Condition(object):
    class UnknownStatusError(ValueError):
        pass

    def __init__(self, config, info, expect=True):
        self._config = config
        self.name = info['type']
        status = info['status']
        if status == 'True':
            self.status = True
        elif status == 'False':
            self.status = False
        else:
            self.status = status
        self.reason = info.get('reason')
        self._expected_status = expect

    def __repr__(self):
        return '<Condition: {0} status={1} reason={2}>'.format(self.name, self.reason)

    def __str__(self):
        if self.ok:
            return self.name
        rstr = '{0}:{1}'.format(self.name, self.reason) if self.reason else ('not ' + self.name)
        return self._config.highlight_error(rstr)

    @property
    def ok(self):
        return self.status == self._expected_status


class NodeCondition(Condition):
    def __init__(self, config, info):
        info = copy(info)
        name = info['type']
        info['reason'] = re.sub(r'^kubelet (has|is) ', '', info.get('message', ''))
        # conditions other than "ready" use a positive to indicate "not satisfied (i.e. failed)"
        super(self.__class__, self).__init__(config, info, name == 'Ready')

    def __str__(self):
        if self.ok:
            return self.reason
        return super(self.__class__, self).__str__()
