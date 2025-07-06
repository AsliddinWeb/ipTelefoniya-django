# core/settings/__init__.py
from .base import *
import os

# Environment
ENVIRONMENT = os.getenv('DJANGO_ENVIRONMENT', 'dev')

if ENVIRONMENT == 'production':
    from .prod import *
else:
    from .dev import *