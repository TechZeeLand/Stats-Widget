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
echo "all PHP tests passed\n";
