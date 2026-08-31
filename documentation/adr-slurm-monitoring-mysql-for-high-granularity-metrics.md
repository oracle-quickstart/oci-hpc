# Use MySQL for high-granularity Slurm monitoring metrics

## Context and Problem Statement

Slurm job monitoring needs to retain detailed job records and query them by fields such as Slurm job ID, user, account, partition, state, node, elapsed time, CPU, memory, and GPU usage. Should these high-granularity job records be stored directly in Prometheus, or should they be stored in MySQL and exposed to dashboards through SQL-backed exporters and Grafana queries?

In this repository, the `prometheus_targets` role adds node and infrastructure labels such as `cluster_name`, `availability_domain`, `compartment_id`, `hostname`, `ip`, `oci_name`, `ocid`, `rack_id`, `rail_id`, `role`, `serial`, and `shape`. These labels add useful filtering context and relatively remain static for the life of a deployed node. Prometheus is a good fit for those labels on low-cardinality operational metrics such as current node state, aggregate job counts, exporter health, and scrape duration.

The problem is different for per-job history. A label such as `slurm_job_id` changes every time a job is submitted. For example, a metric like `slurm_job_cpu_seconds{slurm_job_id="12345",cluster_name="example",hostname="cpu-1",partition="compute",state="COMPLETED"}` creates a distinct time series for that job and host combination. The static target labels are not the main issue; the job ID churn is.

Our clusters range from about 8 to 1000 nodes. If 50,000 jobs run in a day and each job emits one per-job series, `slurm_job_id` alone creates 50,000 new series per day. If the metric is per-job and per-node, the upper bound becomes `jobs x touched nodes`: 50,000 jobs across 8 nodes is up to 400,000 new series per day, and across 1000 nodes is up to 50,000,000 new series per day. That is before adding job array task ID, QoS, GPU type, exit code, or memory bucket. This churn increases Prometheus memory, index size, query cost, and retention pressure.

## Considered Options

  * Store detailed Slurm job history directly in Prometheus labels
  * Store detailed Slurm job history in MySQL and query it from Grafana/exporters
  * Store only coarse aggregates and omit detailed job history

## Decision Outcome

Chosen option: "Store detailed Slurm job history in MySQL and query it from Grafana/exporters", because it preserves detailed job-level analysis without turning unique job attributes into Prometheus labels and risking cardinality explosion.

Prometheus remains the source for current, aggregate, and low-cardinality operational metrics. MySQL is the source for high-granularity Slurm job history and dashboard queries that need filtering, grouping, and sorting over job records.

### Consequences

  * Good, because Prometheus remains focused on bounded-cardinality time series and stays healthier under large job volumes.
  * Good, because MySQL is better suited for indexed job-history queries by job ID, user, account, partition, time range, and state.
  * Good, because Grafana can still visualize detailed job data without requiring every job attribute to become a Prometheus label.
  * Bad, because monitoring now depends on a relational database in addition to Prometheus.
  * Bad, because deployment might take 15-20 mins longer when monitoring uses managed MySQL without Slurm HA.
