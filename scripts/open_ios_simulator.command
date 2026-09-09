#!/bin/zsh
# Double-clickable local RHYTHMOS iOS launcher.
#
# The desktop helper launches this script directly, with no Terminal window.
# When the script itself is double-clicked, it also puts the real work in the
# background so the short-lived Terminal shell can exit immediately.
set -euo pipefail

script_path="${0:A}"
run_in_background=false
for argument in "$@"; do
  if [[ "$argument" == "--background" ]]; then
    run_in_background=true
  fi
done
if [[ "$run_in_background" != "true" ]]; then
  log_path="${TMPDIR:-/tmp}/rhythmos-ios-launch.log"
  /usr/bin/nohup "$script_path" --background >"$log_path" 2>&1 < /dev/null &
  exit 0
fi

project_root="$(cd "$(dirname "$script_path")/.." && pwd)"
project_path="$project_root/ios/RHYTHMOS.xcodeproj"
derived_data="$project_root/.build/ios-derived"
app_path="$derived_data/Build/Products/Debug-iphonesimulator/RHYTHMOS.app"

device_id="$(
  /usr/bin/xcrun simctl list devices available |
    /usr/bin/awk -F '[()]' '/iPhone/ { print $2; exit }'
)"

if [[ -z "$device_id" ]]; then
  echo "没有找到可用的 iPhone Simulator。请先在 Xcode 安装 iOS Simulator runtime。"
  exit 1
fi

source_has_changed=false
if [[ ! -d "$app_path" || "$project_path/project.pbxproj" -nt "$app_path" ]]; then
  source_has_changed=true
elif [[ -n "$(/usr/bin/find "$project_root/ios/RHYTHMOS" -type f -newer "$app_path" -print -quit)" ]]; then
  source_has_changed=true
fi

/usr/bin/xcrun simctl boot "$device_id" 2>/dev/null || true
/usr/bin/xcrun simctl bootstatus "$device_id" -b

# Daily opening path: when the installed build is current, simply launch it.
# A full Xcode build only runs after iOS source/project changes or when the
# Simulator does not yet contain RHYTHMOS.
app_is_installed=false
if /usr/bin/xcrun simctl get_app_container "$device_id" com.rhythmos.ios app >/dev/null 2>&1; then
  app_is_installed=true
fi
if [[ "$source_has_changed" == "true" ]]; then
  echo "正在更新 RHYTHMOS iOS…"
  /usr/bin/xcodebuild -project "$project_path" -scheme RHYTHMOS -configuration Debug -sdk iphonesimulator -derivedDataPath "$derived_data" CODE_SIGNING_ALLOWED=NO build
  /usr/bin/xcrun simctl install "$device_id" "$app_path"
elif [[ "$app_is_installed" != "true" ]]; then
  echo "正在准备 RHYTHMOS iOS…"
  if [[ ! -d "$app_path" ]]; then
    /usr/bin/xcodebuild -project "$project_path" -scheme RHYTHMOS -configuration Debug -sdk iphonesimulator -derivedDataPath "$derived_data" CODE_SIGNING_ALLOWED=NO build
  fi
  /usr/bin/xcrun simctl install "$device_id" "$app_path"
fi

# A Simulator has its own Keychain.  For this local development launcher only,
# pass the existing desktop sync credential as a one-process environment value;
# the app saves it into the Simulator Keychain and never logs or writes it to
# the project.  The physical iPhone is not involved in this path.
desktop_token="$(/usr/bin/security find-generic-password -w -a 'RHYTHMOS desktop sync' -s 'RHYTHMOS.mobile-sync-token' 2>/dev/null || true)"
if [[ -n "$desktop_token" ]]; then
  SIMCTL_CHILD_RHYTHMOS_SIMULATOR_SYNC_URL="https://rhythmos-bk8d.onrender.com" \
  SIMCTL_CHILD_RHYTHMOS_SIMULATOR_SYNC_TOKEN="$desktop_token" \
    /usr/bin/xcrun simctl launch --terminate-running-process "$device_id" com.rhythmos.ios
else
  /usr/bin/xcrun simctl launch --terminate-running-process "$device_id" com.rhythmos.ios
fi
unset desktop_token
/usr/bin/open -a Simulator
