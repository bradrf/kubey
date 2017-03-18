import os
import sys
import logging
import re
import pipes
import click
import jmespath

from collections import defaultdict
from tabulate import tabulate, tabulate_formats
from configstruct import OpenStruct

from .kubectl import KubeCtl
from .cache import Cache
from .container import Container
from .node_condition import NodeCondition


ANY_NAMESPACE = '.'

COLUMN_MAP = {
    'name': 'metadata.name',
    'namespace': 'metadata.namespace',
    'node': 'spec.nodeName',
    'node-ip': 'status.hostIP',
    'status': 'status.phase',
    # 'conditions': 'status.conditions[*].[type,status,message]',
    'containers': 'status.containerStatuses[*].[name,ready,state,image]',
}

logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s #%(process)d] %(levelname)-8s %(name)-12s %(message)s',
    datefmt='%Y-%m-%dT%H:%M:%S%z'
)
_logger = logging.getLogger(__name__)


@click.group(invoke_without_command=True, context_settings=dict(help_option_names=['-h', '--help']))
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
@click.option('--no-headers', is_flag=True, help='disable table headers')
@click.option('--limit', type=int, help='limit number of matches')
@click.argument('match')
@click.pass_context
def cli(ctx, cache_seconds, log_level, context, namespace, table_format, no_headers, limit, match):
    '''Simple wrapper to help find specific Kubernetes pods and containers and run asynchronous
    commands (default is to list those that matched).

    \b
    MATCH       <POD>[/<CONTAINER>]

    POD         provide a regular expression to select one or more pods
    CONTAINER   provide a regular expression to select one or more containers
    '''

    _logger.level = getattr(logging, log_level.upper())

    match_items = match.split('/', 1)
    pod = match_items.pop(0)
    container = match_items.pop(0) if len(match_items) > 0 else '.'

    if namespace == ANY_NAMESPACE:
        query = 'items[*]'
    else:
        query = 'items[?contains(metadata.namespace,\'%s\')]' % (namespace)

    ctx.obj = OpenStruct(
        highlight=sys.stdout.isatty(),
        cache_seconds=cache_seconds,
        table_format=table_format,
        no_headers=no_headers,
        limit=limit,
        namespace_query=query,
        pod_re=re.compile(pod, re.IGNORECASE),
        container_re=re.compile(container, re.IGNORECASE),
        kubectl=KubeCtl(context),
    )

    cache(ctx.obj, 'namespaces')
    cache(ctx.obj, 'nodes')
    cache(ctx.obj, 'pods', '--all-namespaces')

    if (namespace != ANY_NAMESPACE):
        validation_query = 'items[?contains(metadata.name,\'%s\')].status.phase' % (namespace)
        if not jmespath.search(validation_query, ctx.obj.namespaces_cache.obj()):
            ctx.fail('Namespace not found')

    if not ctx.invoked_subcommand:
        ctx.invoke(list_pods)


@cli.command(name='list')
@click.option('-c', '--columns', default=','.join(COLUMN_MAP.keys()), show_default=True,
              help='specify specific columns to show')
@click.option('-f', '--flat', is_flag=True, help='flatten columns with multiple items')
@click.pass_obj
def list_pods(obj, columns, flat):
    '''List available pods and containers for current context.'''
    # TODO: replace (extend?) node to be name instead of private ip now we have node info for health
    columns = [c.strip() for c in columns.split(',')]
    flattener = flatten if flat else None
    headers = [] if obj.no_headers else columns
    rows = each_row(each_match(obj, columns), flattener, container_index_of(columns))
    print tabulate(rows, headers=headers, tablefmt=obj.table_format)


