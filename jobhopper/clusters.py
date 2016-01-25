#!/usr/bin/env python
"""Find and handle aurora clusters.json"""

import json
import os

DEFAULT_SEARCH_PATHS = (
    os.environ.get('AURORA_CONFIG_ROOT') or '/etc/aurora',
    os.path.expanduser('~/.aurora')
)


CLUSTERS = {}


def load():
    for search_path in DEFAULT_SEARCH_PATHS:
        filename = os.path.join(search_path, 'clusters.json')
        if os.path.exists(filename):
            with open(filename) as jsonfh:
                data = json.load(jsonfh)

                for cluster in data:
                    cname = cluster['name']
                    if cname in CLUSTERS:
                        CLUSTERS[cname].update(cluster)
                    else:
                        CLUSTERS[cname] = cluster


load()
