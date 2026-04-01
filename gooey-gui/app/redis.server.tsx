import { createClient } from "redis";
import settings from "./settings";

declare global {
  var redis: ReturnType<typeof createClient> | null;
}

if (typeof global.redis === "undefined") {
  if (!settings.REDIS_URL) {
    global.redis = null;
  } else {
    global.redis = createClient({ url: settings.REDIS_URL });
    global.redis.connect();
  }
}

export default global.redis;
