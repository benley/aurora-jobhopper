#!/usr/bin/env python
# encoding: utf-8
"""Redirect server thingie"""

import collections
import os
import random
import re
import time
import urlparse

from twitter.common import app
from twitter.common import log
from twitter.common import http
from twitter.common.exceptions import ExceptionalThread
from twitter.common.http.diagnostics import DiagnosticsEndpoints
from twitter.common.zookeeper import kazoo_client
from twitter.common.zookeeper.serverset import serverset

from jobhopper import clusters


JOB_RE = r"""
         (?xi) ^
         (?:(?:(?:(?:(?P<instance> \d+          )\.)?
                  (?P<job>         \w[\w.-]*    )\.)?
               (?:(?P<environment> [\w-]+       )\.))?
                  (?P<role>        [\w-]+       )\.)?
                  (?P<cluster>     [\w-]+       )
         \.%(subdomain)s
         (?:\.%(domainname)s)?\.?$
         """
"""Regex used to parse http request hostnames."""


AuroraTask = collections.namedtuple(
    'AuroraJob', ['instance', 'job', 'environment', 'role', 'cluster'])

CLUSTERS = clusters.CLUSTERS


class RedirServer(http.HttpServer, DiagnosticsEndpoints):
    """Aurora job hostname redirect service."""

    def __init__(self, zk_basepath, subdomain, base_domain):
        # Mapping of zookeeper URIs to matching TwitterKazooClient
        self.zk_connections = {}
        self.zk_basepath = zk_basepath

        self.job_re = re.compile(JOB_RE % {'subdomain': subdomain,
                                           'domainname': base_domain})

        DiagnosticsEndpoints.__init__(self)
        http.HttpServer.__init__(self)

    def parse_hostname(self, hostname):
        jmatch = self.job_re.match(hostname)
        if not jmatch:
            return None
        # (instance, job, env, role, cluster)
        return AuroraTask(**jmatch.groupdict())

    @http.route('/<:re:.*>', method='ANY')
    def handle_root(self):
        """Handle all http requests."""
        req_hostname = self.request.urlparts.hostname
        log.info('%s: %s', self.request.method, self.request.url)
        try:
            task = self.parse_hostname(req_hostname)
            if None in (task.role, task.environment, task.job):
                self.scheduler_redir(task)
            self.task_redir(task)
        except (TypeError, ValueError):
            self.abort(404, r"¯\(°_o)/¯")

    def scheduler_redir(self, task):
        """Redirect to the scheduler."""
        scheduler_url = self.get_scheduler_url(task.cluster)

        if task.role is None:
            job_url = '/scheduler'
        elif task.environment is None:
            job_url = '/scheduler/%s' % task.role
        else:
            job_url = '/scheduler/%s/%s' % (task.role, task.environment)

        url = urlparse.urljoin(scheduler_url, job_url)
        log.info('Scheduler redirect: %s', url)
        self.redirect(url)

    def get_scheduler_url(self, clustername):
        """Imitate AuroraClientAPI.scheduler_proxy.scheduler_client.url"""
        cluster = CLUSTERS.get(clustername)

        if 'proxy_url' in cluster:
            return cluster['proxy_url']
        if 'zk' in cluster and 'scheduler_zk_path' in cluster:
            zkclient = self.get_zk(clustername)
            sset = serverset.ServerSet(zkclient, cluster['scheduler_zk_path'])
            instance = list(sset)[0]
            endpoint = instance.additional_endpoints.get(
                'http', instance.service_endpoint)
            return 'http://%s' % endpoint
        if 'scheduler_uri' in cluster:
            return cluster['scheduler_uri']
        raise RuntimeError('Failed to find scheduler for %s' % clustername)

    def get_zk(self, clustername):
        """Return a TwitterKazooClient connection for the given cluster."""
        cluster = CLUSTERS.get(clustername)
        zk_url = "%s:%s" % (cluster.get('zk_discovery' if 'zk_discovery' in cluster else 'zk'),
                            cluster.get('zk_port', 2181))

        if clustername not in self.zk_connections:
            self.zk_connections[zk_url] = kazoo_client.TwitterKazooClient(
                zk_url)

        zkclient = self.zk_connections.get(zk_url)

        if not zkclient.connected:
            zkclient.start()

        return zkclient

    def resolve_task(self, task):
        """Resolve a job/task to a list of serverset instances."""
        zkclient = self.get_zk(task.cluster)
        zkpath = os.path.join(self.zk_basepath, task.role, task.environment,
                              task.job)
        sset = serverset.ServerSet(zkclient, zkpath)

        if task.instance is None:
            return list(sset)
        else:
            for ss_instance in sset:
                if ss_instance.shard == int(task.instance):
                    return [ss_instance]

    def task_redir(self, task):
        """Redirect to a running task instance."""
        def pickandgo(ins):
            """Pick an endpoint, serve a redirect.

            Use the http endpoint if there is one.
            Otherwise use the default service endpoint.
            """
            endpt = ins.additional_endpoints.get('http', ins.service_endpoint)
            url = urlparse.urlunsplit(
                self.request.urlparts._replace(netloc=str(endpt)))
            log.info('Job redirect: %s', url)
            self.redirect(url)

        # TODO: persist serverset connections (maybe for 30 seconds?) with
        # on_join/on_leave callbacks to keep a local cache of sorts and reduce
        # zookeeper load.
        instances = self.resolve_task(task)

        if not instances:
            self.abort(404, "Job not found.")
        else:
            pickandgo(random.choice(instances))


def wait_forever():
    while True:
        time.sleep(60)


def run():
    def main(args, opts):
        """Main"""
        server = RedirServer(opts.zk_basepath,
                             opts.subdomain,
                             opts.base_domain)
        thread = ExceptionalThread(
            target=lambda: server.run(opts.listen,
                                      opts.port,
                                      server='cherrypy'))
        thread.daemon = True
        thread.start()

        wait_forever()

    log.LogOptions.set_stderr_log_level('google:INFO')

    app.add_option('--port', help='http port', default=8080)
    app.add_option('--listen',
                   help='IP address to listen for http connections.',
                   default='0.0.0.0')
    app.add_option('--zk_basepath',
                   help='Zookeeper service path root.',
                   default='/aurora')
    app.add_option('--base_domain',
                   help='Domain name of your site.',
                   default='example.com')
    app.add_option('--subdomain',
                   help='Subdomain that roots Aurora job namespace.',
                   default='aurora')

    app.main()


if __name__ == '__main__':
    run()
