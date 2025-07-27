"""
Exception classes for the application
"""


class ServiceError(Exception):
    """Base exception for service layer errors"""
    pass


class ValidationError(ServiceError):
    """Raised when data validation fails"""
    pass


class NotFoundError(ServiceError):
    """Raised when a requested resource is not found"""
    pass


class BusinessRuleError(ServiceError):
    """Raised when a business rule is violated"""
    pass


class DatabaseError(ServiceError):
    """Raised when database operations fail"""
    pass


class ConfigurationError(ServiceError):
    """Raised when configuration is invalid"""
    pass