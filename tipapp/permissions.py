"""Thermal Image Processing Django Application Permissions."""

# Third-Party
import django
from django.conf import settings
from django.contrib.auth import models
from rest_framework import permissions, request, viewsets
import logging

# Configure logging
logger = logging.getLogger(__name__)


# Typing
from typing import Union
from typing import Any

class IsInAdministratorsGroup(permissions.BasePermission):
    """Permissions for the a user in the Administrators group."""

    def has_permission(  # type: ignore
        self,
        request: request.Request,
        view: viewsets.GenericViewSet,
    ) -> bool:
        return is_administrator(request.user)


class IsInOfficersGroup(permissions.BasePermission):
    """Permissions for the a user in the Administrators group."""

    def has_permission(  # type: ignore
        self,
        request: request.Request,
        view: viewsets.GenericViewSet,
    ) -> bool:
        return is_officer(request.user)


class IsInAdminOrOfficersGroup(permissions.BasePermission):
    """Permissions for the a user in the Administrators group."""

    def has_permission(  # type: ignore
        self,
        request: request.Request,
        view: viewsets.GenericViewSet,
    ) -> bool:
        return is_officer(request.user) or is_administrator(request.user)


def is_administrator(user: Union[models.User, models.AnonymousUser]) -> bool:
    """Checks whether a user is an Administrator.

    Args:
        user (Union[models.User, models.AnonymousUser]): User to be checked.

    Returns:
        bool: Whether the user is in the Administrator group.
    """
    # Check and Return
    group = django.contrib.auth.models.Group.objects.filter(name=settings.GROUP_ADMIN).first()
    return (
        not isinstance(user, models.AnonymousUser)  # Must be logged in
        and group is not None
        and user.groups.filter(id=group.id).exists()  # Must be in group
    )


def is_officer(user: Union[models.User, models.AnonymousUser]) -> bool:
    """Checks whether a user is an Officer.

    Args:
        user (Union[models.User, models.AnonymousUser]): User to be checked.

    Returns:
        bool: Whether the user is in the Officer group.
    """
    # Check and Return
    group = django.contrib.auth.models.Group.objects.filter(name=settings.GROUP_OFFICERS).first()
    return (
        not isinstance(user, models.AnonymousUser)  # Must be logged in
        and group is not None
        and user.groups.filter(id=group.id).exists()  # Must be in group
    )



def has_admin_or_officer_permission(request) -> bool:
    """
    Check if the request user has admin or officer permission.
    
    Args:
        request: Django HTTP request object
        
    Returns:
        bool: True if user is admin or officer, False otherwise
    """
    if not request.user.is_authenticated:
        return False
    return is_administrator(request.user) or is_officer(request.user)
