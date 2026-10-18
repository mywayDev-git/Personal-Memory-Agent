class AppError(Exception):
    def __init__(self, code, message, status=422, retryable=False):
        self.code, self.message = code, message
        self.status, self.retryable = status, retryable
        super().__init__(code)
