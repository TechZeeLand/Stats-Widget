# SPDX-License-Identifier: AGPL-3.0-or-later
# Stats Widget server endpoint. Build context = this folder (server/).
# Settings are environment variables - see docs/SERVER_SETUP.md (STATS_RAID_PATHS, STATS_TOKEN, ...).
FROM php:8.3-cli-alpine

WORKDIR /app
COPY stats.php /app/stats.php

ENV STATS_PORT=8099
EXPOSE 8099

# Runs as an unprivileged user. If /stats.php?debug=1 says a path is "not readable", see SERVER_SETUP.md.
USER nobody
CMD ["sh", "-c", "exec php -S 0.0.0.0:${STATS_PORT:-8099} -t /app"]
