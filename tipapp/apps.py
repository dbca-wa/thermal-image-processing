"""
Thermal Image Processing Application Configuration
"""

from django.apps import AppConfig


class TipappConfig(AppConfig):
    """
    Configuration for the Thermal Image Processing application.
    """
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'tipapp'
    verbose_name = 'Thermal Image Processing'
