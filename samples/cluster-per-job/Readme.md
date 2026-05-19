# Cluster per job
This folder is an example of how one can leverage `mgmt` to create a wrapper in order to create one cluster per job. This is also a workaround for "On Demand" nodes feature which does not work consistently when used with Compute Clusters (RDMA communication).

## Prerequisites

### `mgmt` prerequisites
Create a new configuration for cluster per job submission.

ex:
```
mgmt configurations create from-existing --configuration default --name perjob
mgmt configurations update --name perjob --fields hostname_convention="TEST"
```

Make sure Slurm is updated: 
```
sudo mgmt configurations update-slurm
```

### Submission file requirements
The Slurm submission file must contain the following flags for number of nodes and constraint. This is needed by the wrapper:

```
# number of required nodes
#SBATCH --nodes or #SBATCH -N

# constraint name. This is the name of the configuration created in mgmt
#SBATCH --constraint <constraint> or #SBATCH -C
```

## Wrapper setup
Copy `perjob_submit.sh` from this directory to another location and make it executable:
```
chmod a+x ./perjob_submit.sh
```

Create a crontab to have `janitor` running every 5mins to clean clusters:
```
*/5 * * * * /path/to/perjob_submit.sh --janitor >> /config/logs/perjob-submit/janitor.log 2>&1
```

## Submission
```
./perjob_submit.sh <job.sbatch>
```

## Sequence
`perjob_submit.sh` reads the requested node count and `mgmt` configuration from the sbatch file.
The constraint value is treated as the `mgmt` configuration name. For example:
```
#SBATCH --nodes=3
#SBATCH --constraint=perjob
```
It then creates a temporary cluster with:
```
mgmt clusters create --instancetype perjob --count 3
```

The wrapper then:

1) Validates that the mgmt configuration exists.
2) Checks for duplicate active requests with the same node count and constraint.
3) Copies the sbatch file into `/config/logs/perjob-submit/` so later edits do not affect the submitted job.
4) Starts a background worker.
5) The worker creates the cluster.
6) The worker waits until the new nodes are visible to Slurm.
7) The worker submits the copied sbatch file.
8) The worker records the Slurm job id in a state file.
9) A janitor command later deletes the cluster once the Slurm job is no longer in `squeue`.

## Logs and state
Logs are written under:
```
/config/logs/perjob-submit/
```
State files are written under:
```
/config/logs/perjob-submit/state/
```
Monitor a request with:
```
tail -f /config/logs/perjob-submit/<request_id>.log
cat /config/logs/perjob-submit/state/<request_id>.env
```

## Janitor
The janitor cleans up clusters for completed jobs and abandoned requests.

Run manually:
```
./perjob_submit.sh --janitor
```
Recommended cron entry:
```
*/5 * * * * /path/to/perjob_submit.sh --janitor >> /config/logs/perjob-submit/janitor.log 2>&1
```
## Limits
The wrapper limits concurrent activity to avoid overloading the controller:

* `MAX_CREATING`: maximum clusters being created at the same time.
* `MAX_ACTIVE`: maximum active per-job requests.
Adjust these values near the top of `perjob_submit.sh`.

## Failure Handling
If the worker fails before submitting the Slurm job, it attempts to delete the created cluster.

If the worker dies unexpectedly, the janitor detects abandoned state files and deletes the cluster.

If the job was submitted successfully, the janitor waits until the job disappears from `squeue` before deleting the cluster.

## Known Limitations
* The wrapper assumes `mgmt`, `sbatch`, `squeue`, `sinfo`, `jq`, and `realpath` are available.
* Cleanup depends on the janitor running regularly.
* The wrapper does not use Slurm power saving.
* The Slurm job is submitted only after nodes exist and are visible to Slurm.