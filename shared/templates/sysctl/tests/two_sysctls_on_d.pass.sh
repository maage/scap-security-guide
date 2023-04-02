#!/bin/bash
{{% if SYSCTLVAL == "" %}}
# variables = sysctl_{{{ SYSCTLID }}}_value={{{ SYSCTL_CORRECT_VALUE }}}
{{% endif %}}

. $SHARED/sysctl.sh
sysctl_reset

sed -i "/{{{ SYSCTLVAR }}}/d" /etc/sysctl.conf

echo "{{{ SYSCTLVAR }}} = {{{ SYSCTL_CORRECT_VALUE }}}" >> /etc/sysctl.d/first.conf
echo "{{{ SYSCTLVAR }}} = {{{ SYSCTL_CORRECT_VALUE }}}" >> /etc/sysctl.d/duplicate.conf

sysctl -w {{{ SYSCTLVAR }}}="{{{ SYSCTL_CORRECT_VALUE }}}"
