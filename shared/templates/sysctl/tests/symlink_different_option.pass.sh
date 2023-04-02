#!/bin/bash
{{% if SYSCTLVAL == "" %}}
# variables = sysctl_{{{ SYSCTLID }}}_value={{{ SYSCTL_CORRECT_VALUE }}}
{{% endif %}}

. $SHARED/sysctl.sh
sysctl_reset

sed -i "/{{{ SYSCTLVAR }}}/d" /etc/sysctl.conf
echo "{{{ SYSCTLVAR }}} = {{{ SYSCTL_CORRECT_VALUE }}}" >> /etc/sysctl.conf

# Ensure a different sysctl option is configured
{{% if SYSCTLVAR != "net.ipv4.conf.all.accept_source_route" %}}
echo "net.ipv4.conf.all.accept_source_route = 0" >> /etc/sysctl.d/90-test.conf
{{% else %}}
echo "net.ipv4.conf.default.accept_source_route = 0" >> /etc/sysctl.d/90-test.conf
{{% endif %}}

# Add a symlink
ln -s /etc/sysctl.d/90-test.conf /etc/sysctl.d/99-sysctl.conf

sysctl -w {{{ SYSCTLVAR }}}="{{{ SYSCTL_CORRECT_VALUE }}}"
