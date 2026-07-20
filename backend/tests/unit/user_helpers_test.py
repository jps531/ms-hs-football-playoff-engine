"""Unit tests for backend.helpers.user_helpers (owner-account protection policy)."""

import pytest
from fastapi import HTTPException

from backend.helpers.user_helpers import assert_active_changeable, assert_role_changeable


class TestAssertRoleChangeable:
    """assert_role_changeable blocks changing the owner account's role."""

    def test_owner_role_raises_409(self):
        """Attempting to change the owner's role raises HTTP 409."""
        with pytest.raises(HTTPException) as exc_info:
            assert_role_changeable("owner")
        assert exc_info.value.status_code == 409

    def test_moderator_role_allowed(self):
        """A non-owner role (moderator) raises nothing."""
        assert_role_changeable("moderator")

    def test_user_role_allowed(self):
        """A non-owner role (user) raises nothing."""
        assert_role_changeable("user")


class TestAssertActiveChangeable:
    """assert_active_changeable blocks deactivating the owner account."""

    def test_deactivating_owner_raises_409(self):
        """Setting is_active=False for the owner raises HTTP 409."""
        with pytest.raises(HTTPException) as exc_info:
            assert_active_changeable("owner", False)
        assert exc_info.value.status_code == 409

    def test_activating_owner_allowed(self):
        """Setting is_active=True for the owner raises nothing (already active or reactivating)."""
        assert_active_changeable("owner", True)

    def test_deactivating_non_owner_allowed(self):
        """Deactivating a non-owner account raises nothing."""
        assert_active_changeable("moderator", False)

    def test_activating_non_owner_allowed(self):
        """Activating a non-owner account raises nothing."""
        assert_active_changeable("user", True)
