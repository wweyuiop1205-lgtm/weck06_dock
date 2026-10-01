#!/usr/bin/env bash
set -euo pipefail

# Some Codespaces have a legacy FORWARD policy of DROP while Docker installs
# rules for Compose bridges in the nftables backend. Keep the exception scoped
# to this project's bridge; never change the host-wide FORWARD policy.
cd "$(dirname "$0")/.."
web_id="$(docker compose ps -q web)"
api_id="$(docker compose ps -q api)"
if [[ -z "$web_id" || -z "$api_id" ]]; then
  printf '請先啟動 web 與 api 容器。\n' >&2
  exit 1
fi

web_network_id="$(docker inspect "$web_id" --format '{{range .NetworkSettings.Networks}}{{.NetworkID}}{{end}}')"
api_network_id="$(docker inspect "$api_id" --format '{{range .NetworkSettings.Networks}}{{.NetworkID}}{{end}}')"
if [[ -z "$web_network_id" || "$web_network_id" != "$api_network_id" ]]; then
  printf 'web 與 api 沒有單一共用網路，請檢查 Compose 設定。\n' >&2
  exit 1
fi
if [[ "$(docker network inspect "$web_network_id" --format '{{.Driver}}')" != bridge ]]; then
  printf '容器未使用橋接網路，這個修復腳本不適用。\n' >&2
  exit 1
fi

bridge="$(docker network inspect "$web_network_id" --format '{{index .Options "com.docker.network.bridge.name"}}')"
if [[ -z "$bridge" || "$bridge" == '<no value>' ]]; then
  bridge="br-${web_network_id:0:12}"
fi
ip link show "$bridge" >/dev/null

port="${ERP_WEB_PORT:-8080}"
if curl --silent --show-error --fail --max-time 5 "http://127.0.0.1:${port}/api/v1/ready"; then
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

curl --silent --show-error --fail --max-time 5 "http://127.0.0.1:${port}/api/v1/ready"
printf '\nAPI 代理已恢復。\n'
