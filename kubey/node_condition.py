import re


class NodeCondition(object):
    def __init__(self, name, status, reason, highlight=False):
        self.name = name
        self.status = status
        self.reason = re.sub(r'^kubelet (has|is) ', '', reason)
        self._highlight = highlight

    def __repr__(self):
        if self._highlight:
            ok = 'True' if self.name == 'Ready' else 'False' # other conditions have True has "bad"
            if self.status == ok:
                return self.reason
            return click.style(str(self.reason), bold=True, fg='red')
        return self.reason
