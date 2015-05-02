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
        self.checkmatch('0.job.env.role.xx.aurora.example.com',
                        ('0', 'job', 'env', 'role', 'xx'))
        self.checkmatch('job.env.role.xx.aurora.example.com.',
                        (None, 'job', 'env', 'role', 'xx'))
        self.checkmatch('job.env.role.xx.aurora',
                        (None, 'job', 'env', 'role', 'xx'))
        self.checkmatch('job.env.role.xx.aurora.',
                        (None, 'job', 'env', 'role', 'xx'))
        self.checkmatch('role.xx.aurora',
                        (None, None, None, 'role', 'xx'))
        self.checkmatch('env.role.XX.aurora.',
                        (None, None, 'env', 'role', 'XX'))
        self.checkmatch(
            'job.foo.bar.jobjob.jobfoo.env.role.XX.aurora',
            (None, 'job.foo.bar.jobjob.jobfoo', 'env', 'role', 'XX'))
        self.checkmatch(
            '123.j-o-b001.foo.bar.jobjob.jobfoo.919.env.role.XX.aurora',
            ('123', 'j-o-b001.foo.bar.jobjob.jobfoo.919', 'env', 'role', 'XX'))


if __name__ == '__main__':
    unittest.main()
