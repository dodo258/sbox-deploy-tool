#!/usr/bin/env bash
set -euo pipefail

SOURCE="${BASH_SOURCE[0]}"
while [ -L "$SOURCE" ]; do
  DIR="$(cd "$(dirname "$SOURCE")" && pwd)"
  TARGET="$(readlink "$SOURCE")"
  if [[ "$TARGET" != /* ]]; then
    SOURCE="$DIR/$TARGET"
  else
    SOURCE="$TARGET"
  fi
done

ROOT_DIR="$(cd "$(dirname "$SOURCE")/.." && pwd)"
BACKEND_BIN="${ROOT_DIR}/bin/sboxctl-backend"
SELF_UPDATE_URL="https://raw.githubusercontent.com/dodo258/sbox-deploy-tool/main/bootstrap.sh"

RESET='\033[0m'
BOLD='\033[1m'
DIM='\033[2m'
CYAN='\033[38;5;45m'
GREEN='\033[38;5;41m'
YELLOW='\033[38;5;220m'
RED='\033[38;5;203m'
BLUE='\033[38;5;39m'

print_logo() {
  printf "${CYAN}   _____ __                ____             ${RESET}\n"
  printf "${CYAN}  / ___// /_  ____  _  __ / __ )____  _  __${RESET}\n"
  printf "${CYAN}  \\__ \\/ __ \\/ __ \\| |/_// __  / __ \\| |/_/${RESET}\n"
  printf "${CYAN} ___/ / /_/ / /_/ />  < / /_/ / /_/ />  <  ${RESET}\n"
  printf "${CYAN}/____/_.___/\\____/_/|_|/_____/\\____/_/|_|  ${RESET}\n"
  printf "dodo258 deploy tool | sing-box / xray | reality | media dns\n\n"
}

section() {
  printf "${BOLD}${BLUE}========================================================================${RESET}\n"
  printf "${BOLD}%s${RESET}\n" "$1"
  printf "${BOLD}${BLUE}========================================================================${RESET}\n"
}

info() {
  printf "${CYAN}[INFO]${RESET} %s\n" "$1"
}

ok() {
  printf "${GREEN}[OK]${RESET} %s\n" "$1"
}

warn() {
  printf "${YELLOW}[WARN]${RESET} %s\n" "$1"
}

err() {
  printf "${RED}[ERR]${RESET} %s\n" "$1"
}

clear_screen() {
  if [[ -t 1 ]] && command -v clear >/dev/null 2>&1; then
    clear
  fi
}

print_compact_header() {
  printf "${DIM}dodo258 deploy tool | main menu${RESET}\n\n"
}

pause_screen() {
  printf "\n"
  read -r -p "按回车继续..." _
}

run_backend_json() {
  local stdout_file stderr_file rc
  stdout_file="$(mktemp)"
  stderr_file="$(mktemp)"
  if ! SBOXCTL_JSON=1 "${BACKEND_BIN}" "$@" >"${stdout_file}" 2>"${stderr_file}"; then
    rc=$?
    err "$(tail -n 1 "${stderr_file}" "${stdout_file}" 2>/dev/null | tail -n 1)"
    rm -f "${stdout_file}" "${stderr_file}"
    return "${rc}"
  fi
  if [[ ! -s "${stdout_file}" ]]; then
    err "后台没有返回可用数据"
    rm -f "${stdout_file}" "${stderr_file}"
    return 1
  fi
  cat "${stdout_file}"
  rm -f "${stdout_file}" "${stderr_file}"
}

json_print() {
  local json="$1"
  local mode="$2"
  printf '%s' "$json" | python3 -c '
import json, sys

mode = sys.argv[1]
try:
    data = json.load(sys.stdin)
except Exception:
    print("数据解析失败")
    sys.exit(7)

def yn(value):
    return "是" if value else "否"

def onoff(value):
    return "已开启" if value else "未开启"

def svc(value):
    return "正常" if value == "active" else value

def listen(value):
    return "正常" if value else "未监听"

if mode == "status":
    b = data["bbr"]["bbr"]
    print(f"BBR: {onoff(bool(b['"'"'enabled'"'"']))} | 当前算法: {b['"'"'current'"'"']} | 队列: {b['"'"'qdisc'"'"']}")
    print("")
    if not data["nodes"]:
        print("未发现已部署节点")
    for node in data["nodes"]:
        print(f"{node['"'"'name'"'"']} | 后端={node['"'"'backend'"'"']} | 端口={node['"'"'port'"'"']} | 服务={svc(node['"'"'active'"'"'])} | 自启={yn(bool(node['"'"'enabled'"'"']))} | 监听={listen(bool(node['"'"'listening'"'"']))}")
elif mode == "links":
    if not data["nodes"]:
        print("未发现已部署节点")
    for item in data["nodes"]:
        print(f"[{item['"'"'backend'"'"']}] {item['"'"'name'"'"']}")
        print(item["url"])
        print("")
elif mode == "bbr":
    b = data["bbr"]
    print(f"BBR 状态: {onoff(bool(b['"'"'enabled'"'"']))}")
    print(f"当前算法: {b['"'"'current'"'"']}")
    print(f"队列算法: {b['"'"'qdisc'"'"']}")
    print(f"系统支持 BBR: {yn(bool(b['"'"'has_bbr'"'"']))}")
elif mode == "nodes":
    for index, node in enumerate(data["nodes"], start=1):
        print(f"{index}\t{node['"'"'tag'"'"']}\t{node['"'"'name'"'"']}\t{node['"'"'backend'"'"']}\t{node['"'"'port'"'"']}\t{node['"'"'service'"'"']}\t{node['"'"'role'"'"']}\t{node['"'"'streaming_enabled'"'"']}")
elif mode == "domains":
    for index, item in enumerate(data["domains"], start=1):
        latency = f"{item['"'"'latency_ms'"'"']}ms" if item["latency_ms"] is not None else "当前网络探测失败"
        print(f"{index}\t{item['"'"'domain'"'"']}\t{latency}")
elif mode == "deploy":
    print(f"后端: {data['"'"'backend'"'"']} | 版本: {data['"'"'version'"'"']}")
    print(f"节点名称: {data['"'"'node'"'"']['"'"'name'"'"']}")
    print(f"监听端口: {data['"'"'node'"'"']['"'"'port'"'"']}")
    print(f"Reality 域名: {data['"'"'node'"'"']['"'"'domain'"'"']}")
    print(f"服务状态: {svc(data['"'"'service'"'"']['"'"'active'"'"'])} | 自启: {yn(bool(data['"'"'service'"'"']['"'"'enabled'"'"']))} | 监听: {listen(bool(data['"'"'service'"'"']['"'"'listening'"'"']))}")
    print(f"配置文件: {data['"'"'paths'"'"']['"'"'config'"'"']}")
    print(f"服务文件: {data['"'"'paths'"'"']['"'"'service'"'"']}")
    print(f"清单文件: {data['"'"'paths'"'"']['"'"'manifest'"'"']}")
    print(f"UFW 放行端口: {data['firewall_ports']}")
    print("")
    print("VLESS 地址:")
    print(data["exports"]["shadowrocket_vless"])
' "$mode"
}

json_value() {
  local json="$1"
  local expr="$2"
  printf '%s' "$json" | python3 -c '
import json, sys
try:
    data = json.load(sys.stdin)
except Exception:
    print("")
    sys.exit(7)
expr = sys.argv[1]
value = eval(expr, {"data": data})
if value is None:
    print("")
elif isinstance(value, bool):
    print("true" if value else "false")
else:
    print(value)
' "$expr"
}

prompt_default() {
  local prompt="$1"
  local default="${2:-}"
  local value
  read -r -p "$prompt" value || return 1
  if [[ -z "$value" ]]; then
    printf '%s' "$default"
  else
    printf '%s' "$value"
  fi
}

select_node() {
  local nodes_json lines choice
  nodes_json="$(run_backend_json backend-list-nodes)" || return 1
  lines="$(json_print "$nodes_json" nodes)"
  if [[ -z "$lines" ]]; then
    warn "未发现已部署节点"
    return 1
  fi
  while IFS=$'\t' read -r idx tag name backend port service role streaming_enabled; do
    printf "  %s) %s | 后端=%s | 端口=%s | 服务=%s\n" "$idx" "$name" "$backend" "$port" "$service"
  done <<<"$lines"
  printf "  0) 返回上一层\n"
  while true; do
    read -r -p "请选择节点（默认 1）: " choice || return 1
    choice="${choice:-1}"
    if [[ "$choice" == "0" ]]; then
      return 2
    fi
    local selected
    selected="$(printf '%s\n' "$lines" | awk -F '\t' -v target="$choice" '$1==target {print $0}')"
    if [[ -n "$selected" ]]; then
      printf '%s' "$selected"
      return 0
    fi
    warn "无效选项"
  done
}

select_streaming_node() {
  local nodes_json lines choice default_choice line_count
  nodes_json="$(run_backend_json backend-list-nodes)" || return 1
  lines="$(json_print "$nodes_json" nodes)"
  if [[ -z "$lines" ]]; then
    warn "未发现已部署节点"
    return 1
  fi
  line_count="$(printf '%s\n' "$lines" | grep -c . || true)"
  default_choice="1"
  if [[ "$line_count" == "1" ]]; then
    local selected_single label_single role_single streaming_single name_single
    selected_single="$(printf '%s\n' "$lines" | head -n 1)"
    role_single="$(printf '%s' "$selected_single" | awk -F '\t' '{print $7}')"
    streaming_single="$(printf '%s' "$selected_single" | awk -F '\t' '{print $8}')"
    name_single="$(printf '%s' "$selected_single" | awk -F '\t' '{print $3}')"
    if [[ "$role_single" == "media" ]]; then
      label_single="流媒体专用节点"
    elif [[ "$streaming_single" == "True" || "$streaming_single" == "true" ]]; then
      label_single="主节点 + 流媒体解锁"
    else
      label_single="主节点"
    fi
    echo "当前可修改节点：${name_single}（${label_single}）"
    printf '%s' "$selected_single"
    return 0
  fi
  echo "可修改的节点："
  while IFS=$'\t' read -r idx tag name backend port service role streaming_enabled; do
    local label
    if [[ "$role" == "media" ]]; then
      label="流媒体专用节点"
    elif [[ "$streaming_enabled" == "True" || "$streaming_enabled" == "true" ]]; then
      label="主节点 + 流媒体解锁"
      default_choice="$idx"
    else
      label="主节点"
    fi
    printf "  %s) %s（%s）\n" "$idx" "$name" "$label"
  done <<<"$lines"
  printf "  0) 返回上一层\n"
  while true; do
    read -r -p "请选择节点（默认 ${default_choice}）: " choice || return 1
    choice="${choice:-$default_choice}"
    if [[ "$choice" == "0" ]]; then
      return 2
    fi
    local selected
    selected="$(printf '%s\n' "$lines" | awk -F '\t' -v target="$choice" '$1==target {print $0}')"
    if [[ -n "$selected" ]]; then
      printf '%s' "$selected"
      return 0
    fi
    warn "无效选项"
  done
}

select_streaming_profile() {
  echo "流媒体规则："
  echo "  1) common-media（常见流媒体全选）"
  echo "  2) netflix"
  echo "  3) disney"
  echo "  4) max"
  echo "  5) primevideo"
  echo "  6) hulu"
  echo "  7) 自定义域名后缀"
  echo "  0) 返回上一层"
  local choice
  while true; do
    read -r -p "请选择规则（默认 1）: " choice || return 1
    choice="${choice:-1}"
    case "$choice" in
      1) printf 'common-media\t'; return 0 ;;
      2) printf 'netflix\t'; return 0 ;;
      3) printf 'disney\t'; return 0 ;;
      4) printf 'max\t'; return 0 ;;
      5) printf 'primevideo\t'; return 0 ;;
      6) printf 'hulu\t'; return 0 ;;
      7)
        local custom
        read -r -p "请输入自定义域名后缀（逗号分隔，输入 0 返回）: " custom || return 1
        [[ "$custom" == "0" ]] && return 2
        printf 'common-media\t%s' "$custom"
        return 0
        ;;
      0) return 2 ;;
      *) warn "无效选项" ;;
    esac
  done
}

deploy_flow() {
  local backend="$1"
  local role enable_streaming default_port mode region_json region country region_input port domains_json domains_lines domain_choice domain
  local default_name name streaming_dns profile_data streaming_profile streaming_domains confirm deploy_json region_upper

  section "部署 ${backend} 节点"
  info "任意子项输入 0 可返回上一层"
  echo "节点模式："
  echo "  1) 主节点"
  echo "  2) 流媒体专用节点"
  echo "  3) 主节点 + 流媒体解锁"
  echo "  0) 返回上一层"
  while true; do
    read -r -p "请选择模式（默认 1）: " mode || return 1
    mode="${mode:-1}"
    case "$mode" in
      1) role="main"; enable_streaming="false"; default_port="443"; break ;;
      2) role="media"; enable_streaming="true"; default_port="2443"; break ;;
      3) role="main"; enable_streaming="true"; default_port="443"; break ;;
      0) return 0 ;;
      *) warn "无效选项" ;;
    esac
  done

  region_json="$(run_backend_json backend-detect-region)" || return 1
  region="$(json_value "$region_json" "data['region']")"
  country="$(json_value "$region_json" "data['country']")"
  if [[ -n "$country" ]]; then
    info "自动识别地区池: ${region} (${country})"
  else
    info "自动识别地区池: ${region}"
  fi
  read -r -p "地区标记（默认 ${region}，输入 0 返回）: " region_input || return 1
  [[ "$region_input" == "0" ]] && return 0
  region="${region_input:-$region}"

  read -r -p "监听端口（默认 ${default_port}，输入 0 返回）: " port || return 1
  [[ "$port" == "0" ]] && return 0
  port="${port:-$default_port}"

  info "正在优选内置 Reality 域名，这一步通常需要 3-8 秒，请稍等"
  domains_json="$(run_backend_json backend-recommend-domains --region "$region" --limit 3 --timeout 6)" || return 1
  domains_lines="$(json_print "$domains_json" domains)"
  echo "推荐的 Reality 域名："
  while IFS=$'\t' read -r idx item_domain latency; do
    printf "  %s) %s | 延迟 %s\n" "$idx" "$item_domain" "$latency"
  done <<<"$domains_lines"
  echo "  0) 返回上一层"
  while true; do
    read -r -p "请选择 Reality 域名（默认 1）: " domain_choice || return 1
    domain_choice="${domain_choice:-1}"
    if [[ "$domain_choice" == "0" ]]; then
      return 0
    fi
    domain="$(printf '%s\n' "$domains_lines" | awk -F '\t' -v target="$domain_choice" '$1==target {print $2}')"
    if [[ -n "$domain" ]]; then
      break
    fi
    warn "无效选项"
  done
  echo ""

  region_upper="$(printf '%s' "$region" | tr '[:lower:]' '[:upper:]')"
  if [[ "$role" == "media" ]]; then
    default_name="${region_upper}-${backend}-media"
  else
    default_name="${region_upper}-${backend}-main"
  fi
  read -r -p "节点名称（默认 ${default_name}，输入 0 返回）: " name || return 1
  [[ "$name" == "0" ]] && return 0
  name="${name:-$default_name}"

  streaming_dns=""
  streaming_profile="common-media"
  streaming_domains=""
  if [[ "$enable_streaming" == "true" ]]; then
    read -r -p "流媒体 DNS 地址（输入 0 返回）: " streaming_dns || return 1
    [[ "$streaming_dns" == "0" ]] && return 0
    if [[ -z "$streaming_dns" ]]; then
      warn "当前模式必须填写流媒体 DNS 地址"
      return 1
    fi
    set +e
    profile_data="$(select_streaming_profile)"
    local profile_rc=$?
    set -e
    if [[ $profile_rc -eq 2 ]]; then
      return 0
    elif [[ $profile_rc -ne 0 ]]; then
      return 1
    fi
    streaming_profile="${profile_data%%$'\t'*}"
    streaming_domains="${profile_data#*$'\t'}"
    if [[ "$streaming_domains" == "$profile_data" ]]; then
      streaming_domains=""
    fi
  fi

  echo ""
  echo "部署摘要："
  echo "  后端: ${backend}"
  echo "  节点类型: ${role}"
  echo "  地区标记: ${region}"
  echo "  监听端口: ${port}"
  echo "  Reality 域名: ${domain}"
  echo "  节点名称: ${name}"
  if [[ "$enable_streaming" == "true" ]]; then
    echo "  流媒体 DNS: ${streaming_dns}"
    echo "  流媒体规则: ${streaming_profile}"
    if [[ -n "$streaming_domains" ]]; then
      echo "  自定义域名后缀: ${streaming_domains}"
    fi
  fi
  read -r -p "确认现在部署吗？[Y/n，输入 0 返回]: " confirm || return 1
  [[ "$confirm" == "0" ]] && return 0
  if [[ "${confirm,,}" == "n" ]]; then
    warn "已取消部署"
    return 0
  fi

  info "正在安装依赖、检查 BBR、部署服务，这一步可能需要几十秒"
  local args=(
    backend-deploy-local
    --backend "$backend"
    --role "$role"
    --region "$region"
    --port "$port"
    --domain "$domain"
    --name "$name"
    --backup-root /var/backups/sboxctl
    --backend-version latest
    --firewall
  )
  if [[ "$enable_streaming" == "true" ]]; then
    args+=(--enable-streaming-dns --streaming-dns "$streaming_dns" --streaming-profile "$streaming_profile")
    [[ -n "$streaming_domains" ]] && args+=(--streaming-domains "$streaming_domains")
  fi
  deploy_json="$(run_backend_json "${args[@]}")" || return 1
  ok "部署完成"
  json_print "$deploy_json" deploy
  return 0
}

modify_streaming_dns_flow() {
  section "修改流媒体 DNS"
  info "这里可以修改已部署节点的流媒体 DNS，也可以直接关闭流媒体 DNS"
  local selected rc tag node_name action dns profile_data streaming_profile streaming_domains update_json role streaming_enabled
  local -a args
  set +e
  selected="$(select_streaming_node)"
  rc=$?
  set -e
  if [[ $rc -eq 2 ]]; then
    return 0
  fi
  if [[ $rc -ne 0 ]]; then
    return 1
  fi
  tag="$(printf '%s' "$selected" | awk -F '\t' '{print $2}')"
  node_name="$(printf '%s' "$selected" | awk -F '\t' '{print $3}')"
  role="$(printf '%s' "$selected" | awk -F '\t' '{print $7}')"
  streaming_enabled="$(printf '%s' "$selected" | awk -F '\t' '{print $8}')"
  if [[ "$role" == "media" ]]; then
    echo "当前节点：${node_name}（流媒体专用节点）"
  elif [[ "$streaming_enabled" == "True" || "$streaming_enabled" == "true" ]]; then
    echo "当前节点：${node_name}（主节点 + 流媒体解锁）"
  else
    echo "当前节点：${node_name}（主节点）"
  fi
  echo "  1) 修改或启用流媒体 DNS"
  echo "  2) 关闭流媒体 DNS"
  echo "  0) 返回上一层"
  while true; do
    read -r -p "请选择操作（默认 1）: " action || return 1
    action="${action:-1}"
    case "$action" in
      1)
        read -r -p "新的流媒体 DNS 地址（输入 0 返回）: " dns || return 1
        [[ "$dns" == "0" ]] && return 0
        if [[ -z "$dns" ]]; then
          warn "流媒体 DNS 地址不能为空"
          continue
        fi
        set +e
        profile_data="$(select_streaming_profile)"
        rc=$?
        set -e
        if [[ $rc -eq 2 ]]; then
          return 0
        fi
        if [[ $rc -ne 0 ]]; then
          return 1
        fi
        streaming_profile="${profile_data%%$'\t'*}"
        streaming_domains="${profile_data#*$'\t'}"
        if [[ "$streaming_domains" == "$profile_data" ]]; then
          streaming_domains=""
        fi
        args=(backend-update-streaming-dns --tag "$tag" --streaming-dns "$dns" --streaming-profile "$streaming_profile")
        [[ -n "$streaming_domains" ]] && args+=(--streaming-domains "$streaming_domains")
        update_json="$(run_backend_json "${args[@]}")" || return 1
        ok "流媒体 DNS 已更新"
        printf '节点: %s\n' "$(json_value "$update_json" "data['node']['name']")"
        printf 'DNS: %s\n' "$(json_value "$update_json" "data['streaming_dns']['dns_server']")"
        printf '规则: %s\n' "$(json_value "$update_json" "data['streaming_dns']['profile_name']")"
        return 0
        ;;
      2)
        update_json="$(run_backend_json backend-update-streaming-dns --tag "$tag" --disable)" || return 1
        ok "流媒体 DNS 已关闭"
        printf '节点: %s\n' "$(json_value "$update_json" "data['node']['name']")"
        return 0
        ;;
      0) return 0 ;;
      *) warn "无效选项" ;;
    esac
  done
}

show_overview() {
  print_logo
  section "工具说明"
  echo "服务器端一键部署工具，协议固定为 VLESS + Reality + Vision。"
  echo "默认后端为 sing-box，也支持 xray。"
  echo ""
  echo "服务器端启动命令："
  echo "  curl -fsSL https://raw.githubusercontent.com/dodo258/sbox-deploy-tool/main/bootstrap.sh | sudo bash"
  echo ""
  echo "常用命令："
  echo "  sboxctl menu         # 进入交互首页"
  echo "  sboxctl show-status  # 查看节点状态"
  echo "  sboxctl show-links   # 查看导入地址"
  echo "  sboxctl show-logs    # 查看节点日志"
  echo "  sudo sboxctl update-streaming-dns --tag <节点标记> --streaming-dns <DNS>  # 修改流媒体 DNS"
  echo "  sboxctl bbr-status   # 查看 BBR 状态"
  echo "  sboxctl firewall --show-status # 查看 UFW 状态"
  echo "  首页菜单 -> 更新脚本   # 从 GitHub 拉取最新版脚本"
}

show_reality_help() {
  section "Reality 域名说明"
  echo "脚本只使用内置地址池，不开放手填自定义域名。"
  echo "部署时会先按服务器地区挑选候选域名，再自动测速，只让你选 1 / 2 / 3。"
  echo "当前展示的是适合内地访问习惯的商业站和大厂站点，不会把调试字段直接展示给用户。"
  echo "如果某个地区测速整体偏慢，优先换同地区或邻近地区服务器，不建议手工乱改域名。"
}

self_update_flow() {
  section "更新脚本"
  info "这一步会从 GitHub 拉取最新脚本，并覆盖当前已安装版本"
  read -r -p "确认现在更新脚本吗？[Y/n]: " confirm || return 1
  confirm="${confirm:-y}"
  if [[ "${confirm,,}" == "n" ]]; then
    warn "已取消更新"
    return 0
  fi
  info "正在从 GitHub 拉取最新脚本，这一步通常需要几秒到几十秒"
  exec env SBOXCTL_FORCE_UPDATE=1 bash -lc "curl -fsSL ${SELF_UPDATE_URL} | bash"
}

menu_loop() {
  local suppress_logo_once="${SBOXCTL_SUPPRESS_MENU_LOGO_ONCE:-0}"
  local first_render=1
  while true; do
    clear_screen
    if [[ "$suppress_logo_once" == "1" ]]; then
      suppress_logo_once="0"
    elif [[ "$first_render" == "1" ]]; then
      print_logo
      first_render=0
    else
      print_compact_header
    fi
    echo "1) 部署 sing-box 节点（推荐）"
    echo "2) 部署 xray 节点"
    echo "3) 查看节点状态"
    echo "4) 查看 VLESS 地址"
    echo "5) 查看节点日志"
    echo "6) 删除节点"
    echo "7) 查看 BBR 状态"
    echo "8) 设置 UFW 防火墙"
    echo "9) 修改流媒体 DNS"
    echo "10) Reality 域名说明"
    echo "11) 更新脚本"
    echo "0) 退出"
    read -r -p "请选择: " choice || exit 1
    choice="${choice:-1}"
    case "$choice" in
      1) deploy_flow "sing-box"; pause_screen ;;
      2) deploy_flow "xray"; pause_screen ;;
      3)
        section "节点状态"
        json_print "$(run_backend_json backend-show-status)" status
        pause_screen
        ;;
      4)
        section "VLESS 地址"
        json_print "$(run_backend_json backend-show-links)" links
        pause_screen
        ;;
      5)
        section "节点日志"
        local selected rc service logs_json
        set +e
        selected="$(select_node)"
        rc=$?
        set -e
        if [[ $rc -eq 2 ]]; then
          continue
        fi
        if [[ $rc -ne 0 ]]; then
          pause_screen
          continue
        fi
        service="$(printf '%s' "$selected" | awk -F '\t' '{print $6}')"
        logs_json="$(run_backend_json backend-show-logs --service "$service" --lines 80)" || {
          pause_screen
          continue
        }
        printf '%s\n' "$(json_value "$logs_json" "data['logs']")"
        pause_screen
        ;;
      6)
        section "删除节点"
        local selected_remove rc_remove remove_tag remove_name confirm_remove remove_json
        set +e
        selected_remove="$(select_node)"
        rc_remove=$?
        set -e
        if [[ $rc_remove -eq 2 ]]; then
          continue
        fi
        if [[ $rc_remove -ne 0 ]]; then
          pause_screen
          continue
        fi
        remove_tag="$(printf '%s' "$selected_remove" | awk -F '\t' '{print $2}')"
        remove_name="$(printf '%s' "$selected_remove" | awk -F '\t' '{print $3}')"
        read -r -p "确认删除 ${remove_name} 吗？[y/N]: " confirm_remove || exit 1
        if [[ "${confirm_remove,,}" == "y" ]]; then
          remove_json="$(run_backend_json backend-remove-node --tag "$remove_tag")" || {
            pause_screen
            continue
          }
          ok "节点已删除"
          printf '节点: %s\n' "$(json_value "$remove_json" "data['removed']['name']")"
          printf 'UFW 放行端口: %s\n' "$(json_value "$remove_json" "data['allow_ports']")"
        else
          warn "已取消删除"
        fi
        pause_screen
        ;;
      7)
        section "BBR 状态"
        json_print "$(run_backend_json backend-bbr-status)" bbr
        pause_screen
        ;;
      8)
        section "设置 UFW 防火墙"
        info "脚本会自动保留 22、当前 SSH 端口和所有已部署节点端口"
        read -r -p "如果你还有别的服务要对外开放，请填写额外 TCP 端口（可留空，逗号分隔）: " extra_allow || exit 1
        local fw_json
        fw_json="$(run_backend_json backend-firewall --allow-ports "${extra_allow:-}" --show-status)" || {
          pause_screen
          continue
        }
        ok "UFW 规则已刷新"
        printf '当前 TCP 放行端口: %s\n' "$(json_value "$fw_json" "data['allow_ports']")"
        printf '%s\n' "$(json_value "$fw_json" "data['status']")"
        pause_screen
        ;;
      9)
        modify_streaming_dns_flow
        pause_screen
        ;;
      10)
        show_reality_help
        pause_screen
        ;;
      11)
        self_update_flow
        ;;
      0) exit 0 ;;
      *) warn "未知选项"; pause_screen ;;
    esac
  done
}

main() {
  if [[ "${1:-}" == "--init" ]]; then
    show_overview
    exit 0
  fi
  menu_loop
}

main "$@"
