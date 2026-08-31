# GPU Failure Risk Score (beta)

This technical summary explains how to interpret the **GPU Failure Risk Score (beta)** dashboard. The dashboard is intended for operators investigating GPU reliability symptoms on OCI HPC clusters.

The dashboard is available from the Compute Node Health panel tile menu in Command Center. It shows one gauge per NVIDIA GPU on the selected node and a time series panel that shows which signal family is contributing to the score. This beta feature currently uses NVIDIA/DCGM and PCIe metrics.

## What the score means

The score is a current-state risk indicator from 0 to 100. It is not a forecast, machine learning model, probability of failure, alert severity, or automated remediation trigger. Treat it as an investigation aid that helps identify GPUs with active reliability symptoms.

Prometheus calculates several per-GPU component scores and records the final `node_gpu_failure_risk_score` as the maximum component value. Scores are not added together. A GPU with one severe signal should stand out immediately, while multiple moderate signals do not inflate the final score beyond the strongest observed signal.

## Gauge interpretation

| Score | Gauge color | Interpretation |
| ---: | --- | --- |
| 0 - 29 | Green | No current high-risk signal, or only a low-severity transient signal. Continue normal monitoring. |
| 30 - 59 | Yellow | Investigate when repeated or correlated with workload failures. Check the Risk Signal Contributors panel to see the source. |
| 60 - 84 | Orange | High-risk signal. Review GPU health, PCIe status, thermal behavior, and recent Xid/ECC activity for the specific GPU. |
| 85 - 100 | Red | Severe current signal. Prioritize operator review before returning the GPU or node to heavy workloads. |

## Signal contributors

The Risk Signal Contributors panel shows the component families used to calculate the gauge. Each contributor is a separate Prometheus recording rule. The final gauge uses the highest contributor value for the same `hostname`, `oci_name`, `gpu`, and `UUID`.

Use this panel before acting on the gauge. The same final score can come from very different causes, and the operational response should follow the contributor that is highest.

| Contributor | Main source metrics | How it scores | What it usually means |
| --- | --- | --- | --- |
| `xid` | `DCGM_FI_DEV_XID_ERRORS` | Xid 79 = 100; reset/reboot-class Xids = 70; critical Xids = 60; other Xids = 25 | Driver or GPU-reported error event. Severity depends heavily on the Xid code. |
| `pcie-replay` | `DCGM_FI_DEV_PCIE_REPLAY_COUNTER` | 15-minute increase multiplied by 5, capped at 80 | GPU-side PCIe link retries are increasing. This can point to link quality, slot, cable, board, or platform issues. |
| `pcie-aer` | `pcie_aer_correctable_error_count`, `pcie_aer_nonfatal_error_count`, `pcie_aer_fatal_error_count`, `pcie_bus_inaccessible_status`, `pcie_bus_linkwidth_status` | Correctable AER = increase times 2, capped at 40; nonfatal AER = increase times 25, capped at 80; fatal AER = 100; inaccessible bus = 100; link-width issue = 80 | Host-side PCIe reliability or enumeration problem. Fatal and bus-inaccessible states are severe. |
| `dcgm-health` | `DCGM_EXP_GPU_HEALTH_STATUS` | PCIE watch = 90; DRIVER watch = 80; NVLINK watch = 45; POWER watch = 35; THERMAL watch = 35 | DCGM health subsystem has marked a watched component unhealthy. |
| `power-thermal` | `DCGM_FI_DEV_THERMAL_VIOLATION`, `DCGM_FI_DEV_POWER_VIOLATION`, `DCGM_FI_DEV_BOARD_LIMIT_VIOLATION`, `DCGM_FI_DEV_GPU_TEMP`, `DCGM_FI_DEV_SLOWDOWN_TEMP` | Thermal violation = capped at 40; power violation = capped at 30; board-limit violation = capped at 30; temperature headroom = capped at 60; sustained temperature above 90 percent of slowdown temperature = 85 | GPU is operating near or inside throttling/thermal stress conditions. |
| `memory` | `DCGM_FI_DEV_ROW_REMAP_FAILURE`, `DCGM_FI_DEV_ROW_REMAP_PENDING`, `DCGM_FI_DEV_UNCORRECTABLE_REMAPPED_ROWS`, `DCGM_FI_DEV_CORRECTABLE_REMAPPED_ROWS`, `DCGM_FI_DEV_ECC_DBE_VOL_TOTAL`, `DCGM_FI_DEV_ECC_DBE_AGG_TOTAL`, `DCGM_FI_DEV_ECC_SBE_VOL_TOTAL`, `DCGM_FI_DEV_ECC_SBE_AGG_TOTAL` | Row remap failure = 90; pending row remap = 60; new uncorrectable remap in 24 hours = 70; new correctable remap in 24 hours = 30; new DBE in 1 hour = 80; SBE rate = rate times 10, capped at 40 | Memory reliability signal. DBE, row remap failure, and uncorrectable remaps deserve close review. |
| `telemetry` | Timestamp freshness of `DCGM_FI_DEV_GPU_TEMP` | No update for more than five minutes = 80 | GPU telemetry is stale, so the health picture may be incomplete. |

