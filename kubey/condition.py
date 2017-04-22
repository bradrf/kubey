import re
from .item import Item


class Condition(Item):
    PRIMARY_ATTRIBUTES = ('name', 'status', 'reason')
    ATTRIBUTES = PRIMARY_ATTRIBUTES

    class UnknownStatusError(ValueError):
        pass

    def __init__(self, config, info, expect=True):
        super(Condition, self).__init__(config, info)
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
        super(NodeCondition, self).__init__(config, info)
        self.reason = re.sub(r'^kubelet (has|is) ', '', info.get('message', ''))
        # conditions other than "ready" use a positive to indicate "not satisfied" (i.e. failed)
        self._expected_status = self.name == 'Ready'

    def __str__(self):
        if self.ok:
            return self.reason
        return super(self.__class__, self).__str__()
