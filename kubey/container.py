import json
import click


class Container(object):
    def __init__(self, name, ready, state, image, highlight=False):
        self.name = name
        self.ready = ready
        self.state = state
        self.image = image
        self._highlight = highlight

    def __repr__(self):
        if self._highlight:
            color = 'green' if self.ready else 'red'
            rstr = click.style(str(self.ready), bold=True, fg=color)
        else:
            rstr = self.ready
        return 'name:%s ready:%s state:%s image:%s' % (
            self.name, rstr, json.dumps(self.state), self.image
        )
