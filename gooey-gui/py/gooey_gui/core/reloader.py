import asyncio
import importlib
import logging
import sys
from time import time
import traceback
from copy import copy
from pathlib import Path

import uvicorn
from uvicorn.server import HANDLED_SIGNALS
from uvicorn.supervisors import ChangeReload

from .pubsub import realtime_push, _extra_subscriptions

logger = logging.getLogger("uvicorn.error")


def runserver(*args, **kwargs):
    config = uvicorn.Config(*args, **kwargs)
    server = HotReloadServer(config)
    server.run()


class _UvicornServer(uvicorn.Server):
    async def startup(self, *args, **kwargs):
        ret = await super().startup(*args, **kwargs)
        if self.config.reload:
            realtime_push("--hot-reload", 1)
        return ret


class HotReloadServer:
    def __init__(self, config: uvicorn.Config):
        self.config = config
        self.server: _UvicornServer | None = None
        self.did_reload = False
        if self.config.reload:
            _extra_subscriptions.add("--hot-reload")

    def run(self, *args, **kwargs):
        self.config.setup_event_loop()
        return asyncio.run(self.serve(*args, **kwargs))

    async def serve(self, *args, **kwargs):
        watcher = ChangeReload(self.config, lambda _: None, [])
        task = asyncio.create_task(self.reloader(watcher))
        try:
            while True:
                config = copy(self.config)
                config.loaded = False
                self.server = _UvicornServer(config)
                self.did_reload = False
                try:
                    await self.server.serve(*args, **kwargs)
                except:
                    traceback.print_exc()
                    await self.wait_for_changes()
                if not self.did_reload:
                    return
                try:
                    reload_modules(watcher)
                except:
                    traceback.print_exc()
                    await self.wait_for_changes()
        finally:
            logger.info("Stopping reloader")
            watcher.should_exit.set()
            task.cancel()

    async def wait_for_changes(self):
        should_exit = False

        def handle_exit():
            nonlocal should_exit
            should_exit = True

        loop = asyncio.get_event_loop()
        for sig in HANDLED_SIGNALS:
            loop.add_signal_handler(sig, handle_exit)

        while not (should_exit or self.did_reload):
            await asyncio.sleep(1)

    async def reloader(self, watcher):
        while True:
            loop = asyncio.get_event_loop()
            changes = await loop.run_in_executor(None, watcher.should_restart)
            if not changes:
                continue
            logger.warning(
                "%s detected changes in %s. Reloading...",
                watcher.reloader_name,
                ", ".join(map(str, changes)),
            )
            self.did_reload = True
            if self.server and self.server.started:
                self.server.should_exit = True


def reload_modules(watcher: ChangeReload):
    for name, module in list(sys.modules.items()):
        try:
            if not module.__file__:
                continue
        except AttributeError:
            continue
        modpath = Path(module.__file__)
        if any(
            modpath.match(pattern) for pattern in watcher.config.reload_excludes
        ) or not any(
            modpath.is_relative_to(directory) for directory in watcher.reload_dirs
        ):
            continue
        sys.modules.pop(name, None)
