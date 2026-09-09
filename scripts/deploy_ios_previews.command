#!/bin/zsh
# Build and refresh both RHYTHMOS iOS previews after an iOS source change.
# The Simulator is always refreshed; a connected physical iPhone is refreshed
# when Xcode's device service can see it.
set -euo pipefail

script_path="${0:A}"
project_root="$(cd "$(dirname "$script_path")/.." && pwd)"
project_path="$project_root/ios/RHYTHMOS.xcodeproj"
scheme="RHYTHMOS"
bundle_id="com.rhythmos.ios"
simulator_derived_data="$project_root/.build/ios-derived"
device_derived_data="$project_root/.build/ios-device"

simulator_id="$(
  /usr/bin/xcrun simctl list devices available |
    /usr/bin/awk -F '[()]' '/iPhone/ { print $2; exit }'
)"

if [[ -z "$simulator_id" ]]; then
  echo "没有找到可用的 iPhone Simulator。"
  exit 1
fi

echo "更新 Simulator 预览…"
/usr/bin/xcodebuild -project "$project_path" -scheme "$scheme" -configuration Debug \
  -sdk iphonesimulator -derivedDataPath "$simulator_derived_data" CODE_SIGNING_ALLOWED=NO build
simulator_app="$simulator_derived_data/Build/Products/Debug-iphonesimulator/RHYTHMOS.app"
/usr/bin/xcrun simctl boot "$simulator_id" 2>/dev/null || true
/usr/bin/xcrun simctl bootstatus "$simulator_id" -b
/usr/bin/xcrun simctl install "$simulator_id" "$simulator_app"

desktop_token="$(/usr/bin/security find-generic-password -w -a 'RHYTHMOS desktop sync' -s 'RHYTHMOS.mobile-sync-token' 2>/dev/null || true)"
if [[ -n "$desktop_token" ]]; then
  SIMCTL_CHILD_RHYTHMOS_SIMULATOR_SYNC_URL="https://rhythmos-bk8d.onrender.com" \
  SIMCTL_CHILD_RHYTHMOS_SIMULATOR_SYNC_TOKEN="$desktop_token" \
    /usr/bin/xcrun simctl launch --terminate-running-process "$simulator_id" "$bundle_id"
else
  /usr/bin/xcrun simctl launch --terminate-running-process "$simulator_id" "$bundle_id"
fi
unset desktop_token
/usr/bin/open -a Simulator

physical_device_id="$(
  /usr/bin/xcrun devicectl list devices |
    /usr/bin/awk '$0 ~ / connected / { print $3; exit }'
)"
if [[ -z "$physical_device_id" ]]; then
  if /usr/bin/xcrun devicectl list devices | /usr/bin/grep -q 'available (paired)'; then
    echo "Simulator 已更新；iPhone 已配对但当前未通过数据线连接，真机安装将在连接后执行。"
  else
    echo "Simulator 已更新；未检测到已连接的 iPhone，跳过真机安装。"
  fi
  exit 0
fi

echo "更新已连接的 iPhone…"
/usr/bin/xcodebuild -project "$project_path" -scheme "$scheme" -configuration Debug \
  -destination "platform=iOS,id=$physical_device_id" -derivedDataPath "$device_derived_data" build
device_app="$device_derived_data/Build/Products/Debug-iphoneos/RHYTHMOS.app"
entitlements="$device_derived_data/Build/Intermediates.noindex/RHYTHMOS.build/Debug-iphoneos/RHYTHMOS.build/RHYTHMOS.app.xcent"

# Xcode sometimes leaves extended attributes on a local Debug bundle. Preserve
# the signing identity before clearing them, then re-sign the exact build.
signing_identity="$(/usr/bin/codesign -d --verbose=4 "$device_app" 2>&1 | /usr/bin/awk -F= '/^Authority=Apple Development:/{ print $2; exit }')"
/usr/bin/xattr -cr "$device_app"
if [[ -n "$signing_identity" ]]; then
  /usr/bin/codesign --force --sign "$signing_identity" --entitlements "$entitlements" \
    --timestamp=none --generate-entitlement-der "$device_app"
fi
/usr/bin/codesign --verify --deep --strict "$device_app"
/usr/bin/xcrun devicectl device install app --device "$physical_device_id" "$device_app"
/usr/bin/xcrun devicectl device process launch --device "$physical_device_id" "$bundle_id"

echo "Simulator 与 iPhone 均已更新。"
