<?php
/**
 * Stats Widget - server endpoint
 * https://github.com/TechZeeLand/Stats-Widget
 *
 * Returns the server's CPU / RAM / disk / RAID / network numbers as JSON.
 * Drop this file on any web server with PHP 7.4+ (Linux host).
 *
 * SPDX-License-Identifier: AGPL-3.0-or-later
 */

declare(strict_types=1);

// ───────────────────────── SETTINGS ─────────────────────────
// Do not edit this block - create "stats.config.php" next to this file instead
// (see server/stats.config.example.php). Anything you set there overrides these.
$CONFIG = [
    'proc_root'      => '/proc',   // use '/host/proc' when running in Docker with  -v /proc:/host/proc:ro
    'sys_root'       => '/sys',
    'mounts_file'    => null,      // null = <proc_root>/mounts  (or <proc_root>/1/mounts when readable)
    'system_path'    => '/',       // the "SSD / system disk" row
    'raid_paths'     => ['/raids'],// mount points shown as the RAID row (first one wins); [] = auto-detect only
    'auto_detect'    => true,      // also look for md / ZFS / btrfs / mergerfs mounts when raid_paths fails
    'net_interfaces' => [],        // [] = auto (all physical NICs); or e.g. ['eth0']
    'hostname'       => null,      // null = detect
    'cpu_sample_ms'  => 100,       // how long CPU usage is measured (50-1000)
    'token'          => '',        // non-empty = callers must add  ?key=<token>
    'allow_origin'   => '',        // CORS header, normally not needed
    'allow_client_settings' => true, // true = the widget may choose the system disk and network cards (?system=, ?net=)
];
if (is_file(__DIR__ . '/stats.config.php')) {
    $user = require __DIR__ . '/stats.config.php';
    if (is_array($user)) {
        $CONFIG = array_replace($CONFIG, $user);
    }
}
// Environment variables win over the file (handy in Docker / Portainer, where no config file is mounted):
//   STATS_PROC_ROOT, STATS_SYS_ROOT, STATS_MOUNTS_FILE, STATS_SYSTEM_PATH, STATS_HOSTNAME, STATS_TOKEN, STATS_ALLOW_ORIGIN,
//   STATS_RAID_PATHS and STATS_NET_INTERFACES (comma separated), STATS_AUTO_DETECT (0/1), STATS_CPU_SAMPLE_MS,
//   STATS_ALLOW_CLIENT_SETTINGS (0/1)
foreach ([
    'STATS_PROC_ROOT'      => ['proc_root', 'str'],
    'STATS_SYS_ROOT'       => ['sys_root', 'str'],
    'STATS_MOUNTS_FILE'    => ['mounts_file', 'str'],
    'STATS_SYSTEM_PATH'    => ['system_path', 'str'],
    'STATS_HOSTNAME'       => ['hostname', 'str'],
    'STATS_TOKEN'          => ['token', 'str'],
    'STATS_ALLOW_ORIGIN'   => ['allow_origin', 'str'],
    'STATS_RAID_PATHS'     => ['raid_paths', 'list'],
    'STATS_NET_INTERFACES' => ['net_interfaces', 'list'],
    'STATS_AUTO_DETECT'    => ['auto_detect', 'bool'],
    'STATS_CPU_SAMPLE_MS'  => ['cpu_sample_ms', 'int'],
    'STATS_ALLOW_CLIENT_SETTINGS' => ['allow_client_settings', 'bool'],
] as $envName => [$key, $type]) {
    $raw = getenv($envName);
    if ($raw === false || trim($raw) === '') {
        continue;                       // unset or empty = keep the default
    }
    $raw = trim($raw);
    if ($type === 'list') {
        $CONFIG[$key] = array_values(array_filter(array_map('trim', explode(',', $raw)), 'strlen'));
    } elseif ($type === 'bool') {
        $CONFIG[$key] = !in_array(strtolower($raw), ['0', 'false', 'no', 'off'], true);
    } elseif ($type === 'int') {
        $CONFIG[$key] = (int)$raw;
    } else {
        $CONFIG[$key] = $raw;
    }
}

