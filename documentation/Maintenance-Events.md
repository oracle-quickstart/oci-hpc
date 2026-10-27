# Instance Maintenance Events

The `mgmt` service manages OCI instance maintenance events (IMEs) as part of
its periodic metadata update. It lists the events in each node's compartment,
selects the applicable event for each known node, and stores the event details
in the management database. Events in `FAILED` or `CANCELED` state are ignored.
For a node with multiple events, `SCHEDULED`, `STARTED`, `PROCESSING`, and
`SUCCEEDED` events are considered in that order.

Slurm action is limited to `DOWNTIME_HOST_MAINTENANCE` and
`LIVE_HOST_MAINTENANCE` events. Other event types are recorded without
changing Slurm state. Before applying a policy, `mgmt` retrieves detailed event
metadata when necessary so it can use the OCI `faultId` values as maintenance
error codes.

## Maintenance policy

The controller installs the editable policy at
`/config/mgmt/maintenance.json`. The initial file is copied with `force: false`,
so later stack configuration runs preserve operator changes. If the file is
missing, unreadable, or invalid, `mgmt` keeps the existing behavior:

```json
{
  "default": {
    "drain": true,
    "schedule": true
  }
}
```

The deployed file supports full-line `#` comments. Each `drain` and
`schedule` value accepts `true`, `false`, or `"Healthcheck"`. Per-fault-code
settings override the default; when an event contains multiple configured fault
codes, the first matching code in sorted fault-ID order is used.

```jsonc
{
  "default": {
    "drain": false,
    "schedule": true
  },
  "fault_codes": {
    "FMSRDMA-0002-02": {
      "drain": "Healthcheck",
      "schedule": false
    }
  }
}
```

`"Healthcheck"` enables that individual action only when the node's latest
passive-healthcheck recommendation is not `Healthy`. A missing passive result
is treated as not unhealthy, so the action is not taken.

## Event handling

For a scheduled IME whose OCI window is more than five minutes away:

- `schedule: true` moves the OCI window to approximately five minutes from
  now.
- `schedule: false` leaves the OCI event unchanged. It does not cancel or
  unschedule the IME.

For scheduled, started, and processing IMEs:

- `drain: true` drains the Slurm node with an `OCI-IME::` reason.
- `drain: false` does not change Slurm state.
- An existing non-healthcheck Slurm drain is preserved. A healthcheck-owned
  drain is replaced with the `OCI-IME::` reason when draining is enabled.
- If a compute node is absent from Slurm, a required drain is deferred; a
  permitted OCI reschedule still occurs independently.

When an IME succeeds, `mgmt` resumes only nodes drained with an `OCI-IME::`
reason. It leaves drains owned by another workflow in place. `maintenance.json`
is the sole source of maintenance-event drain and scheduling policy.
