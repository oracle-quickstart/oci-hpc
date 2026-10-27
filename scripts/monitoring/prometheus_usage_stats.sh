#!/bin/bash
PROM_URL="http://localhost:9090"

# Function to query and get raw value
query() {
  curl -s --data-urlencode "query=$1" "$PROM_URL/api/v1/query" | jq -r '.data.result[0].value[1] // empty'
}

# Function to convert bytes to human readable
human_bytes() {
  local bytes=${1%.*}  # Strip decimal
  if [[ -z "$bytes" || "$bytes" == "null" ]]; then
    echo "N/A"
  else
    numfmt --to=iec-i --suffix=B "$bytes" 2>/dev/null || echo "${bytes} bytes"
  fi
}

echo "=== Prometheus TSDB Status ==="

# Current size
SIZE_BYTES=$(query 'prometheus_tsdb_storage_blocks_bytes')
echo "Current TSDB Size: $(human_bytes $SIZE_BYTES)"

# Head block size
HEAD_SIZE=$(query 'prometheus_tsdb_head_chunks_storage_size_bytes')
echo "Head Block Size: $(human_bytes $HEAD_SIZE)"

# WAL size
WAL_SIZE=$(query 'prometheus_tsdb_wal_storage_size_bytes')
echo "WAL Size: $(human_bytes $WAL_SIZE)"

# Daily growth
DAILY_GROWTH=$(query 'increase(prometheus_tsdb_storage_blocks_bytes[24h])')
echo "Daily Growth: $(human_bytes $DAILY_GROWTH)"

# Series count - use printf to handle scientific notation
SERIES=$(query 'prometheus_tsdb_head_series')
printf "Active Series: %.0f\n" "$SERIES" 2>/dev/null || echo "Active Series: $SERIES"

# Samples/sec
SAMPLES_SEC=$(query 'rate(prometheus_tsdb_head_samples_appended_total[5m])')
printf "Ingestion Rate: %.0f samples/sec\n" "$SAMPLES_SEC" 2>/dev/null || echo "Ingestion Rate: $SAMPLES_SEC"

# 30-day projection
PROJECTED=$(query 'predict_linear(prometheus_tsdb_storage_blocks_bytes[7d], 30 * 24 * 3600)')
echo "30-Day Projection: $(human_bytes $PROJECTED)"
