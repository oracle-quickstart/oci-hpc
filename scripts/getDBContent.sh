mongosh network_scan --quiet --eval 'printjson(db.http_servers.find({}))'

#mongosh network_scan --quiet --eval 'db.http_servers.deleteMany({})'
