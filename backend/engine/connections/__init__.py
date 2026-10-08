"""
Database Connection Manager package for Antigravity DataFlow.
Provides named connection CRUD, OS-keyring credential storage, and driver factory.
"""
from .manager import ConnectionManager

__all__ = ["ConnectionManager"]
