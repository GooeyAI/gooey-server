import pytest


@pytest.fixture
def django_db_setup(django_db_setup, django_db_blocker):
    with django_db_blocker.unblock():
        from django.core.management import call_command

        call_command("loaddata", "fixture.json")


@pytest.fixture(
    # add this fixture to all tests
    autouse=True
)
def enable_db_access_for_all_tests(
    # enable transactional db
    transactional_db,
):
    pass
