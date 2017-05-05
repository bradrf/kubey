import types
import tabulate as real_tabulate
from . import serializers
from .openitem import OpenItem


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
            self.rows.append(OpenItem(self.headers, [namespace] + row))
        return add


class RowExtractor(object):
    def __init__(self, config, attributes, serializers):
        self._config = config
        self._attributes = attributes
        self._serializers = serializers

    def row_from(self, item):
        row = []
        for attr, value in item.attrvals(self._attributes):
            for serializer in self._serializers:
                if serializer.match(attr):
                    value = serializer.serialize(value)
                    break
            row.append(value)
        return row


def tabulate(config, items, columns, flat=False, serialize=True):
    flattener = flatten if flat else None
    extractor = RowExtractor(config, columns, serializers.default(config))
    headers = [] if config.no_headers else columns
    rows = each_row(items, flattener, extractor)
    return real_tabulate.tabulate(rows, headers=headers, tablefmt=config.table_format)


def lines(config, items, columns):
    serials = [s for s in serializers.default(config)
               if not isinstance(s, serializers.RelativeTimestampSerializer)] + \
        [serializers.TimestampSerializer(config)]
    extractor = RowExtractor(config, columns, serials)
    for row in each_row(items, None, extractor):
        yield '   '.join((str(i) for i in row))


def each_row(items, flattener, row_extractor):
    for row in table_of(items, row_extractor):
        if flattener:
            for i, item in enumerate(row):
                if is_iterable(item):
                    row[i] = flattener(item)
            yield row
            continue
        # extract out a _copy_ of iterable items and populate into "exploded" rows
        iterables = {i: expand(item) for i, item in enumerate(row) if is_iterable(item)}
        if not iterables:
            yield row
            continue
        exploded = row
        while True:
            exploding = False
            for i, iterable in iterables.items():
                if len(iterable) > 0:
                    exploding = True
                    exploded[i] = iterable.pop(0)
            if not exploding:
                break
            yield exploded
            exploded = [''] * len(row)  # reset next row with empty columns


def flatten(enumerable):
    return ' '.join(str(i) for i in expand(enumerable))


def table_of(items, row_extractor):
    return (row_extractor.row_from(o) for o in items)


def expand(item):
    if isinstance(item, types.GeneratorType):
        return list(item)
    if isinstance(item, dict):
        return ['{0}={1}'.format(k, v) for k, v in item.items()]
    return item


def is_iterable(item):
    # just simple ones for now
    return isinstance(item, (list, tuple, dict))
