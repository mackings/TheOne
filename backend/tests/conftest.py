import os
import tempfile

import pytest
from cryptography.fernet import Fernet

_tmp = tempfile.mkdtemp()
os.environ["EMBEDDER_BACKEND"] = "fake"
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp}/test.db"
os.environ["TEMPLATE_ENCRYPTION_KEY"] = Fernet.generate_key().decode()

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

@pytest.fixture(scope="session")
def client():
    with TestClient(app) as c:
        yield c
