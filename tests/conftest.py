"""
pytest configuration.

Sets the environment variables that thermal_image_processing.py reads at
module-import time, so the module can be imported in a test context without
a real database, GeoServer, or .env file.
"""
import os

# These must be set BEFORE any project module is imported (pytest loads this
# file before collecting any test modules).
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "tipapp.settings")
os.environ.setdefault("SECRET_KEY", "test-secret-key-not-for-production")
os.environ.setdefault("general_districts_dataset_name", "dummy.gpkg")
