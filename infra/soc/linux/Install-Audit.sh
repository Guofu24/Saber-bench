#!/usr/bin/env bash
set -euo pipefail
if [[ "${1:-}" != "--on-target" || "$(id -u)" != 0 ]]; then
  echo 'Run as root with --on-target on a dedicated Linux lab VM.' >&2; exit 2
fi
script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
command -v auditctl >/dev/null || { echo 'Install auditd through the guest package manager first.' >&2; exit 2; }
install -d -m 0750 /var/lib/saber/workspace
install -m 0600 "$script_dir/saber.rules" /etc/audit/rules.d/70-saber.rules
augenrules --load
auditctl -l
echo 'Kernel rules installed. Run saber.lab.logship with --source audit against /var/log/audit using a scoped collector token.'
