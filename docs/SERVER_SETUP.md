# Server setup (`stats.php`)

The server column reads a small JSON document from **`stats.php`**. It only needs PHP (7.4+) on a Linux machine.
It reports CPU, temperature, RAM, swap, load, uptime, the system disk, **RAID/storage pools with health**, and network counters.

## 1. Quick start (nginx or Apache, no Docker)
```bash
# Debian/Ubuntu                           # Fedora/RHEL                       # Arch
sudo apt install nginx php-fpm            # sudo dnf install nginx php-fpm    # sudo pacman -S nginx php-fpm
sudo cp server/stats.php /var/www/html/stats.php
curl http://localhost/stats.php            # JSON appears
```
Minimal nginx `location` (adapt the socket path to your PHP version):
```nginx
location = /stats.php {
    include snippets/fastcgi-php.conf;
    fastcgi_pass unix:/run/php/php-fpm.sock;
}
```
Test from the PC: `curl http://192.168.0.123/stats.php`, then `stats-widget doctor`.

## 2. Configure (only if needed)
Copy `stats.config.example.php` to `stats.config.php` next to `stats.php`:
```php
<?php return [
    'raid_paths'     => ['/raids'],     // where your RAID / storage pool is mounted
    'net_interfaces' => ['enp3s0'],     // default: all physical NICs
    'token'          => 'long-random',  // then:  ...stats.php?key=long-random   (and set it in the widget)
];
```

## 3. RAID shows "Not reachable" / N/A? Run the debug page
```
http://192.168.0.123/stats.php?debug=1
```
It prints the PHP user, whether you are inside Docker, `open_basedir`, and *why* each configured path can not be read.
The usual causes:

| Cause | Fix |
|---|---|
| **PHP runs in a Docker container** and `/raids` is not mounted into it | add `-v /raids:/raids:ro` (see §4) |
| The web-server user (`www-data`, `nginx`, `apache`) can not enter the mount | `sudo chmod o+x /raids` (and every parent folder); read access to files is *not* needed |
| `open_basedir` blocks the path | add the path to `open_basedir` in your PHP pool config, or clear it |
| systemd hardening (`ProtectSystem=strict`, `PrivateTmp`, `ProtectHome`) in the php-fpm unit | `systemctl edit php8.x-fpm` and allow `ReadOnlyPaths=/raids`, or relax the options |
| The RAID is mounted somewhere else | set `raid_paths` (or leave it: with `auto_detect` mdadm / ZFS / btrfs / mergerfs mounts are found automatically) |

RAID **health** (healthy / degraded / rebuilding x %) comes from `/proc/mdstat` and works for mdadm arrays (`md0`…).
ZFS, btrfs and mergerfs pools show their capacity but no mdadm health.

## 4. Docker
Containers see the host's `/proc/stat`, `/proc/meminfo` and `/sys`, but **not** the host's mounts or network interfaces. Use host networking and mount what you want to measure:
```yaml
# docker-compose.yml  (see server/docker-compose.example.yml)
services:
  stats:
    image: php:8.3-cli
    network_mode: host                 # real NIC counters; the server listens on the host
    restart: unless-stopped
    command: php -S 0.0.0.0:8099 -t /app
    volumes:
      - ./stats.php:/app/stats.php:ro
      - ./stats.config.php:/app/stats.config.php:ro
      - /raids:/raids:ro               # <- your RAID mount
```
With this the URL is `http://<server>:8099/stats.php`. For port 80 put your existing reverse proxy in front of it.
The built-in PHP server is fine on a trusted LAN/VPN; do not expose it to the internet.

## 5. Security
`stats.php` reveals system information. Keep it on your LAN and VPN (NetBird, WireGuard, Tailscale), do not forward it to the internet,
and consider the `token` option. If it must be reachable remotely, serve it only over HTTPS behind your VPN or a reverse proxy with authentication.

## 6. The JSON
```jsonc
{ "version":2, "host":"rayaz", "uptime":1234567, "load":[0.42,0.37,0.31], "cores":12,
  "cpu":18.4, "temp":47.5,
  "ram_u":9.6, "ram_t":31.2, "ram_p":30.8, "swap_u":0.1, "swap_t":4, "swap_p":2.5,
  "ssd_u":212.4, "ssd_t":465.8, "ssd_p":45.6,
  "raid_u":6840.2, "raid_t":10900.0, "raid_p":62.8,
  "raid":{"path":"/raids","ok":true,"error":null,"arrays":[{"name":"md0","level":"raid5","devices":4,"working":4,"health":"ok"}]},
  "disks":[{"mount":"/","fs":"ext4","used":212.4,"total":465.8,"percent":45.6,"array":false}],
  "net_rx":5000000000, "net_tx":2000000000, "net_iface":"enp3s0" }
```
All sizes are GB. The keys of the original version (`cpu temp ram_* ssd_* raid_* net_*`) are unchanged, so older widgets keep working.
