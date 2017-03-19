import json
import click


class Container(object):
    def __init__(self, config, name, ready, state, image):
        self.name = name
        self.ready = ready
        self.state = state
        self.image = image
        self._config = config

    def __repr__(self):
        if self._config.highlight:
            color = 'green' if self.ready else 'red'
            rstr = click.style(str(self.ready), bold=True, fg=color)
        else:
            rstr = self.ready
        if self._config.wide:
            return 'name:%s ready:%s state:%s image:%s' % (
                self.name, rstr, json.dumps(self.state), self.image
            )
        return 'name:%s ready:%s' % (self.name, rstr)
