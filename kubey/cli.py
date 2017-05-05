import os
import sys
import logging
import re
import signal
import click

from configstruct import OpenStruct
from collections import defaultdict

from . import tabular

from .kubey import Kubey
from .event import Event
from .node import Node
from .pod import Pod


class ColumnsOption(click.ParamType):
    name = 'columns'
    envvar_list_splitter = ','

    def __init__(self, cls):
        self._cls = cls
        self.default = self._join(self._cls.PRIMARY_ATTRIBUTES)
        self.help = 'specify one or more of ALL,{0}  [default: {1}]'.format(
            self._join(self._cls.ATTRIBUTES), self.default)

    def convert(self, value, param, ctx):
        if value == 'ALL':
            return self._cls.ATTRIBUTES
        columns = self.split_envvar_value(value)
        if 'DEF' in columns:
            i = columns.index('DEF')
            del(columns[i])
            for c in reversed(self._cls.PRIMARY_ATTRIBUTES):
                columns.insert(i, c)
        unknown = set(columns) - (set(columns) & set(self._cls.ATTRIBUTES))
        if len(unknown) > 0:
            self.fail('unknown columns: ' + ','.join(unknown))
        return columns

    def _join(self, attrs):
        return self.envvar_list_splitter.join(attrs)


_logger = None
_event_columns = ColumnsOption(Event)
_node_columns = ColumnsOption(Node)
_pod_columns = ColumnsOption(Pod)


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
              type=click.Choice(tabular.formats), default='simple',
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

    highlight = sys.stdout.isatty()

    def highlight_with(color):
        if not highlight:
            return str

        def colorizer(obj):
            return click.style(str(obj), bold=True, fg=color)
        return colorizer

    hard_percent_limit = 80     # TODO: consider making cfg'abl
    soft_percent_limit = hard_percent_limit * (hard_percent_limit / 100.0)

    ctx.obj = OpenStruct(
        highlight_ok=highlight_with('green'),
        highlight_warn=highlight_with('yellow'),
        highlight_error=highlight_with('red'),
        hard_percent_limit=hard_percent_limit,
        soft_percent_limit=soft_percent_limit,
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


@cli.command()
@click.option('-c', '--columns', type=_node_columns, default=_node_columns.default,
              help=_node_columns.help)
@click.option('-f', '--flat', is_flag=True, help='flatten columns with multiple items')
@click.pass_obj
def health(obj, columns, flat):
    '''Show health stats about matches.'''
    click.echo(tabular.tabulate(obj, obj.kubey.each_node(obj.maximum, True), columns, flat))


# FIXME: if --wide use all attributes, not default
@cli.command(name='list')
@click.option('-c', '--columns', type=_pod_columns, default=_pod_columns.default,
              help=_pod_columns.help)
@click.option('-f', '--flat', is_flag=True, help='flatten columns with multiple items')
@click.pass_obj
def list_pods(obj, columns, flat):
    '''List available pods and containers for current context.'''
    # FIXME: find a "click" way to ask if columns were provided or defaults used
    if obj.namespace == Kubey.ANY and '-c' not in sys.argv and '--columns' not in sys.argv:
        columns = ['namespace'] + columns
    click.echo(tabular.tabulate(obj, obj.kubey.each_pod(obj.maximum), columns, flat))


@cli.command()
@click.pass_obj
def webui(obj):
    '''List dashboard links for matching pods (if only one matched, URL is opened in browser).'''
    kubectl = obj.kubey.kubectl
    info = click.unstyle(kubectl.call_capture('cluster-info'))
    dash_endpoint = re.search(r'kubernetes-dashboard.*?(http\S+)', info).group(1)
    urls = []
    for pod in obj.kubey.each_pod(obj.maximum):
        pod_path = '/#/pod/{0}/{1}?namespace={0}'.format(pod.namespace, pod.name)
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
    for pod in obj.kubey.each_pod(obj.maximum):
        for container in pod.containers:
            if not container.ready:
                _logger.warn('skipping ' + str(container))
                continue
            args = kexec_args + \
                ['-n', pod.namespace, '-c', container.name, pod.name, '--'] + \
                remote_cmd
            if prefix:
                args.insert(0, '[%s/%s] ' % (pod.name, container.name))
                kubectl.call_prefix(*args)
            else:
                kubectl.call_async(*args)
            if not async:
                kubectl.wait()

    if async:
        kubectl.wait()
    if kubectl.final_rc != 0:
        click.get_current_context().exit(kubectl.final_rc)


@cli.command(name='ctl-each', context_settings=dict(ignore_unknown_options=True))
@click.argument('command')
@click.argument('arguments', nargs=-1, type=click.UNPROCESSED)
@click.pass_obj
def ctl_each(obj, command, arguments):
    '''Invoke any kubectl command directly for each pod matched and collate the output.'''
    width, height = click.get_terminal_size()
    kubectl = obj.kubey.kubectl
    collector = tabular.RowCollector()
    ns_pods = defaultdict(list)
    for pod in obj.kubey.each_pod(obj.maximum):
        ns_pods[pod.namespace].append(pod)
    for ns, pods in ns_pods.items():
        args = ['-n', ns] + list(arguments) + [p.name for p in pods]
        kubectl.call_table_rows(collector.handler_for(ns), command, *args)
    kubectl.wait()
    if collector.rows:
        click.echo(tabular.tabulate(obj, sorted(collector.rows), collector.headers))
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

    kubectl = obj.kubey.kubectl

    if re.match(r'^\d+$', number):
        log_args = ['--tail', str(number)]
    else:
        log_args = ['--since', number]

    if follow:
        log_args.append('-f')

    for pod in obj.kubey.each_pod(obj.maximum):
        for container in pod.containers:
            args = ['-n', pod.namespace, '-c', container.name] + log_args + [pod.name]
            if prefix:
                prefix = '[%s:%s] ' % (pod.name, container.name)
                kubectl.call_prefix(prefix, 'logs', *args)
            else:
                kubectl.call_async('logs', *args)

    kubectl.wait()
    if kubectl.final_rc != 0:
        click.get_current_context().exit(kubectl.final_rc)


@cli.command()
@click.option('-c', '--columns', type=_event_columns, default=_event_columns.default,
              help=_event_columns.help)
@click.pass_obj
def events(obj, columns):
    '''Show events associated with matched nodes, pods, and/or containers.'''
    if obj.namespace == Kubey.ANY and '-c' not in sys.argv and '--columns' not in sys.argv:
        columns = ['namespace'] + columns
    for line in tabular.lines(obj, obj.kubey.each_event(obj.maximum), columns):
        click.echo(line)


# not using shlex/pipes.quote because we want glob expansion for remote calls
def quote(arg):
    if ' ' not in arg or re.match(r'^[\'"].*[\'"]$', arg):
        return arg
    if "'" in arg:
        if '"' in arg:
            raise ValueError('Unable to quote: ' + arg)
        return '"' + arg + '"'
    return "'" + arg + "'"


##########################
if __name__ == '__main__':
    cli()