@ini_set('display_errors', '0');
header('Content-Type: application/json; charset=utf-8');
header('Cache-Control: no-store');
if ($CONFIG['allow_origin'] !== '') {
    header('Access-Control-Allow-Origin: ' . $CONFIG['allow_origin']);
}

if ($CONFIG['token'] !== '' && !hash_equals((string)$CONFIG['token'], (string)($_GET['key'] ?? ''))) {
    http_response_code(403);
    echo json_encode(['error' => 'forbidden']);
    exit;
}

// ───────────────────────── HELPERS ─────────────────────────
function slurp(string $path): ?string
{
    $data = @file_get_contents($path);
    return $data === false ? null : $data;
}

function pct($part, $whole): float
{
    return $whole > 0 ? round(100 * $part / $whole, 1) : 0.0;
}

/** Disk usage of a path -> [used_gb, total_gb, error|null] */
function disk_usage(string $path): array
{
    if (!@file_exists($path)) {
        return [0.0, 0.0, 'path does not exist (or is not visible to PHP)'];
    }
    $total = @disk_total_space($path);
    $free  = @disk_free_space($path);
    if ($total === false || $free === false || $total <= 0) {
        return [0.0, 0.0, 'PHP cannot read the size (permissions or open_basedir)'];
    }
    return [round(($total - $free) / 1024 ** 3, 1), round($total / 1024 ** 3, 1), null];
}

// ───────────────────────── CPU ─────────────────────────
function cpu_ticks(string $proc): ?array
{
    $stat = slurp("$proc/stat");
    if ($stat === null) {
        return null;
    }
    $f = preg_split('/\s+/', trim(strtok($stat, "\n")));
    $v = array_map('intval', array_slice($f, 1, 8)); // user nice system idle iowait irq softirq steal
    return ['total' => array_sum($v), 'idle' => ($v[3] ?? 0) + ($v[4] ?? 0)];
}

function cpu_percent(string $proc, int $ms): float
{
    $a = cpu_ticks($proc);
    usleep(max(50, min(1000, $ms)) * 1000);
    $b = cpu_ticks($proc);
    if (!$a || !$b) {
        return 0.0;
    }
    $dt = $b['total'] - $a['total'];
    return $dt > 0 ? round(100 * (1 - ($b['idle'] - $a['idle']) / $dt), 1) : 0.0;
}

function cpu_temperature(string $sys): float
{
    // 1) hwmon: prefer the CPU package sensor
    $best = null;
    $rank = ['coretemp' => 0, 'k10temp' => 0, 'zenpower' => 0, 'cpu_thermal' => 1, 'acpitz' => 2];
    foreach (glob("$sys/class/hwmon/hwmon*") ?: [] as $hw) {
        $name = trim((string)slurp("$hw/name"));
        if (!isset($rank[$name]) || ($best !== null && $rank[$name] >= $best[0])) {
            continue;
        }
        $file = "$hw/temp1_input";
        foreach (glob("$hw/temp*_label") ?: [] as $label) {
            if (preg_match('/package|tctl|tdie/i', (string)slurp($label))) {
                $file = str_replace('_label', '_input', $label);
                break;
            }
        }
        $raw = slurp($file);
        if ($raw !== null) {
            $best = [$rank[$name], (float)$raw / 1000];
        }
    }
    if ($best) {
        return round($best[1], 1);
    }
    // 2) thermal zones
    foreach (glob("$sys/class/thermal/thermal_zone*/temp") ?: [] as $zone) {
        $raw = slurp($zone);
        if ($raw !== null && (float)$raw > 0) {
            return round((float)$raw / 1000, 1);
        }
    }
    return 0.0;
}

/** Current CPU clock in MHz, averaged over all cores (cpufreq when available, else "cpu MHz" in /proc/cpuinfo). 0 = unknown. */
function cpu_clock_mhz(string $proc, string $sys): float
{
    $sum = 0.0;
    $n = 0;
    foreach (glob("$sys/devices/system/cpu/cpu[0-9]*/cpufreq/scaling_cur_freq") ?: [] as $file) {
        $raw = slurp($file);
        if ($raw !== null && (float)$raw > 0) {
            $sum += (float)$raw / 1000;
            $n++;
        }
    }
    if ($n === 0 && preg_match_all('/^cpu MHz\s*:\s*([\d.]+)/m', (string)slurp("$proc/cpuinfo"), $m)) {
        foreach ($m[1] as $mhz) {
            if ((float)$mhz > 0) {
                $sum += (float)$mhz;
                $n++;
            }
        }
    }
    return $n > 0 ? round($sum / $n) : 0.0;
}

