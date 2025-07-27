"""
Exception classes for the application
Enhanced to match legacy services.exceptions functionality
"""


class ServiceError(Exception):
    """
    Base exception for all service-related errors
    """
    def __init__(self, message: str, code: str = None):
        super().__init__(message)
        self.message = message
        self.code = code or "SERVICE_ERROR"
    
    def to_dict(self):
        """Convert exception to dictionary for JSON responses"""
        return {
            'error': self.code,
            'message': self.message
        }


class ValidationError(ServiceError):
    """
    Raised when input validation fails
    """
    def __init__(self, message: str, field: str = None):
        super().__init__(message, "VALIDATION_ERROR")
        self.field = field
    
    def to_dict(self):
        result = super().to_dict()
        if self.field:
            result['field'] = self.field
        return result


class NotFoundError(ServiceError):
    """
    Raised when requested resource is not found
    """
    def __init__(self, resource: str, id: int = None):
        message = f"{resource} not found"
        if id:
            message = f"{resource} with ID {id} not found"
        super().__init__(message, "NOT_FOUND")
        self.resource = resource
        self.id = id


class DuplicateError(ServiceError):
    """
    Raised when attempting to create a duplicate resource
    """
    def __init__(self, resource: str, field: str = None, value: str = None):
        message = f"Duplicate {resource}"
        if field and value:
            message = f"{resource} with {field}='{value}' already exists"
        super().__init__(message, "DUPLICATE_ERROR")
        self.resource = resource
        self.field = field
        self.value = value


class BusinessRuleError(ServiceError):
    """
    Raised when business rule validation fails
    """
    def __init__(self, message: str, rule: str = None):
        super().__init__(message, "BUSINESS_RULE_VIOLATION")
        self.rule = rule
    
    def to_dict(self):
        result = super().to_dict()
        if self.rule:
            result['rule'] = self.rule
        return result


class DatabaseError(ServiceError):
    """
    Raised when database operations fail
    """
    def __init__(self, message: str, operation: str = None):
        super().__init__(message, "DATABASE_ERROR")
        self.operation = operation
    
    def to_dict(self):
        result = super().to_dict()
        if self.operation:
            result['operation'] = self.operation
        return result


class PermissionError(ServiceError):
    """
    Raised when user lacks permission for an operation
    """
    def __init__(self, message: str, required_permission: str = None):
        super().__init__(message, "PERMISSION_DENIED")
        self.required_permission = required_permission


class ConcurrencyError(ServiceError):
    """
    Raised when concurrent modification is detected
    """
    def __init__(self, resource: str, message: str = None):
        if not message:
            message = f"{resource} was modified by another process"
        super().__init__(message, "CONCURRENCY_ERROR")
        self.resource = resource


class IntegrationError(ServiceError):
    """
    Raised when external integration fails
    """
    def __init__(self, service: str, message: str):
        super().__init__(f"{service} integration failed: {message}", "INTEGRATION_ERROR")
        self.service = service


class ConfigurationError(ServiceError):
    """
    Raised when service configuration is invalid
    """
    def __init__(self, message: str, config_key: str = None):
        super().__init__(message, "CONFIGURATION_ERROR")
        self.config_key = config_key