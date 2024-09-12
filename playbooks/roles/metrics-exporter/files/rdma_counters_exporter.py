from prometheus_client import start_http_server, Gauge
import time
import subprocess

# Define Prometheus metrics
np_ecn_marked_roce_packets = Gauge('rdma_np_ecn_marked_roce_packets', 'Number of ROCEv2 packets marked for congestion', ['hostname', 'interface'])
out_of_sequence = Gauge('rdma_out_of_sequence', 'Number of out of sequence packets received.', ['hostname', 'interface'])
packet_seq_err = Gauge('rdma_packet_seq_err', 'Number of received NAK sequence error packets', ['hostname', 'interface'])
local_ack_timeout_err = Gauge('rdma_local_ack_timeout_err', 'Number of times QPs ack timer expired', ['hostname', 'interface'])
roce_adp_retrans = Gauge('rdma_roce_adp_retrans', 'Number of adaptive retransmissions for RoCE traffic', ['hostname', 'interface'])
np_cnp_sent = Gauge('rdma_np_cnp_sent', 'Number of CNP packets sent', ['hostname', 'interface'])
rp_cnp_handled = Gauge('rdma_rp_cnp_handled', 'Number of CNP packets handled to throttle', ['hostname', 'interface'])
rp_cnp_ignored = Gauge('rdma_rp_cnp_ignored', 'Number of CNP packets received and ignored', ['hostname', 'interface'])
rx_icrc_encapsulated = Gauge('rdma_rx_icrc_encapsulated', 'Number of RoCE packets with ICRC (Invertible Cyclic Redundancy Check) errors', ['hostname', 'interface'])
roce_slow_restart = Gauge('rdma_roce_slow_restart', 'Number of times RoCE slow restart was used', ['hostname', 'interface'])

def get_rdma_metrics():
    hostname = subprocess.getoutput("hostname")
    rdma_nics = subprocess.getoutput("rdma link show | grep rdma | cut -d ' ' -f2 | sed 's/\/1//g' | tr '\n' ' '").split()
    for nic in rdma_nics:
        ecn_packets = int(subprocess.getoutput("cat /sys/class/infiniband/{nic}/ports/1/hw_counters/np_ecn_marked_roce_packets".format(nic=nic)))
        out_of_seq = int(subprocess.getoutput("cat /sys/class/infiniband/{nic}/ports/1/hw_counters/out_of_sequence".format(nic=nic)))
        seq_err = int(subprocess.getoutput("cat /sys/class/infiniband/{nic}/ports/1/hw_counters/packet_seq_err".format(nic=nic)))
        local_ack_timeout = int(subprocess.getoutput("cat /sys/class/infiniband/{nic}/ports/1/hw_counters/local_ack_timeout_err".format(nic=nic)))
        adp_retrans = int(subprocess.getoutput("cat /sys/class/infiniband/{nic}/ports/1/hw_counters/roce_adp_retrans".format(nic=nic)))
        cnp_sent = int(subprocess.getoutput("cat /sys/class/infiniband/{nic}/ports/1/hw_counters/np_cnp_sent".format(nic=nic)))
        cnp_handled = int(subprocess.getoutput("cat /sys/class/infiniband/{nic}/ports/1/hw_counters/rp_cnp_handled".format(nic=nic)))
        cnp_ignored = int(subprocess.getoutput("cat /sys/class/infiniband/{nic}/ports/1/hw_counters/rp_cnp_ignored".format(nic=nic)))
        icrc_encaps = int(subprocess.getoutput("cat /sys/class/infiniband/{nic}/ports/1/hw_counters/rx_icrc_encapsulated".format(nic=nic)))
        slow_restart = int(subprocess.getoutput("cat /sys/class/infiniband/{nic}/ports/1/hw_counters/roce_slow_restart".format(nic=nic)))
        np_ecn_marked_roce_packets.labels(hostname=hostname, interface=nic).set(ecn_packets)
        out_of_sequence.labels(hostname=hostname, interface=nic).set(out_of_seq)
        packet_seq_err.labels(hostname=hostname, interface=nic).set(seq_err)
        local_ack_timeout_err.labels(hostname=hostname, interface=nic).set(local_ack_timeout)
        roce_adp_retrans.labels(hostname=hostname, interface=nic).set(adp_retrans)
        np_cnp_sent.labels(hostname=hostname, interface=nic).set(cnp_sent)
        rp_cnp_handled.labels(hostname=hostname, interface=nic).set(cnp_handled)
        rp_cnp_ignored.labels(hostname=hostname, interface=nic).set(cnp_ignored)
        rx_icrc_encapsulated.labels(hostname=hostname, interface=nic).set(icrc_encaps)
        roce_slow_restart.labels(hostname=hostname, interface=nic).set(slow_restart)

if __name__ == '__main__':
    # Start up the server to expose the metrics.
    start_http_server(9500)
    # Generate RDMA metrics every 10 seconds
    while True:
        get_rdma_metrics()
        time.sleep(10)
