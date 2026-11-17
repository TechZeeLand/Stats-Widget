# Contributing

Thanks for helping! Bug reports, distro testing, translations of the docs and pull requests are all welcome.
By participating you agree to the [Code of Conduct](CODE_OF_CONDUCT.md). By contributing you agree that your work is
licensed under the project's license (AGPL-3.0-or-later).

## The most useful contribution: test your distro
The installers for `rhel`, `arch` and `suse` are written from package documentation and could not be run by the author.
Run the one-line installer, then `stats-widget doctor`, and open an issue with the result (use the **Distro report** template).

## Project layout
```
install.sh            one-line bootstrap: detects the distro family, runs distros/<family>/install.sh
distros/<family>/     package list + tweaks for one distro family
lib/common.sh         shared installer code (Rust, building eww, copying the widget)
widget/               what gets installed to ~/.local/share/stats-widget
  eww.yuck            layout            eww.scss   look & feel
  scripts/*.py        one data source each (server, pcstats, weather, clock, calendar_grid), configure.py (GUI), move.py
  bin/stats-widget    the command-line tool
server/stats.php      the endpoint for the server column
docs/                 user documentation
tests/                unit tests
```

## Development setup
```bash
git clone https://github.com/TechZeeLand/Stats-Widget && cd Stats-Widget
export STATS_WIDGET_CONFIG=/tmp/sw/config.toml          # keep your real config untouched
widget/bin/stats-widget start                           # runs straight from the checkout
widget/bin/stats-widget logs
```
Each script prints JSON and can be run alone: `python3 widget/scripts/pcstats.py`.
Test the server script without a web server: `php -r '$_GET=[]; include "server/stats.php";'`.

## Before you open a pull request
```bash
python3 -m unittest discover -s tests -v     # unit tests
php tests/mdstat_test.php                    # RAID parser test (needs php-cli)
shellcheck install.sh uninstall.sh lib/*.sh distros/*/install.sh widget/bin/stats-widget
php -l server/stats.php
```
CI runs the same checks. Please also:
* keep scripts dependency-free (Python standard library + PyGObject only; PHP without extensions),
* stay compatible with Python 3.8+ and PHP 7.4+,
* add your name and a line to `CHANGELOG.md`,
* attach a screenshot for visual changes (the default must stay 795 × 475 px; check it at 60 % and 200 % too).

## Commit style
Short imperative subject (`Add swap row to server column`), details in the body if needed.
