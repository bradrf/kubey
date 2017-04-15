import os
import sys
import logging
import re
import signal
import click

from tabulate import tabulate, tabulate_formats
from configstruct import OpenStruct

from .kubey import Kubey


_logger = None


@click.group(invoke_without_command=True, context_settings=dict(help_option_names=['-h', '--help']))
@click.version_option()
@click.option('--cache-seconds', envvar='KUBEY_CACHE_SECONDS', default=300, show_default=True,
              help='change number of seconds to keep pod info cached')
@click.option('-l', '--log-level', envvar='KUBEY_LOG_LEVEL',
              type=click.Choice(('debug', 'info', 'warning', 'error', 'critical')),
              default='info', help='set logging level')
@click.option('-c', '--context', envvar='KUBEY_CONTEXT', help='context to use when selecting')
@click.option('-n', '--namespace', envvar='KUBEY_NAMESPACE', default='production',
              show_default=True, help='namespace to use when selecting')
@click.option('-f', '--format', 'table_format', envvar='KUBEY_TABLE_FORMAT',
              type=click.Choice(tabulate_formats), default='simple',
              show_default=True, help='output format of tabular data (e.g. listing)')
@click.option('-m', '--max', 'maximum', type=int, help='max number of matches')
@click.option('--no-headers', is_flag=True, help='disable table headers')
@click.option('--wide', is_flag=True, help='force use of wide output')
@click.argument('match')
@click.pass_context
def cli(ctx, cache_seconds, log_level, context, namespace,
        table_format, maximum, no_headers, wide, match):
    '''Simple wrapper to help find specific Kubernetes pods and containers and run asynchronous
    commands (default is to list those that matched).

    \b
    MATCH       [<NODE>/]<POD>[/<CONTAINER>]
    \b
    NODE        provide a regular expression to select one or more nodes
    POD         provide a regular expression to select one or more pods
    CONTAINER   provide a regular expression to select one or more containers
    \b
    Partial match using just node or just node and pod, provide trailing slash:
        my-node//          match all pods and containers hosted in my-node
        my-node/my-pod/    match all containers hosted in my-node/my-pod
    '''

    logging.basicConfig(
        level=getattr(logging, log_level.upper()),
        format='[%(asctime)s #%(process)d] %(levelname)-8s %(name)-12s %(message)s',
        datefmt='%Y-%m-%dT%H:%M:%S%z'
    )
    global _logger
    _logger = logging.getLogger(__name__)

    if not wide:
        width, height = click.get_terminal_size()
        wide = width > 160

    ctx.obj = OpenStruct(
        highlight=sys.stdout.isatty(),
        cache_path=os.path.expanduser('~'),
        cache_seconds=cache_seconds,
        context=context,
        namespace=namespace,
        table_format=table_format,
        no_headers=no_headers,
        wide=wide,
        maximum=maximum,
        match=match,
    )
    ctx.obj.kubey = Kubey(ctx.obj)

    def handle_interrupt(signal, _frame):
        ctx.obj.kubey.kubectl.kill(signal)
        ctx.exit(22)
    signal.signal(signal.SIGINT, handle_interrupt)
    signal.signal(signal.SIGTERM, handle_interrupt)

    if not ctx.invoked_subcommand:
        ctx.invoke(list_pods)


@cli.command(name='list')
@click.option('-c', '--columns', default=','.join(Kubey.POD_COLUMN_MAP.keys()), show_default=True,
              help='specify specific columns to show')
@click.option('-f', '--flat', is_flag=True, help='flatten columns with multiple items')
@click.pass_obj
def list_pods(obj, columns, flat):
    '''List available pods and containers for current context.'''
    # TODO: replace (extend?) node to be name instead of private ip now we have node info for health
    columns = [c.strip() for c in columns.split(',')]
    flattener = flatten if flat else None
    headers = [] if obj.no_headers else columns
    rows = each_row(obj.kubey.each(columns), flattener)
    click.echo(tabulate(rows, headers=headers, tablefmt=obj.table_format))


@cli.command()
@click.pass_obj
def webui(obj):
    '''List dashboard links for matching pods. Three or fewer will be opened automatically.'''
    kubectl = obj.kubey.kubectl
    info = click.unstyle(kubectl.call_capture('cluster-info'))
    dash_endpoint = re.search(r'kubernetes-dashboard.*?(http\S+)', info).group(1)
    urls = []
    for (namespace, pod_name, containers) in obj.kubey.each():
        pod_path = '/#/pod/%s/%s?namespace=%s' % (namespace, pod_name, namespace)
        urls.append(dash_endpoint + pod_path)
    if len(urls) == 1:
        url = urls[0]
        click.echo(url)
        click.launch(url)
    else:
        for url in urls:
            click.echo(url)


