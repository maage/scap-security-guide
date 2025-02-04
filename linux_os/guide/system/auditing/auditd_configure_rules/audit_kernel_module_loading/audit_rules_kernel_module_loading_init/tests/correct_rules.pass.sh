#!/bin/bash
# packages = audit

{{% if "ol" in product or 'rhel' in product %}}
echo "-a always,exit -F arch=b32 -S init_module -F auid>=1000 -F auid!=unset -k modules" >> /etc/audit/rules.d/modules.rules
echo "-a always,exit -F arch=b64 -S init_module -F auid>=1000 -F auid!=unset -k modules" >> /etc/audit/rules.d/modules.rules
{{% else %}}
echo "-a always,exit -F arch=b32 -S init_module -k modules" >> /etc/audit/rules.d/modules.rules
echo "-a always,exit -F arch=b64 -S init_module -k modules" >> /etc/audit/rules.d/modules.rules
{{% endif %}}
