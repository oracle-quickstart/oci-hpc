#!/usr/bin/env bash
# Sample systemd CPU/memory usage over 24h at 1-minute intervals; write CSV.
# Adds memory usage percent vs total system memory.
#
# Usage: ./exporter_usage.sh <service_name> <output.csv>
# Example: ./exporter_usages.sh dcgm-exporter.service dcgm_exporter_24h.csv
#
# CSV columns:
# timestamp_iso,service,cpu_sec_per_sec,single_core_pct,total_capacity_pct,mem_bytes,mem_pct_of_total,tasks,restarts

set -euo pipefail

SVC="${1:-}"
OUT="${2:-}"
if [[ -z "$SVC" || -z "$OUT" ]]; then
  echo "Usage: $0 <service_name> <output.csv>" >&2
  exit 1
fi

# Duration and interval
INTERVAL_SEC=60
SAMPLES=$((24 * 60))  # 24 hours of 1-minute samples

# Ensure locale uses dot as decimal separator
export LC_ALL=C
export LANG=C

CPUS=$(nproc)

# Total system memory in bytes (from /proc/meminfo)
if ! MEM_TOTAL_B=$(awk '/^MemTotal:/ {print $2*1024}' /proc/meminfo); then
  echo "Failed to read MemTotal from /proc/meminfo" >&2
  exit 1
fi
if [[ -z "${MEM_TOTAL_B}" || "${MEM_TOTAL_B}" -le 0 ]]; then
  echo "Invalid MemTotal: ${MEM_TOTAL_B}" >&2
  exit 1
fi

# Check service exists
if ! systemctl status "$SVC" >/dev/null 2>&1; then
  echo "Service not found: $SVC" >&2
  exit 1
fi

# Helper: read selected systemd properties once
read_props() {
  # Outputs: cpu_ns mem_bytes tasks restarts
  local cpu_ns mem tasks restarts
  mapfile -t props < <(systemctl show "$SVC" \
    -p CPUUsageNSec -p MemoryCurrent -p TasksCurrent -p NRestarts 2>/dev/null)

  cpu_ns=0; mem=0; tasks=0; restarts=0
  for p in "${props[@]}"; do
    case "$p" in
      CPUUsageNSec=*) cpu_ns="${p#*=}";;
      MemoryCurrent=*) mem="${p#*=}";;
      TasksCurrent=*) tasks="${p#*=}";;
      NRestarts=*) restarts="${p#*=}";;
    esac
  done
  [[ -z "${cpu_ns}" || "${cpu_ns}" = "n/a" ]] && cpu_ns=0
  [[ -z "${mem}" || "${mem}" = "n/a" ]] && mem=0
  [[ -z "${tasks}" || "${tasks}" = "n/a" ]] && tasks=0
  [[ -z "${restarts}" || "${restarts}" = "n/a" ]] && restarts=0

  echo "${cpu_ns} ${mem} ${tasks} ${restarts}"
}

now_ns() { date +%s%N; }

to_iso() { date -u -d "@$1" +%Y-%m-%dT%H:%M:%SZ; }

# Prepare output
TMP="$(mktemp "${OUT}.XXXX")"
cleanup() { mv -f "$TMP" "$OUT"; }
trap cleanup EXIT

# Header
echo "timestamp_iso,service,cpu_sec_per_sec,single_core_pct,total_capacity_pct,mem_bytes,mem_pct_of_total,tasks,restarts" > "$TMP"

# Initial baseline
t_prev_ns=$(now_ns)
read cpu_prev_ns mem_prev tasks_prev restarts_prev < <(read_props)

# Align to the next minute boundary for neat minute marks
curr_s=$(date +%s)
next_min=$(( (curr_s/60 + 1) * 60 ))
sleep_secs=$(( next_min - curr_s ))
sleep "$sleep_secs"

for ((i=1; i<=SAMPLES; i++)); do
  t1_ns=$(now_ns)
  read cpu_now_ns mem_now tasks_now restarts_now < <(read_props)
  t2_ns=$(now_ns)

  mid_ns=$(( (t1_ns + t2_ns) / 2 ))
  mid_s=$(( mid_ns / 1000000000 ))
  ts_iso=$(to_iso "$mid_s")

  # Compute CPU deltas
  delta_cpu_ns=0
  delta_t_ns=$(( t2_ns - t_prev_ns ))
  if (( cpu_now_ns >= cpu_prev_ns )); then
    delta_cpu_ns=$(( cpu_now_ns - cpu_prev_ns ))
  else
    delta_cpu_ns=0  # counter reset (service restarted)
  fi

  cpu_sec_per_sec="0.000000"
  if (( delta_t_ns > 0 )); then
    cpu_sec_per_sec=$(awk -v dcn="$delta_cpu_ns" -v dtn="$delta_t_ns" 'BEGIN { printf "%.6f", (dcn/1e9)/(dtn/1e9) }')
  fi
  single_core_pct=$(awk -v r="$cpu_sec_per_sec" 'BEGIN { printf "%.2f", r*100 }')
  total_capacity_pct=$(awk -v r="$cpu_sec_per_sec" -v n="$CPUS" 'BEGIN { printf "%.2f", (r/n)*100 }')

  # Memory percent of total
  mem_pct_of_total=$(awk -v m="$mem_now" -v mt="$MEM_TOTAL_B" 'BEGIN { if (mt>0) printf "%.2f", (m/mt)*100; else print "0.00" }')

  # Write CSV row
  echo "${ts_iso},${SVC},${cpu_sec_per_sec},${single_core_pct},${total_capacity_pct},${mem_now},${mem_pct_of_total},${tasks_now},${restarts_now}" >> "$TMP"

  # Update baselines
  t_prev_ns=$t2_ns
  cpu_prev_ns=$cpu_now_ns

  # Sleep until next minute boundary
  now_s=$(date +%s)
  next_tick=$(( (now_s/60 + 1) * 60 ))
  sleep_for=$(( next_tick - now_s ))
  if (( sleep_for > 0 )); then
    sleep "$sleep_for"
  fi
done

echo "Wrote ${SAMPLES} samples to ${OUT}"

