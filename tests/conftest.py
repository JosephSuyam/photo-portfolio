import pytest

from tests.fixtures.fake_drive import FakeDriveClient


@pytest.fixture
def fake_drive() -> FakeDriveClient:
    return FakeDriveClient()
