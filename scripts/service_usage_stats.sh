#!/usr/bin/env bash
# Sample systemd service CPU and memory usage without changing service state.

set -euo pipefail

usage() {
  cat <<'EOF'
Usage:
  service_usage_stats.sh <service_name> <output.csv>
  service_usage_stats.sh [options]

Options:
  --service SERVICE           Service to sample; may be specified more than once
  --output FILE               CSV output path
  --duration-hours HOURS      Collection duration; default: 24
  --interval-seconds SECONDS  Sampling interval; default: 60
  --help                      Show this help

The original two-positional-argument form remains supported and samples one
service for 24 hours at 60-second intervals.
EOF
}

SERVICES=()
OUT=""
DURATION_HOURS=24
INTERVAL_SEC=60

if [[ $# -eq 2 && "$1" != --* ]]; then
  SERVICES=("$1")
  OUT="$2"
else
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --service)
        [[ $# -ge 2 ]] || { echo "Missing value for --service" >&2; exit 1; }
        SERVICES+=("$2")
        shift 2
        ;;
      --output)
        [[ $# -ge 2 ]] || { echo "Missing value for --output" >&2; exit 1; }
        OUT="$2"
        shift 2
        ;;
      --duration-hours)
        [[ $# -ge 2 ]] || { echo "Missing value for --duration-hours" >&2; exit 1; }
        DURATION_HOURS="$2"
        shift 2
        ;;
      --interval-seconds)
        [[ $# -ge 2 ]] || { echo "Missing value for --interval-seconds" >&2; exit 1; }
        INTERVAL_SEC="$2"
        shift 2
        ;;
      --help|-h)
        usage
        exit 0
        ;;
      *)
        echo "Unknown option: $1" >&2
        usage >&2
        exit 1
        ;;
    esac
  done
fi

is_positive_number() {
  awk -v value="$1" 'BEGIN { exit !(value ~ /^[0-9]+([.][0-9]+)?$/ && value > 0) }'
}

for value in "$DURATION_HOURS" "$INTERVAL_SEC"; do
  is_positive_number "$value" || { echo "Expected a positive number: $value" >&2; exit 1; }
done

if [[ ${#SERVICES[@]} -eq 0 || -z "$OUT" ]]; then
  usage >&2
  exit 1
fi

for service in "${SERVICES[@]}"; do
  if ! systemctl status "$service" >/dev/null 2>&1; then
    echo "Service not found or not active: $service" >&2
    exit 1
  fi
done

export LC_ALL=C
export LANG=C

CPUS=$(nproc)
MEM_TOTAL_B=$(awk '/^MemTotal:/ {print $2*1024}' /proc/meminfo)
if [[ -z "$MEM_TOTAL_B" || "$MEM_TOTAL_B" -le 0 ]]; then
  echo "Failed to read total memory from /proc/meminfo" >&2
  exit 1
fi

SAMPLES=$(awk -v hours="$DURATION_HOURS" -v interval="$INTERVAL_SEC" \
  'BEGIN { value=(hours*3600)/interval; print int(value) == value ? int(value) : int(value)+1 }')
if [[ "$SAMPLES" -lt 1 ]]; then
  echo "Collection duration must contain at least one sample" >&2
  exit 1
fi

read_props() {
  local service="$1"
  local cpu_ns=0 mem=0 tasks=0 restarts=0 property
  local -a props
  mapfile -t props < <(systemctl show "$service" \
    -p CPUUsageNSec -p MemoryCurrent -p TasksCurrent -p NRestarts 2>/dev/null)

  for property in "${props[@]}"; do
    case "$property" in
      CPUUsageNSec=*) cpu_ns="${property#*=}" ;;
      MemoryCurrent=*) mem="${property#*=}" ;;
      TasksCurrent=*) tasks="${property#*=}" ;;
      NRestarts=*) restarts="${property#*=}" ;;
    esac
  done
  [[ -z "$cpu_ns" || "$cpu_ns" == n/a ]] && cpu_ns=0
  [[ -z "$mem" || "$mem" == n/a ]] && mem=0
  [[ -z "$tasks" || "$tasks" == n/a ]] && tasks=0
  [[ -z "$restarts" || "$restarts" == n/a ]] && restarts=0
  echo "$cpu_ns $mem $tasks $restarts"
}

percentile_99() {
  sort -n | awk '{ values[NR]=$1 } END {
    if (NR == 0) { print 0; exit }
    index=int((NR-1)*0.99)+1
    print values[index]
  }'
}

now_ns() { date +%s%N; }
to_iso() { date -u -d "@$1" +%Y-%m-%dT%H:%M:%SZ; }

declare -A CPU_PREV_NS
declare -a COMBINED_CPU_VALUES COMBINED_MEM_VALUES

TMP=$(mktemp "${OUT}.XXXX")
cleanup() { mv -f "$TMP" "$OUT"; }
trap cleanup EXIT

echo "timestamp_iso,service,cpu_sec_per_sec,single_core_pct,total_capacity_pct,mem_bytes,mem_pct_of_total,tasks,restarts" > "$TMP"

for service in "${SERVICES[@]}"; do
  read -r cpu_ns _ < <(read_props "$service")
  CPU_PREV_NS["$service"]="$cpu_ns"
done
time_prev_ns=$(now_ns)

echo "Sampling ${SERVICES[*]} every ${INTERVAL_SEC}s for ${DURATION_HOURS}h (${SAMPLES} samples)"

for ((sample=1; sample<=SAMPLES; sample++)); do
  sleep "$INTERVAL_SEC"
  time_now_ns=$(now_ns)
  delta_time_ns=$((time_now_ns - time_prev_ns))
  timestamp=$(to_iso "$((time_now_ns / 1000000000))")
  combined_cpu="0"
  combined_mem=0

  for service in "${SERVICES[@]}"; do
    read -r cpu_now_ns mem_now tasks_now restarts_now < <(read_props "$service")
    cpu_delta_ns=0
    if (( cpu_now_ns >= CPU_PREV_NS["$service"] )); then
      cpu_delta_ns=$((cpu_now_ns - CPU_PREV_NS["$service"]))
    fi
    cpu_rate=$(awk -v cpu="$cpu_delta_ns" -v elapsed="$delta_time_ns" \
      'BEGIN { if (elapsed > 0) printf "%.6f", cpu/elapsed; else print "0.000000" }')
    single_core_pct=$(awk -v rate="$cpu_rate" 'BEGIN { printf "%.2f", rate*100 }')
    total_capacity_pct=$(awk -v rate="$cpu_rate" -v cpus="$CPUS" \
      'BEGIN { printf "%.2f", (rate/cpus)*100 }')
    mem_pct_of_total=$(awk -v mem="$mem_now" -v total="$MEM_TOTAL_B" \
      'BEGIN { printf "%.2f", (mem/total)*100 }')

    echo "${timestamp},${service},${cpu_rate},${single_core_pct},${total_capacity_pct},${mem_now},${mem_pct_of_total},${tasks_now},${restarts_now}" >> "$TMP"
    combined_cpu=$(awk -v total="$combined_cpu" -v value="$cpu_rate" \
      'BEGIN { printf "%.6f", total+value }')
    combined_mem=$((combined_mem + mem_now))
    CPU_PREV_NS["$service"]="$cpu_now_ns"
  done

  COMBINED_CPU_VALUES+=("$combined_cpu")
  COMBINED_MEM_VALUES+=("$combined_mem")
  time_prev_ns="$time_now_ns"
done

p99_cpu_vcpus=$(printf '%s\n' "${COMBINED_CPU_VALUES[@]}" | percentile_99)
p99_mem_bytes=$(printf '%s\n' "${COMBINED_MEM_VALUES[@]}" | percentile_99)
p99_mem_gib=$(awk -v bytes="$p99_mem_bytes" 'BEGIN { printf "%.3f", bytes/(1024^3) }')

echo "Wrote ${SAMPLES} samples per service to ${OUT}"
echo "Observed p99 combined services: ${p99_cpu_vcpus} logical CPUs, ${p99_mem_gib} GiB memory"
