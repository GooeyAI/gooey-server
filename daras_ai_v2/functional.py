import typing
from concurrent.futures import ThreadPoolExecutor

T = typing.TypeVar("T")
R = typing.TypeVar("R")


def flatten(l1: typing.Iterable[typing.Iterable[T]]) -> list[T]:
    return [it for l2 in l1 for it in l2]


def map_parallel(fn: typing.Callable[[T], R], it: typing.Sequence[T]) -> typing.List[R]:
    with ThreadPoolExecutor(max_workers=len(it)) as pool:
        return list(pool.map(fn, it))
