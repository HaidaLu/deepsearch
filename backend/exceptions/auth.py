# exceptions/auth.py — Custom auth exception
# Keeps HTTP concerns out of the service layer (service raises this,
# app_main.py converts it to an HTTP 401 response)

class AuthError(Exception):
    def __init__(self, message: str = "Authentication failed"):
        self.message = message
        super().__init__(message)
