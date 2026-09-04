"""
__init__.py — makes backend a proper package.
"""

import os

# Prevent Windows SSLKEYLOGFILE permission errors in httpx/ssl
os.environ.pop("SSLKEYLOGFILE", None)