// ───────────────────────── CPU NAME ─────────────────────────
/** "Intel(R) Core(TM) i5-8250U CPU @ 1.60GHz" -> "Intel Core i5-8250U" (host CPU, also inside Docker). */
function clean_cpu_name(string $model): string
{
    $model = preg_replace('/\((?:R|TM|r|tm)\)/', '', $model) ?? $model;
    $model = preg_replace('/@.*$/', '', $model) ?? $model;
    $model = preg_replace('/\b\d+(?:st|nd|rd|th) Gen\b/', '', $model) ?? $model;
    $model = preg_replace('/\b(?:CPU|Processor|\d+-Core)\b/', '', $model) ?? $model;
    $model = preg_replace('/\bwith Radeon.*$/', '', $model) ?? $model;
    return trim((string)preg_replace('/\s+/', ' ', $model), " ,");
}

function cpu_name(string $proc): string
{
    if (preg_match('/^model name\s*:\s*(.+)$/m', (string)slurp("$proc/cpuinfo"), $m)) {
        return clean_cpu_name($m[1]);
    }
    return '';   // ARM boards etc. have no "model name" line
}

// ───────────────────────── MEMORY / LOAD / UPTIME ─────────────────────────
function meminfo(string $proc): array
{
    $mem = [];
    if (preg_match_all('/^(\w+):\s+(\d+)/m', (string)slurp("$proc/meminfo"), $m)) {
        $mem = array_combine($m[1], array_map('intval', $m[2]));
    }
    $gb = fn(string $k): float => ($mem[$k] ?? 0) / 1024 / 1024;
    $total = $gb('MemTotal');
    $used  = $total - $gb('MemAvailable');
    $st    = $gb('SwapTotal');
    $su    = $st - $gb('SwapFree');
    return [
        'ram_u' => round($used, 1), 'ram_t' => round($total, 1), 'ram_p' => pct($used, $total),
        'swap_u' => round($su, 1), 'swap_t' => round($st, 1), 'swap_p' => pct($su, $st),
    ];
}

// ───────────────────────── RAID (mdadm) ─────────────────────────
/** Parse the text of /proc/mdstat into a list of arrays. */
function parse_mdstat(?string $text): array
{
    $arrays = [];
    if ($text === null) {
        return $arrays;
    }
    $lines = preg_split('/\R/', $text);
    for ($i = 0, $n = count($lines); $i < $n; $i++) {
        if (!preg_match('/^(md\d+)\s*:\s*(\w+)\s+(?:\([^)]*\)\s+)?(raid\d+|linear|multipath)?/', $lines[$i], $m)) {
            continue;
        }
        $a = ['name' => $m[1], 'state' => $m[2], 'level' => $m[3] ?? '?', 'devices' => null, 'working' => null,
              'health' => $m[2] === 'active' ? 'ok' : 'inactive', 'progress' => null, 'action' => null];
        // the next lines belong to this array until a blank line
        for ($j = $i + 1; $j < $n && trim($lines[$j]) !== ''; $j++) {
            if (preg_match('/\[(\d+)\/(\d+)\]\s*\[([U_]+)\]/', $lines[$j], $s)) {
                $a['devices'] = (int)$s[1];
                $a['working'] = (int)$s[2];
                if (strpos($s[3], '_') !== false) {
                    $a['health'] = 'degraded';
                }
            }
            if (preg_match('/(resync|recovery|reshape|check)\s*=\s*([\d.]+)%/', $lines[$j], $p)) {
                $a['action']   = $p[1];
                $a['progress'] = (float)$p[2];
                if ($a['health'] === 'ok') {
                    $a['health'] = $p[1] === 'check' ? 'checking' : 'syncing';
                }
            }
        }
        $arrays[] = $a;
    }
    return $arrays;
}

