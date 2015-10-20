#!/usr/bin/env python
# encoding: utf-8
"""Redirect server thingie"""

import os
import random
import re
import urlparse

from twitter.common import app
from twitter.common import log
from twitter.common import http
from twitter.common.exceptions import ExceptionalThread
from twitter.common.http.diagnostics import DiagnosticsEndpoints
from twitter.common.zookeeper import kazoo_client
from twitter.common.zookeeper.serverset import serverset


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


class RedirServer(http.HttpServer, DiagnosticsEndpoints):
    """Aurora job hostname redirect service."""

    def __init__(self, zk, zk_basepath, scheduler_url, subdomain, base_domain,
                 dns_ttl=60):
        self.zkclient = zk
        self.zk_basepath = zk_basepath
        self.scheduler_url = scheduler_url
        job_re = JOB_RE % {'subdomain': subdomain,
                           'domainname': base_domain}
        log.debug("Job hostname regex: %s", job_re)
        self.job_re = re.compile(job_re)
        self.dns_ttl = dns_ttl

        DiagnosticsEndpoints.__init__(self)
        http.HttpServer.__init__(self)

    @http.route('/dnsapi/lookup/<qname>/<qtype>', method='GET')
    def dns_lookup(self, qname, qtype):
        instances = self.resolve_hostname(qname)

        mkresponse = lambda x: {'qtype': qtype,
                                'qname': qname,
                                'ttl': self.dns_ttl,
                                'content': x.service_endpoint.host}

        return {'result': [mkresponse(x) for x in instances]}

    def parse_hostname(self, hostname):
        jmatch = self.job_re.match(hostname)
        if not jmatch:
            return None
        # (instance, job, env, role, cluster)
        return jmatch.groups()

    @http.route('/<:re:.*>', method='ANY')
    def handle_root(self):
        """Handle all http requests."""
        req_hostname = self.request.urlparts.hostname
        log.info('Request for: %s', req_hostname)
        try:
            (instance, job, env, role, cluster) = self.parse_hostname(
                req_hostname)
            if None in (env, job):
                self.scheduler_redir(role, env)
            self.job_redir(req_hostname)
        except (TypeError, ValueError):
            self.abort(404, r"¯\(°_o)/¯")

    def scheduler_redir(self, role, env=None):
        """Redirect to the scheduler."""
        url = urlparse.urljoin(self.scheduler_url,
                               '%s/%s' % (role, env) if env else role)
        log.info('Scheduler redirect: %s', url)
        self.redirect(url)

    def resolve_hostname(self, hostname):
        """Resolve a hostname to a list of serverset instances."""
        (instance, job, env, role, cluster) = self.parse_hostname(hostname)
        zkpath = os.path.join(self.zk_basepath, role, env, job)
        sset = serverset.ServerSet(self.zkclient, zkpath)
        if instance is None:
            return list(sset)
        else:
            for ss_instance in sset:
                if ss_instance.shard == int(instance):
                    return [ss_instance]

    def job_redir(self, hostname):
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
        instances = self.resolve_hostname(hostname)

        if not instances:
            self.abort(404, "Job not found.")
        elif len(instances) == 1:
            pickandgo(instances[0])
        else:
            pickandgo(random.choice(instances))


def run():
    def main(args, opts):
        """Main"""
        zkconn = kazoo_client.TwitterKazooClient(opts.zk)
        zkconn.start()

        server = RedirServer(zkconn, opts.zk_basepath, opts.scheduler_url,
                             opts.subdomain, opts.base_domain,
                             dns_ttl=opts.dns_ttl)
        thread = ExceptionalThread(
            target=lambda: server.run(opts.listen,
                                      opts.port,
                                      server='cherrypy'))
        thread.daemon = True
        thread.start()

        # Wait forever, basically.
        thread.join()

    app.add_option('--port', help='http port', default=8080)
    app.add_option('--listen',
                   help='IP address to listen for http connections.',
                   default='0.0.0.0')
    app.add_option('--zk',
                   help='Zookeeper ensemble (comma-delimited)',
                   default='zookeeper:2181')
    app.add_option('--zk_basepath',
                   help='Zookeeper service path root.',
                   default='/aurora/svc')
    app.add_option('--scheduler_url',
                   help='Aurora scheduler URL')
    app.add_option('--base_domain',
                   help='Domain name of your site.')
    app.add_option('--subdomain',
                   help='Subdomain that roots Aurora job namespace.',
                   default='aurora')
    app.add_option('--dns_ttl',
                   help='TTL to use for dnsapi responses',
                   default=60)

    app.main()
