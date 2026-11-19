<?php
// SPDX-License-Identifier: AGPL-3.0-or-later
// Run:  php tests/mdstat_test.php
define('STATS_WIDGET_LIB', true);
require __DIR__ . '/../server/stats.php';

function check($cond, $msg) { if (!$cond) { fwrite(STDERR, "FAIL: $msg\n"); exit(1); } echo "ok  $msg\n"; }

$healthy = "Personalities : [raid1] [raid5]\nmd0 : active raid5 sdd1[3] sdc1[2] sdb1[1] sda1[0]\n      11720661504 blocks super 1.2 level 5, 512k chunk, algorithm 2 [4/4] [UUUU]\n      bitmap: 0/22 pages\n\nunused devices: <none>\n";
$a = parse_mdstat($healthy);
check(count($a) === 1 && $a[0]['level'] === 'raid5' && $a[0]['health'] === 'ok' && $a[0]['devices'] === 4, 'healthy raid5');

$degraded = "md1 : active raid1 sdb1[1]\n      976630464 blocks super 1.2 [2/1] [_U]\n\n";
$a = parse_mdstat($degraded);
check($a[0]['health'] === 'degraded' && $a[0]['working'] === 1, 'degraded raid1');

$rebuild = "md0 : active raid5 sdd1[3] sdc1[2] sdb1[1] sda1[0]\n      11720661504 blocks super 1.2 level 5 [4/3] [UUU_]\n      [==>.....]  recovery = 12.6% (493000000/3906887168) finish=300.2min speed=100000K/sec\n\n";
$a = parse_mdstat($rebuild);
check($a[0]['health'] === 'degraded' && $a[0]['action'] === 'recovery' && $a[0]['progress'] === 12.6, 'rebuilding raid5');

$resync = "md2 : active raid1 sdc1[1] sdd1[0]\n      100 blocks [2/2] [UU]\n      [=>...]  resync = 40.0% (1/2) finish=1min speed=1K/sec\n\n";
$a = parse_mdstat($resync);
check($a[0]['health'] === 'syncing', 'resync of a complete array is "syncing", not degraded');

check(parse_mdstat(null) === [] && parse_mdstat("Personalities :\nunused devices: <none>\n") === [], 'no arrays');
check(pct(1, 4) === 25.0 && pct(1, 0) === 0.0, 'pct() and division by zero');

// CPU name cleaning
check(clean_cpu_name('Intel(R) Core(TM) i5-8250U CPU @ 1.60GHz') === 'Intel Core i5-8250U', 'cpu name: Intel');
check(clean_cpu_name('AMD Ryzen 5 5600G with Radeon Graphics') === 'AMD Ryzen 5 5600G', 'cpu name: AMD');
check(clean_cpu_name('') === '', 'cpu name: empty');

// RAID row must never repeat the system disk
$mounts = [
    ['dev' => 'overlay',        'mount' => '/',      'fs' => 'overlay'],
    ['dev' => '/dev/nvme0n1p2', 'mount' => '/raids', 'fs' => 'ext4'],
    ['dev' => '/dev/md0',       'mount' => '/pool',  'fs' => 'ext4'],
];
check(mount_for('/raids/sub', $mounts)['mount'] === '/raids', 'mount_for: longest prefix');
check(mount_for('/raidsX', $mounts)['mount'] === '/', 'mount_for: no false prefix match');
check(is_system_disk('/pool', '/', $mounts) === false, 'a /dev/md mount is never the system disk');
check(is_system_disk('/tmp', '/tmp', $mounts) === true, 'same path = same disk');
$sys = [['dev' => '/dev/nvme0n1p2', 'mount' => '/', 'fs' => 'ext4'], ['dev' => '/dev/nvme0n1p2', 'mount' => '/raids', 'fs' => 'ext4']];
check(is_system_disk('/raids', '/', $sys) === true, 'bind mount of the same source device is the system disk');

// settings sent by the widget
check(safe_path('/raids/') === '/raids' && safe_path('/') === '/', 'safe_path: normal paths');
check(safe_path('raids') === null && safe_path('/a/../etc') === null && safe_path("/a\0b") === null && safe_path('') === null, 'safe_path: relative / traversal / NUL / empty rejected');
check(safe_path('/' . str_repeat('a', 300)) === null, 'safe_path: too long');
check(safe_nic('enp3s0') === 'enp3s0' && safe_nic('br0.10') === 'br0.10' && safe_nic('a b') === null && safe_nic('x;rm') === null, 'safe_nic');
$on = ['allow_client_config' => true];
$o = client_overrides($on, ['paths' => ['/raids', '/raids/', '../x', '/mnt/m'], 'system' => '/', 'nic' => 'eth0,eth1']);
check($o['paths'] === ['/raids', '/mnt/m'] && $o['system'] === '/' && $o['nic'] === ['eth0', 'eth1'], 'overrides: arrays and comma strings, duplicates and bad values dropped');
check(client_overrides($on, ['paths' => ['relative']])['paths'] === null, 'overrides: nothing valid -> server default');
check(client_overrides(['allow_client_config' => false], ['paths' => ['/raids']]) === ['paths' => null, 'system' => null, 'nic' => null], 'overrides: switched off');
check(count(request_list(array_map(fn($i) => "/p$i", range(1, 20)), 'safe_path', 6)) === 6, 'overrides: at most 6 paths');

// pools
check(pool_kind(['dev' => '/dev/md0', 'mount' => '/r', 'fs' => 'ext4']) === 'raid', 'kind: md');
check(pool_kind(['dev' => 'tank', 'mount' => '/tank', 'fs' => 'zfs']) === 'zfs' && pool_kind(null) === 'disk', 'kind: zfs / plain');
$arrs = parse_mdstat($healthy . "\nmd1 : active raid1 sdb1[1] sda1[0]\n      10 blocks [2/1] [_U]\n\n");
check(md_for_entry(['dev' => '/dev/md1', 'mount' => '/x', 'fs' => 'ext4'], $arrs)['health'] === 'degraded', 'md_for_entry: right array');
check(md_for_entry(['dev' => '/dev/sda1', 'mount' => '/x', 'fs' => 'ext4'], $arrs) === null, 'md_for_entry: not an array');
if (is_dir('/dev/shm') && @disk_total_space('/dev/shm') > 0) {
    $c = ['system_path' => '/', 'raid_paths' => ['/nope'], 'auto_detect' => false];
    $notes = [];
    $p = storage_pools($c, [], [], ['/dev/shm', '/definitely/missing'], $notes);
    check(count($p) === 2 && $p[0]['ok'] === true && $p[1]['ok'] === false, 'explicit paths: a real one and a missing one (shown as an error row)');
    $p = storage_pools($c, [], [], null, $notes);
    check($p === [], 'server default path missing and no RAID known: no row');
}
check(is_array(cpu_clock('/proc', '/sys')) && count(cpu_clock('/proc', '/sys')) === 2, 'cpu_clock returns [current, max]');
echo "all PHP tests passed\n";
