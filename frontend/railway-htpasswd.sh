#!/bin/sh
# Build the basic-auth file at container start. Fails closed: without credentials the site
# must not come up unauthenticated.
set -e
if [ -z "$BASIC_AUTH_USER" ] || [ -z "$BASIC_AUTH_PASSWORD" ]; then
    echo "BASIC_AUTH_USER and BASIC_AUTH_PASSWORD must be set; refusing to start unauthenticated." >&2
    exit 1
fi
htpasswd -bcm /etc/nginx/.htpasswd "$BASIC_AUTH_USER" "$BASIC_AUTH_PASSWORD"
