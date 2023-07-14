#!/bin/bash


/usr/bin/nvidia-smi --query-gpu=timestamp,pci.bus,utilization.gpu,utilization.memory,temperature.gpu,power.draw,clocks.mem,clocks.gr,clocks_throttle_reasons.sw_power_cap,clocks_throttle_reasons.hw_thermal_slowdown,clocks_throttle_reasons.hw_power_brake_slowdown,clocks_throttle_reasons.sw_thermal_slowdown,clocks_throttle_reasons.sync_boost,clocks_throttle_reasons.active --format=csv