@cli.command()
@click.pass_obj
def webui(obj):
    '''List dashboard links for matching pods. Three or fewer will be opened automatically.'''
    info = click.unstyle(obj.kubectl.call_capture('cluster-info'))
    dash_endpoint = re.search(r'kubernetes-dashboard.*?(http\S+)', info).group(1)
    urls = []
    for (namespace, pod_name, containers) in each_match(obj):
        pod_path = '/#/pod/%s/%s?namespace=%s' % (namespace, pod_name, namespace)
        urls.append(dash_endpoint + pod_path)
    if len(urls) == 1:
        url = urls[0]
        print url
        click.launch(url)
    else:
        for url in urls:
            print url


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

    kubectl = obj['kubectl']
    kexec_args = ['exec']
    if prefix:
        kexec = kubectl.call_prefix
        if interactive:
            click.get_current_context().fail('Interactive and prefix do not operate together')
    elif async:
        kexec = kubectl.call_async
        if interactive:
            click.get_current_context().fail('Interactive and async do not operate together')
    else:
        kexec = kubectl.call
        if interactive:
            kexec_args += ['-ti']
            # FIXME: when https://github.com/docker/docker/issues/8755 is fixed, remove env/term?
            #        for now, this allows for "fancy" terminal apps run in interactive mode
            arguments = ('TERM=xterm', command) + arguments
            command = 'env'

    # TODO: consider using "sh -c exec ..." only if command has no semicolon?
    remote_args = [command] + [pipes.quote(a) for a in arguments]
    remote_cmd = [shell, '-c', ' '.join(remote_args)]

    # TODO: add option to include 'node' name in prefix
    columns = ['namespace', 'node', 'name', 'containers']
    for (namespace, node_name, pod_name, containers) in each_match(obj, columns):
        for container in containers:
            if not container.ready:
                _logger.warn('skipping ' + str(container))
                continue
            args = list(kexec_args)  # copy
            if prefix:
                args.append('[%s/%s] ' % (pod_name, container.name))
            args += ['-n', namespace, '-c', container.name, pod_name, '--'] + remote_cmd
            kexec(*args)

    if async:
        kubectl.wait()

    if kubectl.final_rc != 0:
        click.get_current_context().exit(kubectl.final_rc)


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

    kubectl = obj['kubectl']

    if re.match(r'^\d+$', number):
        log_args = ['--tail', str(number)]
    else:
        log_args = ['--since', number]

    if follow:
        log_args.append('-f')

    for (namespace, pod_name, containers) in each_match(obj):
        for container in containers:
            if not container.ready:
                _logger.warn('skipping ' + str(container))
                continue
            args = ['-n', namespace, '-c', container.name] + log_args + [pod_name]
            if prefix:
                prefix = '[%s:%s] ' % (pod_name, container.name)
                kubectl.call_prefix('logs', prefix, *args)
            else:
                kubectl.call_async('logs', *args)

    kubectl.wait()
    if kubectl.final_rc != 0:
        click.get_current_context().exit(kubectl.final_rc)


# @cli.command(context_settings=dict(ignore_unknown_options=True))
# @click.argument('command')
# @click.argument('arguments', nargs=-1, type=click.UNPROCESSED)
# @click.pass_obj
# def call(obj, command, arguments):
#     '''Generic proxy for any other kubectl request'''
#     kubectl = obj['kubectl']
#     items = kubectl.call_json(command, *arguments)['items']
#     headers = [] if obj.no_headers else 'keys'
#     print tabulate(items, headers=headers, tablefmt=obj.table_format)


