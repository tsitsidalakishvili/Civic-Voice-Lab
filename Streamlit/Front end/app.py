"""Compatibility entrypoint for Streamlit Cloud.

The app has been migrated to Home.py + pages/, but some deployments
still use `app.py` as the configured main module.
"""

from Home import *  # noqa: F401,F403

