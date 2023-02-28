import os

import uvicorn
from uvicorn.supervisors import ChangeReload

if __name__ == "__main__":
    try:
        os.remove("/tmp/uvicorn.sock")
    except FileNotFoundError:
        pass

    config = uvicorn.Config("server:app", uds="/tmp/uvicorn.sock", debug=True)
    server = uvicorn.Server(config=config)

    server.force_exit = True  # <--- https://github.com/encode/uvicorn/issues/675

    sock = config.bind_socket()
    supervisor = ChangeReload(config, target=server.run, sockets=[sock])
    supervisor.run()
