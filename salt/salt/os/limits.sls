/etc/security/limits.conf:
  file.append: 
    - text: | 
        *               hard    memlock         unlimited
        *               soft    memlock         unlimited
        *               hard    nofile          65535
        *               soft    nofile          65535