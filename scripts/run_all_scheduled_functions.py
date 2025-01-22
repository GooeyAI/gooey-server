from bots.tasks import run_all_scheduled_functions


def run():
    run_all_scheduled_functions.delay()