// ───────────────────────── MOUNTS / DISKS ─────────────────────────
function read_mounts(array $c): array
{
    $file = $c['mounts_file'];
    if ($file === null) {
        $file = is_readable($c['proc_root'] . '/1/mounts') ? $c['proc_root'] . '/1/mounts' : $c['proc_root'] . '/mounts';
    }
    $out = [];
    foreach (preg_split('/\R/', (string)slurp($file)) as $line) {
        $p = preg_split('/\s+/', $line);
        if (count($p) >= 3) {
            $out[] = ['dev' => $p[0], 'mount' => str_replace('\040', ' ', $p[1]), 'fs' => $p[2]];
        }
    }
    return $out;
}

function is_array_mount(array $m): bool
{
    return strpos($m['dev'], '/dev/md') === 0
        || in_array($m['fs'], ['zfs', 'btrfs', 'fuse.mergerfs', 'fuse.unionfs', 'mergerfs'], true);
}

function real_disks(array $mounts): array
{
    $ok = ['ext2', 'ext3', 'ext4', 'xfs', 'btrfs', 'zfs', 'f2fs', 'ntfs', 'ntfs3', 'exfat', 'fuse.mergerfs', 'fuse.unionfs', 'mergerfs'];
    $skip = '#^/(boot|snap|run|sys|proc|dev|var/lib/(docker|containers|kubelet)|etc/(hosts|hostname|resolv\.conf))#';
    $seen = $res = [];
    foreach ($mounts as $m) {
        if (!in_array($m['fs'], $ok, true) || preg_match($skip, $m['mount'])) {
            continue;
        }
        $key = $m['fs'] === 'btrfs' || $m['fs'] === 'zfs' ? $m['dev'] : $m['dev'] . $m['mount'];
        if (isset($seen[$key]) && $m['fs'] !== 'fuse.mergerfs') {
            continue;
        }
        $seen[$key] = true;
        $res[] = $m;
    }
    return array_slice($res, 0, 16);
}

/** Exact byte sizes of the filesystem at $path -> [total, free] or null. */
function disk_bytes(string $path): ?array
{
    $total = @disk_total_space($path);
    $free  = @disk_free_space($path);
    return ($total === false || $free === false || $total <= 0) ? null : [(float)$total, (float)$free];
}

/** The mount-table entry that contains $path (longest matching mount point). */
function mount_for(string $path, array $mounts): ?array
{
    $best = null;
    foreach ($mounts as $m) {
        $mp = rtrim($m['mount'], '/');
        if ($path === $m['mount'] || $mp === '' || strpos($path . '/', $mp . '/') === 0) {
            if ($best === null || strlen($m['mount']) > strlen($best['mount'])) {
                $best = $m;
            }
        }
    }
    return $best;
}

/**
 * True when $path is the very same filesystem as the system disk, so a "RAID" row would only repeat it.
 * Three independent checks, because in Docker "/" is an overlay while a bind-mounted folder shows the real
 * device underneath (so st_dev differs even though both are the same SSD):
 *   1. same st_dev;  2. same source device in the mount table;  3. identical total size and free space (+-0.5 %).
 * A real md array (/dev/mdN) is never treated as the system disk.
 */
function is_system_disk(string $path, string $system, array $mounts): bool
{
    $entry = mount_for($path, $mounts);
    if ($entry !== null && strpos($entry['dev'], '/dev/md') === 0) {
        return false;
    }
    $a = @stat($path);
    $b = @stat($system);
    if ($a && $b && $a['dev'] === $b['dev']) {
        return true;
    }
    $sysEntry = mount_for($system, $mounts);
    if ($entry !== null && $sysEntry !== null && strpos($entry['dev'], '/dev/') === 0 && $entry['dev'] === $sysEntry['dev']) {
        return true;
    }
    $x = disk_bytes($path);
    $y = disk_bytes($system);
    return $x !== null && $y !== null && abs($x[0] - $y[0]) / $y[0] < 0.005
        && abs($x[1] - $y[1]) / $y[0] < 0.005;
}