### `xid`

The `xid` contributor groups DCGM Xid errors by operational severity. Xid 79 receives a score of 100 because it indicates the GPU has fallen off the bus. Reset/reboot-class Xids receive 70 because they often require active recovery. Critical Xids receive 60. Other Xids receive 25 so they are visible without immediately dominating more severe signals.

When `xid` is highest, check the exact Xid code, timestamp, affected GPU UUID, and whether the event repeats under workload. Correlate with `dmesg`, DCGM health, Slurm job failures, and any node-level health check output.

### `pcie-replay`

The `pcie-replay` contributor tracks growth in the GPU-side PCIe replay counter over the last 15 minutes. Replays are retries on the PCIe link. A small transient increase may be noise, but steady growth indicates the link is struggling and can precede stronger PCIe or GPU symptoms.

When `pcie-replay` is highest, compare the affected GPU with the other GPUs on the same node. Look for repeated increases, workload correlation, PCIe AER messages, link-width changes, and any platform-level maintenance or hardware events.

### `pcie-aer`

The `pcie-aer` contributor comes from host-side PCIe AER and bus status checks. Correctable errors are weighted lower and capped at 40. Nonfatal errors are weighted higher and capped at 80. Fatal AER errors and bus-inaccessible status drive the score to 100. Link-width issues drive the score to 80 because a degraded link can affect performance and reliability even when the GPU is still visible.

When `pcie-aer` is highest, inspect the host PCIe error logs and confirm whether the GPU is still enumerated. Fatal AER, bus inaccessible, or repeated nonfatal AER should be treated as stronger evidence than an isolated correctable error.

### `dcgm-health`

The `dcgm-health` contributor reflects DCGM's health watch status. PCIE health failures score 90 and DRIVER failures score 80 because they often indicate the GPU or software stack is no longer in a reliable operating state. NVLINK, POWER, and THERMAL watches score lower because they can also represent degraded or environmental states that need correlation.

When `dcgm-health` is highest, open the GPU Health dashboard for the same node and GPU. Confirm which watch failed, whether it is persistent, and whether it aligns with Xid, PCIe, thermal, or workload symptoms.

### `power-thermal`

The `power-thermal` contributor combines recent violation counters with temperature headroom. Thermal, power, and board-limit violation counters are calculated over 15 minutes. Temperature headroom rises when GPU temperature approaches the slowdown temperature. Sustained temperature above 90 percent of slowdown temperature for three minutes scores 85.

When `power-thermal` is highest, inspect GPU temperature, power draw, utilization, fan/cooling behavior, workload placement, and whether neighboring GPUs show the same pattern. A high score here is not automatically a failed GPU, but it means the GPU is running close to conditions that can create instability or throttling.

### `memory`

The `memory` contributor focuses on GPU memory reliability. Row remap failure scores 90, pending row remap scores 60, and new uncorrectable remapped rows over 24 hours score 70. New double-bit ECC errors over one hour score 80. Correctable remaps and single-bit ECC rates are lower severity but remain visible because they can provide useful context when they increase.

When `memory` is highest, inspect ECC and row remap history for the GPU UUID. DBE, row remap failure, and uncorrectable remap signals should be treated as stronger evidence than isolated correctable events.

### `telemetry`

The `telemetry` contributor fires when `DCGM_FI_DEV_GPU_TEMP` has not updated for more than five minutes. It does not mean the GPU has failed by itself. It means the monitoring signal is stale enough that the dashboard cannot trust the rest of the current GPU picture.

When `telemetry` is highest, check DCGM exporter, node exporter health, Prometheus scrape status, and whether the node or GPU is unavailable. Resolve stale telemetry before interpreting a low or missing risk score as healthy.

## How to investigate

When a GPU has a nonzero score, start with the highest series in **Risk Signal Contributors**. Then use the existing GPU Health, GPU Metrics, Host Metrics, and logs for the same `hostname`, `oci_name`, `gpu`, and `UUID` labels.

A single yellow value can be transient. Repeated orange or red values, especially with concrete Xid, PCIe fatal, bus inaccessible, row remap, ECC DBE, or thermal-trip symptoms, should be treated as stronger evidence of a GPU or node reliability issue.

## Scope and limitations

- The beta score is calculated from currently observed telemetry only.
- It does not forecast future failures.
- It does not automatically drain, reboot, reset, or terminate nodes.
- It should be interpreted together with node health, workload symptoms, system logs, and existing GPU health dashboards.
