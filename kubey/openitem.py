from .item import Item


class OpenItem(Item):
    def __init__(self, headers, values):
        if len(headers) != len(values):
            raise ValueError('mismatched headers and values')
        self.ATTRIBUTES = headers
        for attr in headers:
            setattr(self, attr, values.pop(0))
