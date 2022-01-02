#!/bin/bash

# go to script folder
test_dir=$(dirname "$(readlink -f "$0")")

# set default hosts if not provided in command line
HOSTS=${@:-cliche81 cliche82 cliche83}

# clear logs / configure / start server + console on each host
for host in $HOSTS
do
  x=`echo "$host" | tail -c 2`
  ping -c 1 $host 2>&1 >/dev/null && ssh $host "cd $test_dir
    rm -rf log ; mkdir log
    ./configure.sh
	  export DISPLAY=:0
  	echo \"start Supvisors on $host as server_$x\"
	  export IDENTIFIER=server_$x
	  supervisord -c etc/supervisord_server.conf -i \$IDENTIFIER
  	echo \"start Supvisors on $host as console_$x\"
	  export IDENTIFIER=console_$x
	  supervisord -c etc/supervisord_console.conf -i \$IDENTIFIER"
done

# start firefox to get the Web UI
firefox http://localhost:61000 &