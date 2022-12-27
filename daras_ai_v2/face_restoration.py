from concurrent.futures import ThreadPoolExecutor

from daras_ai_v2.gpu_server import call_gpu_server_b64, GpuEndpoints


def gfpgan(img: str, scale: int = 1) -> bytes:
    # one weird hack to fix the gfpgan's crappy maths -
    #   https://github.com/TencentARC/GFPGAN/blob/2eac2033893ca7f427f4035d80fe95b92649ac56/cog_predict.py#L135
    if scale == 1:
        scale = 2 - 1e-10
    elif scale != 2:
        scale *= 2

    return call_gpu_server_b64(
        endpoint=GpuEndpoints.gfpgan,
        input_data={
            "img": img,
            "version": "v1.4",
            "scale": scale,
        },
    )[0]


def map_parallel(fn, it):
    with ThreadPoolExecutor(max_workers=len(it)) as pool:
        return list(pool.map(fn, it))
