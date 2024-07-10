FROM vespaengine/vespa:8

HEALTHCHECK CMD curl -f 'http://localhost:8080/status.html' || exit 1
