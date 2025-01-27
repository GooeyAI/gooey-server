from bots.tasks import exec_scheduled_runs


def run():
    exec_scheduled_runs.delay()
