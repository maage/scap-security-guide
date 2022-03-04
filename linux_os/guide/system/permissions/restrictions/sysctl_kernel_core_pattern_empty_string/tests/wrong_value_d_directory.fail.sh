#!/bin/bash

{{{ bash_sysctl_test_clean() }}}

sed -i "/kernel.core_pattern/d" /etc/sysctl.conf
echo "kernel.core_pattern=|/bin/false" >> /etc/sysctl.d/98-sysctl.conf

# set correct runtime value to check if the filesystem configuration is evaluated properly
sysctl -w kernel.core_pattern=""
