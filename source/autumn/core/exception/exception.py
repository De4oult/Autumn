

class DependencyInjectionError(RuntimeError):
    pass

class DependencyProviderError(KeyError):
    pass

class CircularDependencyError(DependencyInjectionError):
    pass