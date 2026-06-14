class BusinessException(Exception):
    def __init__(self, message='业务异常'):
        super().__init__(message)
        self.message = message


class ValidationException(BusinessException):
    def __init__(self, message='参数校验失败'):
        super().__init__(message)


class NotFoundException(BusinessException):
    def __init__(self, message='资源不存在'):
        super().__init__(message)