@cli.command()
@click.argument('repl')
@click.argument('arguments', nargs=-1, type=click.UNPROCESSED)
@click.pass_context
def repl(ctx, repl, arguments):
    '''Start an interactive Read-Eval-Print Loop (REPL), e.g. bash, rails console, etc.'''
    ctx.invoke(each, interactive=True, command=repl, arguments=arguments)


@cli.command(context_settings=dict(ignore_unknown_options=True))
@click.option('-s', '--shell', default='/bin/sh', show_default=True,
              help='alternate shell used for remote execution')
@click.option('-i', '--interactive', is_flag=True,
              help='require interactive session '
                   '(works with REPLs like shells or other command instances needing input)')
@click.option('-a', '--async', is_flag=True,
              help='run commands asynchronously (incompatible with "interactive")')
@click.option('-p', '--prefix', is_flag=True,
              help='add a prefix to all output indicating the pod and container names '
                   '(incompatible with "interactive")')
@click.argument('command')
@click.argument('arguments', nargs=-1, type=click.UNPROCESSED)
@click.pass_obj
def each(obj, shell, interactive, async, prefix, command, arguments):
    '''Execute a command remotely for each pod matched.'''

    kubectl = obj.kubey.kubectl
    kexec_args = ['exec']
    if interactive:
        kexec_args.append('-ti')
        # FIXME: when https://github.com/docker/docker/issues/8755 is fixed, remove env/term?
        #        for now, this allows for "fancy" terminal apps run in interactive mode
        arguments = ('TERM=xterm', command) + arguments
        command = 'env'

    remote_args = [command] + [quote(a) for a in arguments]
    # TODO: consider using "sh -c exec ..." only if command has no semicolon?
    remote_cmd = [shell, '-c', ' '.join(remote_args)]

    # TODO: add option to include 'node' name in prefix
    columns = ['namespace', 'node', 'name', 'containers']
    for (namespace, node_name, pod_name, containers) in obj.kubey.each(columns):
        for container in containers:
            if not container.ready:
                _logger.warn('skipping ' + str(container))
                continue
            args = kexec_args + ['-n', namespace, '-c', container.name, pod_name, '--'] + remote_cmd
            if prefix:
                args.insert(0, '[%s/%s] ' % (pod_name, container.name))
                kubectl.call_prefix(*args)
            else:
                kubectl.call_async(*args)
            if not async:
                kubectl.wait()

    if async:
        kubectl.wait()
    if kubectl.final_rc != 0:
        click.get_current_context().exit(kubectl.final_rc)


@cli.command(context_settings=dict(ignore_unknown_options=True))
@click.argument('command')
@click.argument('arguments', nargs=-1, type=click.UNPROCESSED)
@click.pass_obj
def each_pod(obj, command, arguments):
    '''Invoke a command for each pod matched.'''
    width, height = click.get_terminal_size()
    kubectl = obj.kubey.kubectl
    collector = RowCollector()
    for (namespace, pod_name) in obj.kubey.each(['namespace', 'name']):
        args = ('-n', namespace) + arguments + (pod_name,)
        kubectl.call_table_rows(collector.handler_for(namespace), command, *args)
    kubectl.wait()
    if collector.rows:
        click.echo(tabulate(sorted(collector.rows), headers=collector.headers,
                            tablefmt=obj.table_format))
    if kubectl.final_rc != 0:
        click.get_current_context().exit(kubectl.final_rc)


class RowCollector(object):
    def __init__(self):
        self.headers = None
        self.rows = []

    def handler_for(self, namespace):
        def add(i, row):
            if i == 1:
                if not self.headers:
                    self.headers = ['NAMESPACE'] + row
                return
            self.rows.append([namespace] + row)
        return add


@cli.command()
@click.option('-f', '--follow', is_flag=True,
              help='stream new logs until interrupted')
@click.option('-p', '--prefix', is_flag=True,
              help='add a prefix to all output indicating the pod and container names')