// ───────────────────────── NETWORK ─────────────────────────
function network(array $c): array
{
    $file = is_readable($c['proc_root'] . '/1/net/dev') ? $c['proc_root'] . '/1/net/dev' : $c['proc_root'] . '/net/dev';
    $rx = $tx = 0;
    $used = [];
    $virtual = '/^(lo|docker\d*|veth|br-|virbr|cni|flannel|cali|tun|tap|wt\d|tailscale|wg|zt|vmnet|ifb)/';
    foreach (preg_split('/\R/', (string)slurp($file)) as $line) {
        if (!preg_match('/^\s*([^:\s]+):\s*(\d+)\s+(?:\d+\s+){7}(\d+)/', $line, $m)) {
            continue;
        }
        [, $name, $r, $t] = $m;
        $wanted = $c['net_interfaces'] ? in_array($name, $c['net_interfaces'], true) : !preg_match($virtual, $name);
        if ($wanted) {
            $rx += (int)$r;
            $tx += (int)$t;
            $used[] = $name;
        }
    }
    return ['net_rx' => $rx, 'net_tx' => $tx, 'net_iface' => implode(',', $used)];
}

// ───────────────────────── SETTINGS SENT BY THE WIDGET ─────────────────────────
/**
 * The widget may ask for  ?system=<mount point>  and  ?net=eth0,eth1.  Only values that exist on this server are
 * accepted (the system path must be a mount point from the mount table), so nobody can probe arbitrary folders.
 * Switch it off with  'allow_client_settings' => false  (or STATS_ALLOW_CLIENT_SETTINGS=0).
 */
function apply_client_settings(array $c, array $get): array
{
    if (empty($c['allow_client_settings'])) {
        return $c;
    }
    $system = isset($get['system']) && is_string($get['system']) ? trim($get['system']) : '';
    if ($system !== '') {
        foreach (read_mounts($c) as $m) {
            if ($m['mount'] === $system) {
                $c['system_path'] = $system;
                break;
            }
        }
    }
    $net = isset($get['net']) && is_string($get['net']) ? trim($get['net']) : '';
    if ($net !== '') {
        $c['net_interfaces'] = array_slice(array_values(array_filter(array_map('trim', explode(',', $net)), 'strlen')), 0, 8);
    }
    return $c;
}

// ───────────────────────── BUILD THE ANSWER ─────────────────────────
function collect(array $c): array
{
    $proc = $c['proc_root'];
    $out = [
        'version'  => 2,
        'host'     => $c['hostname'] ?? (trim((string)slurp("$proc/sys/kernel/hostname")) ?: (string)gethostname()),
        'time'     => time(),
        'uptime'   => (int)floatval((string)slurp("$proc/uptime")),
        'cores'    => max(1, preg_match_all('/^processor\s*:/m', (string)slurp("$proc/cpuinfo"))),
        'load'     => array_map('floatval', array_slice(explode(' ', (string)slurp("$proc/loadavg")), 0, 3)),
        'cpu'      => cpu_percent($proc, (int)$c['cpu_sample_ms']),
        'cpu_mhz'  => cpu_clock_mhz($proc, $c['sys_root']),
        'temp'     => cpu_temperature($c['sys_root']),
        'cpu_name' => cpu_name($proc),
    ];
    $out += meminfo($proc);

    // system disk
    [$u, $t, $err] = disk_usage($c['system_path']);
    $out += ['ssd_u' => $u, 'ssd_t' => $t, 'ssd_p' => pct($u, $t)];

    // disks + RAID
    $mounts = read_mounts($c);
    $disks = [];
    foreach (real_disks($mounts) as $m) {
        [$du, $dt, $derr] = disk_usage($m['mount']);
        if ($derr === null) {
            $disks[] = ['mount' => $m['mount'], 'dev' => $m['dev'], 'fs' => $m['fs'],
                        'used' => $du, 'total' => $dt, 'percent' => pct($du, $dt), 'array' => is_array_mount($m),
                        'md' => preg_match('#^/dev/(md\d+)$#', $m['dev'], $mdm) ? $mdm[1] : null,
                        'system' => $m['mount'] === $c['system_path'] || is_system_disk($m['mount'], $c['system_path'], $mounts)];
        }
    }
    $raid = ['path' => null, 'ok' => false, 'present' => false, 'error' => null, 'arrays' => parse_mdstat(slurp("$proc/mdstat"))];
    $candidates = $c['raid_paths'];
    if ($c['auto_detect']) {
        foreach ($mounts as $m) {
            if (is_array_mount($m) && !in_array($m['mount'], $candidates, true) && $m['mount'] !== $c['system_path']
                && !preg_match('#^/(boot|run|var/lib)#', $m['mount'])) {
                $candidates[] = $m['mount'];
            }
        }
    }
    $errors = [];
    foreach ($candidates as $path) {
        [$ru, $rt, $rerr] = disk_usage($path);
        if ($rerr === null && is_system_disk($path, $c['system_path'], $mounts)) {
            $errors[] = "$path: same disk as the system path (no separate RAID/pool there)";
            continue;
        }
        if ($rerr === null) {
            $raid['path'] = $path;
            $raid['ok'] = true;
            $raid['present'] = true;
            $out += ['raid_u' => $ru, 'raid_t' => $rt, 'raid_p' => pct($ru, $rt)];
            break;
        }
        $errors[] = "$path: $rerr";
    }
    if (!$raid['ok']) {
        $raid['error'] = $errors ? implode('; ', $errors) : 'no RAID path configured or detected';
        $raid['present'] = false;
        $out += ['raid_u' => 0, 'raid_t' => 0, 'raid_p' => 0];
    }
    $out['raid']  = $raid;
    $out['disks'] = $disks;
    return $out + network($c);
}

