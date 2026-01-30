


import click
from lib.database import get_all_configs
from lib.functions import generate_slurm_entries, read_slurm_conf, write_slurm_conf, sync_slurm_config, generate_topology_entries_simple
from lib.logger import logger
import sys

@click.command()
@click.option('--slurm-conf', default='/etc/slurm/slurm.conf', help='Path to slurm.conf')
@click.option('--dry-run', is_flag=True, help='Show changes without applying them')
def update_slurm(slurm_conf, dry_run):
    """Synchronize database configurations to slurm.conf."""

    configs = get_all_configs("compute")
    
    if dry_run:
        logger.info("Dry run mode - showing what would be generated:")
        logger.info("Dry run mode - entries in slurm.conf:")
        slurmconf = generate_slurm_entries(configs)
        logger.info(slurmconf)
        for entry in slurmconf[0]:
            logger.info(entry)
        topologyconf = generate_topology_entries_simple(slurmconf[1])
        for entry in topologyconf:
            logger.info(entry)            
    else:
        if sync_slurm_config(configs, slurm_conf):
            logger.info("✓ Configuration synchronized successfully")
        else:
            logger.error("✗ Failed to synchronize configuration")
            sys.exit(1)


