from prometheus_client import start_http_server, Gauge
import time
import socket
import os

def read_counter(path, default=0):
    """Safely read a counter file, returning default if not found."""
    try:
        with open(path, 'r') as f:
            return int(f.read().strip().split(':')[0])
    except (FileNotFoundError, ValueError, PermissionError, OSError):
        return default

def get_ib_devices():
    """
    Get all InfiniBand devices from /sys/class/infiniband.
    Returns list of device names (e.g., ['mlx5_0', 'mlx5_1', ...])
    """
    ib_path = '/sys/class/infiniband'
    if not os.path.exists(ib_path):
        return []
    return [d for d in os.listdir(ib_path) if os.path.isdir(os.path.join(ib_path, d))]

# Critical Error Counters
rdma_out_of_sequence = Gauge('rdma_out_of_sequence', 'Packets received out of order', ['hostname', 'interface'])
rdma_packet_seq_err = Gauge('rdma_packet_seq_err', 'NAK sequence error packets (retransmissions)', ['hostname', 'interface'])
rdma_local_ack_timeout_err = Gauge('rdma_local_ack_timeout_err', 'QP ack timer expirations', ['hostname', 'interface'])
rdma_rx_icrc_encapsulated = Gauge('rdma_rx_icrc_encapsulated', 'RoCE packets with ICRC errors (data corruption)', ['hostname', 'interface'])
ib_symbol_error = Gauge('ib_symbol_error', 'Physical layer errors on link', ['hostname', 'interface'])
ib_port_rcv_errors = Gauge('ib_port_rcv_errors', 'Packets with errors received', ['hostname', 'interface'])
ib_link_downed = Gauge('ib_link_downed', 'Times link went down', ['hostname', 'interface'])
ib_link_error_recovery = Gauge('ib_link_error_recovery', 'Link error recovery events', ['hostname', 'interface'])

# Congestion Indicators
rdma_np_ecn_marked_roce_packets = Gauge('rdma_np_ecn_marked_roce_packets', 'ECN marked packets (network congestion)', ['hostname', 'interface'])
rdma_roce_adp_retrans = Gauge('rdma_roce_adp_retrans', 'Adaptive retransmissions', ['hostname', 'interface'])
rdma_np_cnp_sent = Gauge('rdma_np_cnp_sent', 'Congestion notification packets sent', ['hostname', 'interface'])
rdma_rp_cnp_handled = Gauge('rdma_rp_cnp_handled', 'Congestion notifications handled (throttling)', ['hostname', 'interface'])
rdma_roce_slow_restart = Gauge('rdma_roce_slow_restart', 'Slow restart events', ['hostname', 'interface'])
ib_port_xmit_wait = Gauge('ib_port_xmit_wait', 'Ticks waiting to transmit (backpressure)', ['hostname', 'interface'])

# Link State & Bandwidth
ib_link_state = Gauge('ib_link_state', 'Port state (4=ACTIVE)', ['hostname', 'interface'])
ib_link_phys_state = Gauge('ib_link_phys_state', 'Physical state (5=LinkUp)', ['hostname', 'interface'])
ib_port_xmit_data = Gauge('ib_port_xmit_data', 'Total bytes transmitted', ['hostname', 'interface'])
ib_port_rcv_data = Gauge('ib_port_rcv_data', 'Total bytes received', ['hostname', 'interface'])

def get_rdma_metrics():
    hostname = socket.gethostname()
    rdma_nics = get_ib_devices()

    for nic in rdma_nics:
        base_path = f"/sys/class/infiniband/{nic}/ports/1"
        hw_counters = f"{base_path}/hw_counters"
        counters = f"{base_path}/counters"

        # Critical Errors
        rdma_out_of_sequence.labels(hostname=hostname, interface=nic).set(
            read_counter(f"{hw_counters}/out_of_sequence"))
        rdma_packet_seq_err.labels(hostname=hostname, interface=nic).set(
            read_counter(f"{hw_counters}/packet_seq_err"))
        rdma_local_ack_timeout_err.labels(hostname=hostname, interface=nic).set(
            read_counter(f"{hw_counters}/local_ack_timeout_err"))
        rdma_rx_icrc_encapsulated.labels(hostname=hostname, interface=nic).set(
            read_counter(f"{hw_counters}/rx_icrc_encapsulated"))
        ib_symbol_error.labels(hostname=hostname, interface=nic).set(
            read_counter(f"{counters}/symbol_error"))
        ib_port_rcv_errors.labels(hostname=hostname, interface=nic).set(
            read_counter(f"{counters}/port_rcv_errors"))
        ib_link_downed.labels(hostname=hostname, interface=nic).set(
            read_counter(f"{counters}/link_downed"))
        ib_link_error_recovery.labels(hostname=hostname, interface=nic).set(
            read_counter(f"{counters}/link_error_recovery"))

        # Congestion
        rdma_np_ecn_marked_roce_packets.labels(hostname=hostname, interface=nic).set(
            read_counter(f"{hw_counters}/np_ecn_marked_roce_packets"))
        rdma_roce_adp_retrans.labels(hostname=hostname, interface=nic).set(
            read_counter(f"{hw_counters}/roce_adp_retrans"))
        rdma_np_cnp_sent.labels(hostname=hostname, interface=nic).set(
            read_counter(f"{hw_counters}/np_cnp_sent"))
        rdma_rp_cnp_handled.labels(hostname=hostname, interface=nic).set(
            read_counter(f"{hw_counters}/rp_cnp_handled"))
        rdma_roce_slow_restart.labels(hostname=hostname, interface=nic).set(
            read_counter(f"{hw_counters}/roce_slow_restart"))
        ib_port_xmit_wait.labels(hostname=hostname, interface=nic).set(
            read_counter(f"{counters}/port_xmit_wait"))

        # Link State & Bandwidth
        ib_link_state.labels(hostname=hostname, interface=nic).set(
            read_counter(f"{base_path}/state"))
        ib_link_phys_state.labels(hostname=hostname, interface=nic).set(
            read_counter(f"{base_path}/phys_state"))
        ib_port_xmit_data.labels(hostname=hostname, interface=nic).set(
            read_counter(f"{counters}/port_xmit_data") * 4)
        ib_port_rcv_data.labels(hostname=hostname, interface=nic).set(
            read_counter(f"{counters}/port_rcv_data") * 4)

if __name__ == '__main__':
    start_http_server(9500)
    while True:
        get_rdma_metrics()
        time.sleep(10)
