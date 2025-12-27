from collections.abc import Callable


def then[T, U](x: T | None, f: Callable[[T], U]) -> U | None:
    """If the optional value `x` is some, return the result of applying `f`,
    else return `None`"""
    if x is None:
        return None
    return f(x)