@click.argument('number', default='10')
@click.pass_obj
def tail(obj, follow, prefix, number):
    '''Show recent logs from containers for each pod matched.

    NUMBER is a count of recent lines or a relative duration (e.g. 5s, 2m, 3h)
    '''

    kubectl = obj.kubey.kubectl

    if re.match(r'^\d+$', number):
        log_args = ['--tail', str(number)]
    else:
        log_args = ['--since', number]

    if follow:
        log_args.append('-f')

    for (namespace, pod_name, containers) in obj.kubey.each():
        for container in containers:
            args = ['-n', namespace, '-c', container.name] + log_args + [pod_name]
            if prefix:
                prefix = '[%s:%s] ' % (pod_name, container.name)
                kubectl.call_prefix(prefix, 'logs', *args)
            else:
                kubectl.call_async('logs', *args)

    kubectl.wait()
    if kubectl.final_rc != 0:
        click.get_current_context().exit(kubectl.final_rc)


@cli.command()
@click.option('-c', '--columns', default='', help='specify specific columns to show')
@click.option('-f', '--flat', is_flag=True, help='flatten columns with multiple items')
@click.pass_obj
def health(obj, columns, flat):
    '''Show health stats about matches.'''

    # TODO: split this giant up!! use generators/enumerators!!

    columns = [c.strip() for c in columns.split(',')]
    flattener = flatten if flat else None

    addresses = {}
    conditions = {}
    pods_selected = {}

    for (node_name, addrs, conds, pods) in \
            obj.kubey.each_node('name', 'addresses', 'conditions', 'pods'):
        addrs = [a for a in set(addrs) if a not in node_name]
        addresses[node_name] = sorted(addrs, reverse=True)
        conditions[node_name] = conds
        pods_selected[node_name] = pods

    # TODO: color pods not in ready state! (i.e. what you'd see as red in list)
    # TODO: restriction of pods still shows everything on node:
    #       kubey collab-production 'back|sqs' . health

    kubectl = obj.kubey.kubectl

    top_node_rows = []
    kubectl.call_table_rows(lambda i, row: top_node_rows.append(row), 'top', 'node')
    kubectl.wait()

    headers = None
    selected_columns = None
    rows = []
    extra_columns = ['CONDITIONS', 'PODS', 'ADDRESSES'] if obj.wide else ['CONDITIONS']
    for row in top_node_rows:
        if headers is None:
            headers = row + extra_columns
            if columns:
                selected_columns = []
                for c in columns:
                    matches = [i for (i, h) in enumerate(headers) if c in h.lower()]
                    selected_columns.extend(matches)
            if obj.no_headers:
                headers = []
            continue
        if obj.highlight:
            mark_percentages(row, 80)
        node_name = row[0]
        if node_name in pods_selected:
            pod_names = pods_selected[node_name]
            if obj.wide:
                row.extend([conditions[node_name], pod_names, addresses[node_name]])
            else:
                row.append(conditions[node_name])
            if selected_columns:
                row = [i for i in row if row.index(i) in selected_columns]
            rows.append(row)

    rows = sorted(rows)  # FIXME: should sort as we go
    if selected_columns:
        headers = [h for h in headers if headers.index(h) in selected_columns]
    click.echo(tabulate(each_row(rows, flattener), headers=headers, tablefmt=obj.table_format))


######################################################################


_percent_re = re.compile(r'^(\d+)%$')
_skip_re = re.compile(r'^[\'"].*[\'"]$')


def mark_percentages(info, limit):
    soft_limit = limit * (limit / 100.0)
    for i, val in enumerate(info):
        m = _percent_re.match(val)
        if not m:
            continue
        v = int(m.group(1))
        if v >= limit:
            info[i] = click.style(val, bold=True, fg='red')
        elif v >= soft_limit:
            info[i] = click.style(val, fg='yellow')


def flatten(enumerable):
    return ' '.join(str(i) for i in enumerable)


def each_row(rows, flattener):
    for row in rows:
        row = list(row)  # copy row to avoid stomping on original items
        if flattener:
            for i, item in enumerate(row):
                if is_iterable(item):
                    row[i] = flattener(item)
            yield row
            continue
        # extract out a _copy_ of iterable items and populate into "exploded" rows
        iterables = {i: list(item) for i, item in enumerate(row) if is_iterable(item)}
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


# not using shlex/pipes.quote because we want glob expansion for remote calls
def quote(arg):
    if ' ' not in arg or _skip_re.match(arg):
        return arg
    if "'" in arg:
        if '"' in arg:
            raise ValueError('Unable to quote: ' + arg)
        return '"' + arg + '"'
    return "'" + arg + "'"


def is_iterable(item):
    # just simple ones for now
    return isinstance(item, list) or isinstance(item, tuple)


##########################
if __name__ == '__main__':
    cli()
