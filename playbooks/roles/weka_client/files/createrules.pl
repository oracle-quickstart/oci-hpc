#! /usr/bin/perl -w
#
use strict;
my $TABLE=0;
while(<STDIN>)
{
	chomp;
	my $NIC = $_;
	my $IP = '';
	$TABLE++;

	open(FH, '<', "/etc/sysconfig/network-scripts/ifcfg-$NIC");
	while(<FH>)
	{	
		chomp;	
		if(m/IPADDR=(\d+\.\d+\.\d+\.\d+)/)
		{
			$IP=$1;
		}
	}

	#`echo '192.168.0.0/16 dev $NIC src 192.168.2.153 table net$TABLE' >> /etc/sysconfig/network-scripts/route-$NIC`;
	print "echo '192.168.0.0/16 dev $NIC src $IP table net$TABLE' > /etc/sysconfig/network-scripts/route-$NIC"."\n";

	#`echo 'table net$TABLE from $IP' >> /etc/sysconfig/network-scripts/rule-$NIC`;
	print "echo 'table net$TABLE from $IP' > /etc/sysconfig/network-scripts/rule-$NIC"."\n";

}
