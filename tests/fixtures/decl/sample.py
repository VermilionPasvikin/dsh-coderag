"""Sample module."""


def add(a, b):
    return a + b


def decorator(func):
    return func


@decorator
def run():
    return add(1, 2)


class Pool:
    def acquire(self):
        return 1
