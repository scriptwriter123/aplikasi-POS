class POSException(Exception):
    pass


class AuthenticationError(POSException):
    pass


class AuthorizationError(POSException):
    pass


class InsufficientStockError(POSException):
    pass


class PaymentIncompleteError(POSException):
    pass


class ShiftNotOpenError(POSException):
    pass


class LicenseExpiredError(POSException):
    pass


class ValidationError(POSException):
    pass
