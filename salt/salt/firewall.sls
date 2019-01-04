firewalld_disable: 
  service.disabled: 
    - name: firewalld

firewalld_stop: 
  service.dead:  
    - name: firewalld
