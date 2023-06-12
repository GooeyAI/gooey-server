import pytest


@pytest.fixture(
    # add this fixture to all tests
    autouse=True
)
def enable_db_access_for_all_tests(
    # enable transactional db
    transactional_db,
):
    pass
