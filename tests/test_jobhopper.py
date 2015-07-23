#!/usr/bin/env python
"""Tests for the aurora redirector thingie"""

import re
import unittest
from jobhopper import jobhopper


class RegexTests(unittest.TestCase):
    """Main"""

    def setUp(self):
        self.job_re = re.compile(
            jobhopper.JOB_RE % {'subdomain': 'aurora',
                                'domainname': 'example.com'})

    def checkmatch(self, hoststr, expected):
        match = self.job_re.match(hoststr)
        self.assertIsNotNone(match)
        self.assertSequenceEqual(match.groups(), expected)

    def testTheFancyRegex(self):
        self.checkmatch('0.job.env.role.us-east-1.aurora.example.com',
                        ('0', 'job', 'env', 'role', 'us-east-1'))
        self.checkmatch('job.env.role.us-west-2.aurora.example.com.',
                        (None, 'job', 'env', 'role', 'us-west-2'))
        self.checkmatch('job.env.role.ap-northeast-1.aurora',
                        (None, 'job', 'env', 'role', 'ap-northeast-1'))
        self.checkmatch('job.env.role.ap-northeast-2.aurora.',
                        (None, 'job', 'env', 'role', 'ap-northeast-2'))
        self.checkmatch('east1.aurora',
                        (None, None, None, None, 'east1'))
        self.checkmatch('role.testcluster.aurora',
                        (None, None, None, 'role', 'testcluster'))
        self.checkmatch('env.role.XX.aurora.',
                        (None, None, 'env', 'role', 'XX'))
        self.checkmatch(
            'job.foo.bar.jobjob.jobfoo.env.role.my-cluster5.aurora',
            (None, 'job.foo.bar.jobjob.jobfoo', 'env', 'role', 'my-cluster5'))
        self.checkmatch(
            '123.j-o-b001.foo.bar.jobjob.jobfoo.919.env.role.XX.aurora',
            ('123', 'j-o-b001.foo.bar.jobjob.jobfoo.919', 'env', 'role', 'XX'))


if __name__ == '__main__':
    unittest.main()
