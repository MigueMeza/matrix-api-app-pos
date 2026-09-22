from enum import Enum


class Rol(str, Enum):
    """Los tres tipos de usuario. vendedor nunca inicia sesión por sí mismo."""

    VENDEDOR = "vendedor"
    SUPERVISOR = "supervisor"
    SUPER_ADMIN = "super_admin"


ROLES_CON_LOGIN = (Rol.SUPERVISOR, Rol.SUPER_ADMIN)
