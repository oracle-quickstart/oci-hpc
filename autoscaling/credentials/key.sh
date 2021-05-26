#!/bin/bash

sed 's/-----END RSA PRIVATE KEY-----//' $1 | sed 's/ /\n/4g' > $2
echo -----END RSA PRIVATE KEY----- >> $2
chmod 600 $2