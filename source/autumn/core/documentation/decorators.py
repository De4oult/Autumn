import inspect

def summary(text: str):
    def wrapper(object):
        setattr(object, '__summary__', text)
        return object
    
    return wrapper

def description(text: str):
    def wrapper(object):
        setattr(object, '__description__', text)
        return object
    
    return wrapper

def tag(text: str):
    def wrapper(object):
        if inspect.isclass(object):
            setattr(object, '__tag__', text)
            return object
        
        tags = getattr(object, '__tags__', None)

        if tags is None:
            tags = []
            setattr(object, '__tags__', tags)

        tags.append(text)

        return object
    
    return wrapper
