#!/bin/sh
# Benign lab workload: emits Sysmon-like JSON telemetry events to a shared volume.
# There is NO attack behaviour here — every event is a benign process/file action, so the output
# is safe to ingest and label as benign baseline telemetry (saber.evaldata event_log importer).
set -eu

OUT=/telemetry/events.jsonl
host=$(hostname)
iters=${SABER_LAB_ITERS:-30}
interval=${SABER_LAB_INTERVAL:-2}

i=0
while [ "$i" -lt "$iters" ]; do
  ts=$(date -u +%Y-%m-%dT%H:%M:%SZ)
  # EventID 1 = process create (benign /usr/bin/true), EventID 11 = file create+delete in tmp.
  printf '{"UtcTime":"%s","Hostname":"%s","Channel":"Microsoft-Windows-Sysmon/Operational","EventID":1,"Image":"/usr/bin/true","CommandLine":"true","User":"labuser"}\n' "$ts" "$host" >> "$OUT"
  scratch="/tmp/scratch.$i"
  : > "$scratch"
  printf '{"UtcTime":"%s","Hostname":"%s","Channel":"Microsoft-Windows-Sysmon/Operational","EventID":11,"TargetFilename":"%s"}\n' "$ts" "$host" "$scratch" >> "$OUT"
  rm -f "$scratch"
  i=$((i + 1))
  sleep "$interval"
done

printf '{"UtcTime":"%s","Hostname":"%s","Channel":"saber-lab","EventID":0,"Message":"benign workload complete"}\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$host" >> "$OUT"
