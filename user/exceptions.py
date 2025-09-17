class InvalidOtpException(Exception):
    pass

class OtpExpiredException(Exception):
    pass

class ResourceNotFoundException(Exception):
    pass

class InvalidTokenException(Exception):
    pass

class OtpResendTooSoonException(Exception):
    pass

class LoggingFailureException(Exception):
    pass