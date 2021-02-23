# Odoo Community

## Install Postgres 

Create a postgres container
```
docker run -d -e POSTGRES_USER=odoo -e POSTGRES_PASSWORD=odoo -e POSTGRES_DB=postgres --name postgres_ce postgres:10
```

## Install Odoo Community

Don't forget to write the correct path to the files
```
docker run -v "[PATH]/addons/13.0:/mnt/extra-addons -v [PATH]/config/13.0:/etc/odoo -p 8069:8069 --name odoo_13_ce --link postgres_ce:db -t odoo:13.0
```
