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
Copy `stats.config.example.php` to `stats.config.php` next to `stats.php` (Docker users: use the `STATS_...` environment variables instead):
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
| **PHP runs in a Docker container** and `/raids` is not mounted into it | use the stack in §4 (`RAID_HOST_PATH`), or add `-v /your/raid:/raids:ro` |
| The web-server user (`www-data`, `nginx`, `apache`) can not enter the mount | `sudo chmod o+x /raids` (and every parent folder); read access to files is *not* needed |
| `open_basedir` blocks the path | add the path to `open_basedir` in your PHP pool config, or clear it |
| systemd hardening (`ProtectSystem=strict`, `PrivateTmp`, `ProtectHome`) in the php-fpm unit | `systemctl edit php8.x-fpm` and allow `ReadOnlyPaths=/raids`, or relax the options |
| The RAID is mounted somewhere else | set `raid_paths` (or leave it: with `auto_detect` mdadm / ZFS / btrfs / mergerfs mounts are found automatically) |

**No RAID?** If the folder you point at is on the same disk as the system (for example a plain `/raids` directory), `stats.php` detects that and the widget simply hides the RAID row - nothing to configure.

RAID **health** (healthy / degraded / rebuilding x %) comes from `/proc/mdstat` and works for mdadm arrays (`md0`…).
ZFS, btrfs and mergerfs pools show their capacity but no mdadm health.

## 4. Docker / Portainer (recommended for a server)
The repository contains a ready `docker-compose.yml` and `server/Dockerfile`: Docker **builds the image straight from GitHub**, nothing
has to be copied or edited. Settings are environment variables.

### Step 1 - find where the RAID is mounted on the server
```bash
cat /proc/mdstat            # mdadm arrays (md0 ...)
df -h | grep -E "md|raid"   # shows the mount point, e.g. /raids or /mnt/raid
```
Write the mount point down (this guide uses `/raids`). The container always sees it as `/raids`.

### Step 2 - note the old stats.php (do not delete it yet)
```bash
sudo find / -name stats.php -not -path "*/proc/*" 2>/dev/null     # where the old file lives
grep -rn "stats.php" /etc/nginx 2>/dev/null                       # does nginx have a special rule for it?
```
If nginx runs in a container, the same file is inside that container's web folder (`docker ps` shows your containers).

### Step 3 - create the stack in Portainer
1. **Stacks -> Add stack**. Name: `stats-widget`.
2. Build method: **Repository**.
3. Repository URL: `https://github.com/TechZeeLand/Stats-Widget` - Reference: `refs/heads/main` - Compose path: `docker-compose.yml`. (Public repo: leave authentication off.)
4. **Environment variables -> Add**:

| Name | Value | Needed? |
|---|---|---|
| `RAID_HOST_PATH` | your RAID mount point from step 1, e.g. `/raids` | yes, if it is not `/raids` |
| `STATS_PORT` | port to listen on (default `8099`) | no |
| `STATS_TOKEN` | a long random password (then use `stats.php?key=...`) | recommended |
| `STATS_NET_INTERFACES` | e.g. `enp3s0` (default: all physical network cards) | no |
| `STATS_HOSTNAME` | name shown in the widget (default: the server's name) | no |

5. Tick **Re-pull image / build**  if offered, then **Deploy the stack**. The first build takes about a minute.

### Step 4 - test
Open `http://192.168.0.123:8099/stats.php?debug=1` (your server's IP and port). `"in_docker": true` is normal; `/raids` must say `"ok"`.
Then open `http://192.168.0.123:8099/stats.php` - JSON with `"raid_u"`, `"raid_t"` numbers means it works.
If `/raids` says *does not exist*: `RAID_HOST_PATH` is wrong. If it says *cannot read*: see the table in section 3, or add `user: root` under the service in the stack editor.

### Step 5 - switch the widget over and remove the old stats.php
Pick one:
* **Change the widget's address** (simplest): on your PC run `stats-widget config` and set the server address to `http://192.168.0.123:8099/stats.php`.
* **Keep the old address** `http://192.168.0.123/stats.php`: let nginx forward it to the container. In the server block that serves port 80 put
  (use the server's LAN IP, not 127.0.0.1, if nginx itself runs in a container):
  ```nginx
  location = /stats.php {
      proxy_pass http://192.168.0.123:8099/stats.php;
  }
  ```
  then `sudo nginx -t && sudo systemctl reload nginx` (or `docker exec <nginx-container> nginx -s reload`).

Once the widget shows the right numbers, delete the old file you found in step 2 (`sudo rm /path/to/stats.php`), and remove any old
`stats.config.php` next to it and old PHP-specific `location` rules. Nothing else from the old setup is needed.

### Updating later
Portainer: **Stacks -> stats-widget -> Pull and redeploy**, with *Re-build image* switched on and *Re-pull image* switched off (the image is built from the repository, there is nothing to pull).

### Without Portainer
```bash
git clone https://github.com/TechZeeLand/Stats-Widget && cd Stats-Widget
RAID_HOST_PATH=/raids docker compose up -d --build
```
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
