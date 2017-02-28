====================
Jobhopper for Aurora
====================

Jobhopper is a simple http redirector daemon designed to make it easy and
convenient for developers and administrators to navigate directly to any
running Aurora job on your Mesos cluster from your browser's address bar.

Run jobhopper on your Aurora schedulers, or any other static serving host.
Add a wildcard CNAME record to DNS which points \*.aurora.yourcompany.com to
the machine(s) running jobhopper. (you can use any subdomain, it doesn't have
to be called "aurora")

Launch the daemon:

.. code:: sh

    jobhopper --port=80 \
              --zk=your.zookeeper.ensemble:2181 \
              --zk_basepath=/aurora/svc \
              --scheduler_url=https://your.aurora.scheduler/scheduler \
              --base_domain=example.com \
              --subdomain=aurora

At that point, you can use nifty URLs in your browser.

For example, to hop directly to task #0 of a job called `foojob` in the
environment `devel` running as role `produser` on the aurora cluster `east1`:

http://0.foojob.devel.produser.east1.aurora.example.com/

If you set up your DNS search path to include the base domain, you can shorten
that to:

http://0.foojob.devel.produser.east1.aurora/

Jobhopper will also do useful things with fewer parts of a job name.

http://foojob.devel.produser.east1.aurora/ will hop to *a random task number*
of east1/produser/devel/foojob on your cluster.

If you leave off the job name entirely, Jobhopper will send you to the
approprate Aurora scheduler info page.

http://devel.produser.east1.aurora/ will take you to
http://your.aurora.scheduler/scheduler/east1/produser/devel

http://produser.east1.aurora/ will take you to the scheduler page for produser.

http://east1.aurora/ will take you to the top-level scheduler status page for
the east1 aurora cluster.

This app is not intended to be used for serving production traffic!
For that, you should consider tools like aurproxy_, synapse_, envoy_, and linkerd_.

.. _Synapse: https://github.com/benley/synapse
.. _aurproxy: https://github.com/tellapart/aurproxy
.. _envoy: https://github.com/lyft/envoy
.. _linkerd: https://github.com/linkerd/linkerd
