CREATE TABLE IF NOT EXISTS cluster_log.clusters (
    sql_id INT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
    id VARCHAR(64) UNIQUE,
    creation_log VARCHAR(128),
    deletion_log VARCHAR(128),
    started_creation TIMESTAMP,
    created TIMESTAMP,
    creation_time TIME,
    started_deletion TIMESTAMP,
    deleted TIMESTAMP,
    deletion_time TIME,
    state ENUM('creating', 'running', 'deleting', 'deleted'),
    oci_state ENUM('provisioning', 'scaling','running', 'terminating', 'terminated'),
    nodes INT,
    trigger_job_id VARCHAR(64),
    class_name VARCHAR(64),
    cluster_name VARCHAR(64),
    cluster_OCID VARCHAR(128) UNIQUE,
    creation_error VARCHAR(512),
    deletion_error VARCHAR(512),
    deletion_tries INT DEFAULT 0,
    shape VARCHAR(64),
    CN BOOLEAN,
    cpu_per_node INT
);
CREATE TABLE IF NOT EXISTS cluster_log.nodes (
    id INT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
    cluster_id VARCHAR(64),
    cluster_index INT UNSIGNED,
    cpus INT,
    used_cpus INT,
    started_creation TIMESTAMP,
    created TIMESTAMP,
    started_deletion TIMESTAMP,
    deleted TIMESTAMP,
    state ENUM('provisioning', 'running', 'deleting', 'deleted'),
    oci_state ENUM('provisioning', 'running', 'deleting', 'deleted'),
    sched_state ENUM('idle', 'busy'),
    class_name VARCHAR(64),
    hostname VARCHAR(64) UNIQUE,
    ip VARCHAR(32),
    node_OCID VARCHAR(128) UNIQUE,
    shape VARCHAR(64),
    FOREIGN KEY (cluster_id) REFERENCES cluster_log.clusters(id),
    CONSTRAINT cluster_key UNIQUE(cluster_id,cluster_index)
);

CREATE TABLE IF NOT EXISTS cluster_log.jobs (
    id INT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
    cluster_id VARCHAR(64),
    cluster_name VARCHAR(64),
    job_id VARCHAR(64) UNIQUE,
    cpus INT,
    nodes INT,
    submitted TIMESTAMP,
    started TIMESTAMP,
    finished TIMESTAMP,
    queue_time TIME,
    run_time TIME,
    state ENUM('queued', 'running', 'done', 'failed', 'cancelled'),
    class_name VARCHAR(64),
    FOREIGN KEY (cluster_id) REFERENCES cluster_log.clusters(id)
);

CREATE TABLE IF NOT EXISTS cluster_log.nodes_timeserie (
	id INT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
	node_id INT UNSIGNED,
	state_m TEXT,
	oci_state_m TEXT,
	created_on_m TIMESTAMP,
	used_cpus INT,
	FOREIGN KEY (node_id) REFERENCES cluster_log.nodes(id)
);

CREATE TABLE IF NOT EXISTS cluster_log.jobs_timeserie (
	id INT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
	node_id INT UNSIGNED,
	job_id VARCHAR(64),
	used_cpus INT,
	created_on_m TIMESTAMP,
	FOREIGN KEY (node_id) REFERENCES cluster_log.nodes(id),
	FOREIGN KEY (job_id) REFERENCES cluster_log.jobs(job_id),
	UNIQUE(node_id, job_id, created_on_m)
);

CREATE TABLE IF NOT EXISTS cluster_log.errors_timeserie (
	id INT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
	cluster_id VARCHAR(64),
	cluster_OCID VARCHAR(128),
    state ENUM('creation','deletion','oci'),
	error_log VARCHAR(128),
    error_type VARCHAR(512),
    nodes INT,
	created_on_m TIMESTAMP,
    FOREIGN KEY (cluster_id) REFERENCES cluster_log.clusters(id),
	UNIQUE(id)
);