@cli.command()
@click.option('-c', '--columns', default='', help='specify specific columns to show')
@click.option('-f', '--flat', is_flag=True, help='flatten columns with multiple items')
@click.pass_obj
def health(obj, columns, flat):
    '''Show health stats about matches.'''

    # TODO: split this giant up!! use generators/enumerators!!

    columns = [c.strip() for c in columns.split(',')]
    flattener = flatten if flat else None

    pods_selected = defaultdict(list)
    for (node_name, pod_name) in each_pod(obj, ['node', 'name']):
        pods_selected[node_name].append(pod_name)

    query = 'items[?kind==\'Node\'].['\
            'metadata.name,status.addresses[*].address,'\
            'status.conditions[*].[type,status,message]'\
            ']'
    addresses = {}
    conditions = {}
    for (node_name, addrs, condlist) in jmespath.search(query, obj.nodes_cache.obj()):
        addrs = [a for a in set(addrs) if a not in node_name]
        addresses[node_name] = sorted(addrs, reverse=True)
        conditions[node_name] = [NodeCondition(*(c + [obj.highlight])) for c in condlist]

    headers = None
    selected_columns = None
    rows = []

    # TODO: sort this output (seems to randomly change when running over again)
    # TODO: color pods not in ready state! (i.e. what you'd see as red in list)
    # TODO: restriction of pods still shows everything on node:
    #       kubey collab-production 'back|sqs' . health

    extra_columns = ['CONDITIONS', 'PODS', 'ADDRESSES']

    for line in obj.kubectl.call_capture('top', 'node').splitlines():
        info = line.split()
        if headers is None:
            headers = info + extra_columns
            if columns:
                selected_columns = []
                for c in columns:
                    matches = [i for (i, h) in enumerate(headers) if c in h.lower()]
                    selected_columns.extend(matches)
            if obj.no_headers:
                headers = []
            continue
        node_name = info[0]
        if node_name in pods_selected:
            pod_names = pods_selected[node_name]
            info.extend([conditions[node_name], pod_names, addresses[node_name]])
            if selected_columns:
                info = [i for i in info if info.index(i) in selected_columns]
            rows.append(info)

    rows = sorted(rows)  # FIXME: should sort as we go
    if selected_columns:
        headers = [h for h in headers if headers.index(h) in selected_columns]
    enumerable_indices = [i for (i, h) in enumerate(headers) if h in extra_columns]
    print tabulate(each_row(rows, flattener, *enumerable_indices),
                   headers=headers, tablefmt=obj.table_format)


######################################################################

def cache(obj, name, *args):
    cache_fn = os.path.join(
        os.path.expanduser('~'), '.%s_%s_%s' % (__name__, obj.kubectl.context, name)
    )
    obj[name + '_cache'] = Cache(
        cache_fn, obj.cache_seconds, obj.kubectl.call_json, 'get', name, *args
    )


def flatten(enumerable):
    return ' '.join(str(i) for i in enumerable)


def container_index_of(columns):
    return columns.index('containers') if 'containers' in columns else None


def each_match(obj, columns=['namespace', 'name', 'containers']):
    container_index = container_index_of(columns)
    cols = ['name', 'containers'] + columns
    # FIXME: use set and indices map: {v: i for i, v enumerate(cols)}
    count = 0
    for pod in each_pod(obj, cols):
        (pod_name, container_info), col_values = pod[:2], pod[2:]  # FIXME: duplicating cols!
        if not obj.pod_re.match(pod_name):
            continue
        containers = []
        for (name, ready, state, image) in container_info:
            if not obj.container_re.match(name):
                continue
            containers.append(Container(name, ready, state, image, obj.highlight))
        if not containers:
            continue
        if container_index:
            col_values[container_index] = containers
        count += 1
        if obj.limit and obj.limit < count:
            _logger.debug('Prematurely stopping at match limit of ' + str(obj.limit))
            break
        yield(col_values)


def each_pod(obj, columns):
    query = obj.namespace_query + '.[' + ','.join([COLUMN_MAP[c] for c in columns]) + ']'
    pods = obj.pods_cache.obj()
    for pod in jmespath.search(query, pods):
        yield pod


def each_row(rows, flattener, *enumerable_indices):
    enumerable_indices = [i for i in enumerable_indices if i is not None]
    for row in rows:
        if not enumerable_indices:
            yield row
            continue

        if flattener:
            for i in enumerable_indices:
                row[i] = flattener(row[i])
            yield row
            continue

        enumerables = {i: row[i] for i in enumerable_indices}
        final_row = row
        while True:
            processing = False
            for index, enumerable in enumerables.iteritems():
                if not enumerable:
                    continue
                processing = True
                final_row[index] = enumerable.pop(0)
            if not processing:
                break
            yield final_row
            final_row = [''] * len(row)


##########################
if __name__ == '__main__':
    cli()
