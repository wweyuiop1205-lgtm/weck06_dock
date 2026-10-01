#!/usr/bin/env bash
set -euo pipefail

# Some Codespaces have a legacy FORWARD policy of DROP while Docker installs
# rules for Compose bridges in the nftables backend. Keep the exception scoped
# to this project's bridge; never change the host-wide FORWARD policy.
network_name="supply-chain-risk-source_default"
network_id="$(docker network inspect "$network_name" --format '{{.Id}}')"
bridge="br-${network_id:0:12}"
ip link show "$bridge" >/dev/null

if curl --silent --show-error --fail --max-time 5 http://127.0.0.1:8080/api/v1/ready; then
  printf '\nAPI 代理已正常，無需修改防火牆。\n'
  exit 0
fi

if ! sudo iptables-legacy -S FORWARD | grep -q '^-P FORWARD DROP$'; then
  printf '舊版 FORWARD 鏈並非 DROP；請檢查容器日誌，不變更防火牆。\n' >&2
  exit 1
fi

if sudo iptables-legacy -C FORWARD -i "$bridge" -o "$bridge" -j ACCEPT 2>/dev/null; then
  printf '本專案橋接網路的允許規則已存在。\n'
else
  sudo iptables-legacy -I FORWARD 1 -i "$bridge" -o "$bridge" -j ACCEPT
  printf '已允許本專案橋接網路內的容器互相連線。\n'
fi

curl --silent --show-error --fail --max-time 5 http://127.0.0.1:8080/api/v1/ready
printf '\nAPI 代理已恢復。\n'
