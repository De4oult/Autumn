def body(schema):
    def decorator(func):
        setattr(func, '__body_schema__', schema)
        return func

    return decorator
