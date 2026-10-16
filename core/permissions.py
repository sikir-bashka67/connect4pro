from rest_framework import permissions


def _is_admin(user):
    return bool(user and user.is_authenticated and user.role == 'admin')


def _owner_of(obj):
    """Return the user who owns an object (supports all models of the project)."""
    for attr in ('author', 'provider', 'user', 'client'):
        owner = getattr(obj, attr, None)
        if owner is not None:
            return owner
    # nested objects: photos belong to ad / service
    for attr in ('ad', 'service', 'topic'):
        parent = getattr(obj, attr, None)
        if parent is not None:
            return _owner_of(parent)
    return None


class IsAdminOrReadOnly(permissions.BasePermission):
    """Anyone may read; only platform admins may change catalog data."""

    def has_permission(self, request, view):
        if request.method in permissions.SAFE_METHODS:
            return True
        return _is_admin(request.user)


class IsOwnerOrAdmin(permissions.BasePermission):
    """Authenticated users may create; only the owner or an admin may change/delete."""

    def has_permission(self, request, view):
        if request.method in permissions.SAFE_METHODS:
            return True
        return bool(request.user and request.user.is_authenticated)

    def has_object_permission(self, request, view, obj):
        if request.method in permissions.SAFE_METHODS:
            return True
        return _is_admin(request.user) or _owner_of(obj) == request.user


class IsProviderOwnerOrAdmin(permissions.BasePermission):
    def has_permission(self, request, view):
        if request.method in permissions.SAFE_METHODS:
            return True
        return bool(request.user and request.user.is_authenticated and request.user.role in ('provider', 'admin'))

    def has_object_permission(self, request, view, obj):
        if request.method in permissions.SAFE_METHODS:
            return True
        return _is_admin(request.user) or _owner_of(obj) == request.user


class IsPremiumOrReadOnly(permissions.BasePermission):
    def has_permission(self, request, view):
        if request.method in permissions.SAFE_METHODS:
            return True
        return _is_admin(request.user)

    def has_object_permission(self, request, view, obj):
        if request.method in permissions.SAFE_METHODS:
            if not getattr(obj, 'is_premium_only', False):
                return True
            return bool(request.user and request.user.is_authenticated and request.user.is_premium_active())
        return _is_admin(request.user)


class IsPremium(permissions.BasePermission):
    message = 'Доступно только по подписке Premium.'

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and request.user.is_premium_active())
