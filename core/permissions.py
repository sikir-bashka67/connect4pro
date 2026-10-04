from rest_framework import permissions


class IsAdminOrReadOnly(permissions.BasePermission):
    """Anyone may read; only platform admins may change catalog data."""

    def has_permission(self, request, view):
        if request.method in permissions.SAFE_METHODS:
            return True
        return bool(request.user and request.user.is_authenticated and request.user.role == 'admin')


class IsOwnerOrAdmin(permissions.BasePermission):
    """Object can be changed only by its owner or an administrator."""

    def has_object_permission(self, request, view, obj):
        if request.method in permissions.SAFE_METHODS:
            return True
        owner = getattr(obj, 'author', None) or getattr(obj, 'provider', None)
        return bool(request.user and request.user.is_authenticated and (owner == request.user or request.user.role == 'admin'))


class IsProviderOwnerOrAdmin(permissions.BasePermission):
    def has_permission(self, request, view):
        if request.method in permissions.SAFE_METHODS:
            return True
        return bool(request.user and request.user.is_authenticated and request.user.role in ('provider', 'admin'))

    def has_object_permission(self, request, view, obj):
        if request.method in permissions.SAFE_METHODS:
            return True
        return bool(request.user and request.user.is_authenticated and (obj.provider == request.user or request.user.role == 'admin'))


class IsPremiumOrReadOnly(permissions.BasePermission):
    def has_permission(self, request, view):
        if request.method in permissions.SAFE_METHODS:
            return True
        return bool(request.user and request.user.is_authenticated and request.user.role == 'admin')

    def has_object_permission(self, request, view, obj):
        if request.method in permissions.SAFE_METHODS:
            if not getattr(obj, 'is_premium_only', False):
                return True
            return bool(request.user and request.user.is_authenticated and (request.user.subscription == 'premium' or request.user.role == 'admin'))
        return bool(request.user and request.user.is_authenticated and request.user.role == 'admin')
