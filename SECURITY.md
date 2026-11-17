# Security policy

## Supported versions
Only the latest release receives security fixes.

## Reporting a vulnerability
Please **do not** open a public issue. Use GitHub's private reporting:
**Security → Report a vulnerability** on https://github.com/TechZeeLand/Stats-Widget/security/advisories/new
You will get an answer within 7 days. Please include the version (`stats-widget version`), what you did and what happened.

## Things worth knowing
* `server/stats.php` exposes system information (uptime, load, disk sizes, host name). Do not publish it on the open internet.
  Keep it on your LAN / VPN (e.g. NetBird, WireGuard, Tailscale), or protect it with the `token` option and TLS/reverse-proxy rules.
  The `?debug=1` page also requires the token when one is set.
* The one-line installer runs a script downloaded over HTTPS from this repository. If you prefer, clone the repository,
  read the scripts, and run `./install.sh` locally.
* The widget needs no elevated privileges at runtime; the installer uses `sudo` only to install distribution packages.
