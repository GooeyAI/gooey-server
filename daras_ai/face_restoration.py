from concurrent.futures import ThreadPoolExecutor

import replicate


def gfpgan(img: str) -> bytes:
    model = replicate.models.get("tencentarc/gfpgan")
    return model.predict(img=img)


def map_parallel(fn, it):
    with ThreadPoolExecutor(max_workers=len(it)) as pool:
        return list(pool.map(fn, it))
