Stack to create an autoscaling cluster. 
As described when you specify your variables, if you select instance-principal as way of authenticating your node, make sure your generate a dynamic group and give the folowing policies to it: 

Allow dynamic-group instance_principal to read app-catalog-listing in tenancy
Allow dynamic-group instance_principal to use tag-namespace in tenancy

And also either:

Allow dynamic-group instance_principal to manage compute-management-family in compartment comaprtmentName
Allow dynamic-group instance_principal to manage instance-family in compartment comaprtmentName
Allow dynamic-group instance_principal to use virtual-network-family in compartment comaprtmentName

or:

Allow dynamic-group instance_principal to manage all-resources in compartment comaprtmentName


Clusters folders: 

~/autoscaling/clusters/clustername

Logs: 

~/autosclaing/logs

Cronjob: 

~/autoscaling/crontab/

To turn off the cronjob: Comment out the second line in : 
crontab -e

