from bots.tasks import run_all_scheduled_runs


def run():
    run_all_scheduled_runs.delay()
