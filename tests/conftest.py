"""Test setup: let Home Assistant load the integration from custom_components/."""
import pytest


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Needed for pytest-homeassistant-custom-component to find custom_components/."""
    yield
