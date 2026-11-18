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
echo "all PHP tests passed\n";
