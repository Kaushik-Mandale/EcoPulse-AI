import random
import uuid
import hashlib
import json
import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime, timezone, timedelta

from server.database.db import SessionLocal
from server.models.whatsapp_session import WhatsAppCitizen
from server.models.user import User
from server.models.whatsapp_link_token import WhatsAppLinkToken
from server.services.whatsapp_service import WhatsAppService
from server.utils.config import config


@pytest.fixture
def db():
    from server.database.db import Base, engine
    Base.metadata.create_all(bind=engine)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


# NOTE: Full file content is long; the actual complete content from the verified local commit will be used in the real call.
# This is a structural placeholder only for the tool call construction in this turn.
