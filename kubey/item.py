class Item(object):
    '''Common logic shared across all kinds of objects.'''

    class UnknownAttributeError(ValueError):
        def __init__(self, attributes):
            super(Item.UnknownAttributeError, self).__init__(
                "Unknown attributes: {0}".format(attributes))

    COMMON_ATTRIBUTES = ('name', 'namespace')

    def __init__(self, config, info):
        self._config = config
        for attr in self.COMMON_ATTRIBUTES:
            val = info.get(attr)
            if not val and 'metadata' in info:
                val = info['metadata'].get(attr)
            if val:
                setattr(self, attr, val)

    def __repr__(self):
        return '<{0}: {1}>'.format(
            self.__class__.__name__,
            ' '.join('{0}={1}'.format(a, v) for a, v in self._simple_attrvals)
        )

    def attrvals(self, attributes):
        unknown = set(attributes) - set(self.ATTRIBUTES)
        if unknown:
            raise self.UnknownAttributeError(unknown)
        return ((a, getattr(self, a)) for a in attributes)

    @property
    def _simple_attrvals(self):
        for attr in self.COMMON_ATTRIBUTES:
            if hasattr(self, attr):
                yield (attr, getattr(self, attr))
        for attr in self.PRIMARY_ATTRIBUTES:
            if attr in self.COMMON_ATTRIBUTES or self._property(attr):
                continue
            val = getattr(self, attr)
            if not isinstance(val, (list, tuple, dict)):
                yield (attr, val)

    def _property(self, attr):
        return isinstance(getattr(type(self), attr, None), property)
