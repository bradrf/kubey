import re


class Condition(object):
    class UnknownStatusError(ValueError):
        pass

    def __init__(self, config, name, status, expect=True):
        self._config = config
        self.name = name
        if status == 'True':
            self.status = True
        elif status == 'False':
            self.status = False
        else:
            raise self.UnknownStatusError('name={0} status={1}'.format(name, status))
        self._expected_status = expect

    def __repr__(self):
        if self.status == self._expected_status:
            return self.name
        return self._config.highlight_error(self.name)


class NodeCondition(Condition):
    def __init__(self, config, name, reason, status):
        simple_reason = re.sub(r'^kubelet (has|is) ', '', reason)
        # conditions other than "ready" use positive to indicate a problem
        super(self.__class__, self).__init__(config, simple_reason, status, name == 'Ready')
