#!/usr/bin/env python
# encoding: utf-8
"""Redirect server thingie"""

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


def dnsresponse(data):
    """Construct a response for the PowerDNS remote backend.

    Remote api docs:
        https://doc.powerdns.com/md/authoritative/backend-remote/
    """
    resp = {'result': data}
    log.info('DNS response: %s', resp)
    return resp


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
        self.soa_zone = '.'.join([subdomain, base_domain])

        DiagnosticsEndpoints.__init__(self)
        http.HttpServer.__init__(self)

    @http.route('/dnsapi/lookup/<qname>/<qtype>', method='GET')
    def dns_lookup(self, qname, qtype):
        log.info('%s: %s', self.request.method, self.request.url)

        a_response = lambda x: {
            'qtype': 'A',
            'qname': qname,
            'ttl': self.dns_ttl,
            'content': x.service_endpoint.host
            }
        soa_response = lambda: {
            'qtype': 'SOA',
            'qname': self.soa_zone,
            'ttl': self.dns_ttl,
            'content': 'ns1.%(zone)s root.%(zone)s 1 3600 600 8400 1' % {
                'zone': self.soa_zone,
                }
            }

        if qtype in ['A', 'ANY']:
            instances = self.resolve_hostname(qname)
            return dnsresponse([a_response(x) for x in instances] or False)

        elif qtype == 'SOA' and qname.lower().endswith(self.soa_zone):
            return dnsresponse([soa_response()])

        else:
            return dnsresponse(False)

    @http.route('/dnsapi/getDomainMetadata/<qname>/<qkind>', method='GET')
    def dns_getdomainmetadata(self, qname, qkind):
        if qkind == 'SOA-EDIT':
            # http://jpmens.net/2013/01/18/understanding-powerdns-soa-edit/
            return dnsresponse(['EPOCH'])
        else:
            return dnsresponse(False)

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
        log.info('%s: %s', self.request.method, self.request.url)
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
        try:
            (instance, job, env, role, cluster) = self.parse_hostname(hostname)
        except TypeError:
            return []
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


def wait_forever():
    while True:
        time.sleep(60)


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

        wait_forever()

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


if __name__ == '__main__':
    run()
