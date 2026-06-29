from rest_framework.permissions import BasePermission, SAFE_METHODS
from rest_framework.exceptions import PermissionDenied

class RolePermission(BasePermission):
    def __init__(self, permission):
        self.permission = permission

    def has_permission(self, request, view):
        if not (request.user and request.user.is_authenticated):
            return False
        
        if request.user.has_permission(self.permission):
            return True
        
        raise PermissionDenied({"error": f"You do not have the permission: '{self.permission}' to perform this action."})
    

    def has_object_permission(self, request, view, obj):
        if request.method in SAFE_METHODS:
            return True
        
        owner_per = getattr(obj, 'owner', getattr(obj, 'user', None))

        if owner_per == request.user:
            return True
        
        raise PermissionDenied({"error": "Access Denied. You do not own this specific resource."})