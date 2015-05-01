#!/usr/bin/env python
"""Tests for the aurora redirector thingie"""

import re
import unittest
from jobhopper import jobhopper


class FuckingShitTest(unittest.TestCase):
    """Main"""

    def setUp(self):
        self.job_re = re.compile(
            jobhopper.JOB_RE % {'subdomain': 'aurora',
                                'domainname': 'folsomlabs.com'})

    def derp(self, hurr, expected):
        match = self.job_re.match(hurr)
        self.assertIsNotNone(match)
        self.assertSequenceEqual(match.groups(), expected)

    def testTheFuckingRegex(self):
        self.derp('0.job.env.role.xx.aurora.folsomlabs.com',
                  ('0', 'job', 'env', 'role', 'xx'))
        self.derp('job.env.role.xx.aurora.folsomlabs.com.',
                  (None, 'job', 'env', 'role', 'xx'))
        self.derp('job.env.role.xx.aurora',
                  (None, 'job', 'env', 'role', 'xx'))
        self.derp('job.env.role.xx.aurora.',
                  (None, 'job', 'env', 'role', 'xx'))
        self.derp('role.xx.aurora',
                  (None, None, None, 'role', 'xx'))
        self.derp('env.role.XX.aurora.',
                  (None, None, 'env', 'role', 'XX'))
        self.derp('job.foo.bar.jobjob.jobfoo.env.role.XX.aurora',
                  (None, 'job.foo.bar.jobjob.jobfoo', 'env', 'role', 'XX'))
        self.derp(
            '123.j-o-b001.foo.bar.jobjob.jobfoo.919.env.role.XX.aurora',
            ('123', 'j-o-b001.foo.bar.jobjob.jobfoo.919', 'env', 'role', 'XX'))


if __name__ == '__main__':
    unittest.main()
