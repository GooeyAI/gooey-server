import typing

from django.db import transaction, IntegrityError
from django.db.models import Model


def get_or_create_lazy(
    model: typing.Type[Model], create: typing.Callable[..., dict] = None, **kwargs
):
    """
    Look up an object with the given kwargs, creating one if necessary.
    Return a tuple of (object, created), where created is a boolean
    specifying whether an object was created.
    """
    self = model.objects.all()
    # The get() needs to be targeted at the write database in order
    # to avoid potential transaction consistency problems.
    self._for_write = True
    try:
        return self.get(**kwargs), False
    except self.model.DoesNotExist:
        # Try to create an object using passed params.
        try:
            with transaction.atomic(using=self.db):
                return create(**kwargs), True
        except IntegrityError:
            try:
                return self.get(**kwargs), False
            except self.model.DoesNotExist:
                pass
            raise
