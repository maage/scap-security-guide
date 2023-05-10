#!/bin/bash
{{% if SYSCTLVAL is none or SYSCTLVAL is not string %}}
# variables = sysctl_{{{ SYSCTLID }}}_value={{{ SYSCTL_CORRECT_VALUE }}}
{{% endif %}}

{{{ bash_sysctl_test_clean() }}}

sed -i "/{{{ SYSCTLVAR }}}/d" /etc/sysctl.conf
echo "{{{ SYSCTLVAR }}} = {{{ SYSCTL_CORRECT_VALUE }}}" >> /etc/sysctl.conf

# Multiple symliks to the same file should be ignored
ln -s /etc/sysctl.conf /etc/sysctl.d/90-sysctl.conf
ln -s /etc/sysctl.conf /etc/sysctl.d/99-sysctl.conf

sysctl -w {{{ SYSCTLVAR }}}="{{{ SYSCTL_CORRECT_VALUE }}}"

