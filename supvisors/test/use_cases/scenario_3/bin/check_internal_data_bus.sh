#!/bin/bash

function internal_data_bus_running() {
    local result=`supervisorctl -s http://localhost:61000 status scen3_mw:internal_data_bus | awk '{print $2}'`
    echo $result
}

while [ $(common_data_bus_running) != "RUNNING" ]
do
    sleep 1
done
