#!/bin/bash

mkdir /mnt/ramfs
mount -t ramfs none /mnt/ramfs
mkdir /mnt/ramfs/pgdata
chown postgres. /mnt/ramfs/pgdata
chmod 600 /mnt/ramfs/pgdata

su -c "psql -c \"CREATE TABLESPACE ram LOCATION '/mnt/ramfs/pgdata';\"" postgres
