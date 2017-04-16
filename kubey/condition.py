import re


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
            raise self.UnknownStatusError(str(info))
        self.reason = info.get('reason')
        self._expected_status = expect

    def __repr__(self):
        if self.status == self._expected_status:
            return self.name
        rstr = '{0}:{1}'.format(self.name, self.reason) if self.reason else self.name
        return self._config.highlight_error(rstr)


class NodeCondition(Condition):
    def __init__(self, config, info):
        name = info['type']
        simple_reason = re.sub(r'^kubelet (has|is) ', '', info.get('reason', ''))
        # conditions other than "ready" use a positive to indicate "not satisfied (i.e. failed)"
        super(self.__class__, self).__init__(config, name, simple_reason, name == 'Ready')
