import tabulate as real_tabulate
from configstruct import OpenStruct
from . import serializers


formats = real_tabulate.tabulate_formats


class RowCollector(object):
    def __init__(self):
        self.headers = None
        self.rows = []

    def handler_for(self, namespace):
        def add(i, row):
            if i == 1:
                if not self.headers:
                    self.headers = ['namespace'] + [c.lower() for c in row]
                return
            self.rows.append(OpenStruct(zip(self.headers, [namespace] + row)))
        return add


class RowExtractor(object):
    def __init__(self, config, attributes):
        self._config = config
        self._attributes = attributes
        self._serializers = serializers.all(config)

    def row_from(self, obj):
        row = []
        for attr in self._attributes:
            value = getattr(obj, attr)
            for serializer in self._serializers:
                if serializer.match(attr):
                    value = serializer.serialize(value)
                    break
            row.append(value)
        return row


def tabulate(config, objs, columns, flat=False, serialize=True):
    flattener = flatten if flat else None
    extractor = RowExtractor(config, columns)
    headers = [] if config.no_headers else columns
    rows = each_row(objs, flattener, extractor)
    return real_tabulate.tabulate(rows, headers=headers, tablefmt=config.table_format)


def each_row(objs, flattener, row_extractor):
    for row in table_of(objs, row_extractor):
        if flattener:
            for i, item in enumerate(row):
                if is_iterable(item):
                    row[i] = flattener(item)
            yield row
            continue
        # extract out a _copy_ of iterable items and populate into "exploded" rows
        iterables = {i: list(item) for i, item in enumerate(row) if is_iterable(item)}
        if not iterables:
            yield row
            continue
        exploded = row
        while True:
            exploding = False
            for i, iterable in iterables.iteritems():
                if len(iterable) > 0:
                    exploding = True
                    exploded[i] = iterable.pop(0)
            if not exploding:
                break
            yield exploded
            exploded = [''] * len(row)  # reset next row with empty columns


def flatten(enumerable):
    return ' '.join(str(i) for i in enumerable)


def table_of(objs, row_extractor):
    return (row_extractor.row_from(o) for o in objs)


def is_iterable(item):
    # just simple ones for now
    return isinstance(item, (list, tuple))
