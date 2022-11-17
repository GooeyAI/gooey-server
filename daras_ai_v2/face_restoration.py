from concurrent.futures import ThreadPoolExecutor

from daras_ai_v2.gpu_server import call_gpu_server_b64, GpuEndpoints


def gfpgan(img: str) -> bytes:
    return call_gpu_server_b64(
        endpoint=GpuEndpoints.gfpgan,
        input_data={
            "img": img,
            "version": "v1.4",
            "scale": 1,
        },
    )[0]


def map_parallel(fn, it):
    with ThreadPoolExecutor(max_workers=len(it)) as pool:
        return list(pool.map(fn, it))