// ───────────────────────── DEBUG PAGE ─────────────────────────
if (defined('STATS_WIDGET_LIB')) {
    return;   // unit tests include this file for its functions only
}
if (isset($_GET['debug'])) {
    $diag = [
        'php'          => PHP_VERSION,
        'user'         => function_exists('posix_geteuid') ? (posix_getpwuid(posix_geteuid())['name'] ?? '?') : get_current_user(),
        'in_docker'    => file_exists('/.dockerenv'),
        'open_basedir' => ini_get('open_basedir') ?: '(none)',
        'config'       => array_diff_key($CONFIG, ['token' => 1]),
        'proc_readable' => is_readable($CONFIG['proc_root'] . '/stat'),
        'mdstat'       => is_readable($CONFIG['proc_root'] . '/mdstat') ? 'readable' : 'not readable / no md arrays',
        'paths'        => [],
        'hints'        => [],
    ];
    $dbgMounts = read_mounts($CONFIG);
    foreach (array_merge([$CONFIG['system_path']], $CONFIG['raid_paths']) as $p) {
        [, , $e] = disk_usage($p);
        $diag['paths'][$p] = $e ?? 'ok';
        if ($e === null && $p !== $CONFIG['system_path'] && is_system_disk($p, $CONFIG['system_path'], $dbgMounts)) {
            $diag['paths'][$p] = 'ok, but this is the SAME disk as the system path - it is not shown as RAID';
            $diag['hints'][] = "$p is on the system disk. There is no separate RAID/pool here, so the widget hides the RAID row by itself; "
                . 'if you do have one, mount the real pool into the container.';
        }
    }
    $diag['cpu_name'] = cpu_name($CONFIG['proc_root']);
    if ($diag['in_docker']) {
        $diag['hints'][] = 'Running in Docker: the RAID must be mounted INTO this container (volume /your/host/raid:/raids:ro, see docs/SERVER_SETUP.md). '
            . 'Optional: for host-wide mounts also mount /proc (-v /proc:/host/proc:ro) and set STATS_PROC_ROOT=/host/proc.';
    }
    if (in_array('PHP cannot read the size (permissions or open_basedir)', $diag['paths'], true)) {
        $diag['hints'][] = 'Give the web-server user execute (x) permission on every parent folder of the RAID mount, and check open_basedir.';
    }
    echo json_encode($diag, JSON_PRETTY_PRINT | JSON_UNESCAPED_SLASHES);
    exit;
}

echo json_encode(collect(apply_client_settings($CONFIG, $_GET)), JSON_UNESCAPED_SLASHES | JSON_PARTIAL_OUTPUT_ON_ERROR);
