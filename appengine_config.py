from google.appengine.ext import vendor
vendor.add('env27/Lib/site-packages')

import logging
logging.basicConfig(level=logging.DEBUG)

import os
#os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'	# env param setting in this code is ignored.

PRODUCTION_MODE = not os.environ.get('SERVER_SOFTWARE', 'Development').startswith('Development')

if not PRODUCTION_MODE:
    if os.name == 'nt':
	import sys
	os.name = None
	sys.platform = ''

from google.appengine.api import urlfetch
urlfetch.set_default_fetch_deadline(20.0)

import requests
import requests_toolbelt.adapters.appengine
requests_toolbelt.adapters.appengine.monkeypatch()


