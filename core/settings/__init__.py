# core/settings/__init__.py
from .base import *
import os

from dotenv import load_dotenv

load_dotenv()

# Environment
ENVIRONMENT = os.environ.get('DJANGO_ENVIRONMENT', 'dev')
print(ENVIRONMENT)

if ENVIRONMENT == 'production':
    from .prod import *
else:
    from .dev import *