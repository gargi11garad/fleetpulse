from rest_framework.permissions import SAFE_METHODS, BasePermission


class FleetRolePermission(BasePermission):
    """Authenticated staff/managers can change fleet data; users can read it."""

    def has_permission(self, request, view):
        return request.user and request.user.is_authenticated and (
            request.method in SAFE_METHODS or request.user.is_staff
        )
