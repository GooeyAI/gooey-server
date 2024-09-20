FROM vespaengine/vespa:8

# NOTE: this HEALTHCHECK will only work *after* Vespa is configured with setup_vespa_db script
HEALTHCHECK CMD curl -f 'http://localhost:8080/status.html' || exit 1
