===============================
Kubey
===============================


.. image:: https://img.shields.io/pypi/v/kubey.svg
        :target: https://pypi.python.org/pypi/kubey

.. image:: https://img.shields.io/travis/bradrf/kubey.svg
        :target: https://travis-ci.org/bradrf/kubey

.. image:: https://readthedocs.org/projects/kubey/badge/?version=latest
        :target: https://kubey.readthedocs.io/en/latest/?badge=latest
        :alt: Documentation Status


Kubey is a tool that simplifies node, pod, and container selection when interacting with a
Kubernetes cluster.

* Free software: MIT license
* Documentation: https://kubey.readthedocs.io.

Features
--------

**SELECTION**

To select interesting items from a Kubernetes cluster, Kubey support regular expression matches
against namespaces, node names, pod names, and container names. For example, the following would
list all items currently in the ``kube-system`` namespace:

.. code-block:: console

    $ kubey -n kube-system .

To reduce the set to get info on only pods whose name contains ``proxy``:

.. code-block:: console

    $ kubey -n kube-system proxy

By default, Kubey matches pod names. Further restrictions can be requested to show only items
matching a particular node or a container using slashes to separate the expressions based on this
model: ``[<NODE>/]<POD>[/<CONTAINER>]``. For example, the following will show all items in any
namespace but running only on one node:

.. code-block:: console

    $ kubey -n . my-special-node//

More help about selection is available in ``kubey --help`` usage information.

**REMOTE EXECUTION**

Often it's useful to inspect running containers when tracking down problems. Kubey makes it trivial
to run commands on selected containers with one request locally that is multiplexed out to many
remote executions, either serially or concurrently. For example, this would asynchronously report
the hostname of all containers found associated with the ``my-special-pod`` pod names, prefixing all
standard output with the pod and container names (using the ``--async`` and ``--prefix`` options):

.. code-block:: console

    $ kubey my-special-pod each -ap hostname

**INTERACTIVE SHELL**

Kubey can also provide access to any remote "Read-Evaluate-Print Loop" (REPL) shell on matching
containers (e.g. ``bash``, ``rails``, etc.). In the following case, use of the ``--max`` option is
employed to limit the match to the first container:

.. code-block:: console

     $ kubey -m1 my-special-pod repl bash

**TAILING LOGS**

When monitoring for issues, all the selected container logs can be shown simultaneously:

.. code-block:: console

     $ kubey ./my-special-container tail -f

**SHOW EVENTS**

To start watching all active events in the system (will continuously monitor for new events):

.. code-block:: console

     $ kubey -n . . events

**REPORTING NODE HEALTH**

Kubey can show node-level health restricted to only items selected. For example, the following will
show a node health report for all nodes that are currently running a particular pod, detailing
important items like CPU and memory usage along with other conditions:

.. code-block:: console

     $ kubey my-special-pod health

**WEBUI LINK**

To show links to selected items in the Kubernetes WebUI:

.. code-block:: console

     $ kubey my-special-pod webui

Credits
---------

This package was created with Cookiecutter_ and the `audreyr/cookiecutter-pypackage`_ project template.

.. _Cookiecutter: https://github.com/audreyr/cookiecutter
.. _`audreyr/cookiecutter-pypackage`: https://github.com/audreyr/cookiecutter-pypackage
