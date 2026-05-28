#!/bin/bash
# install_updater.sh — 安装自动更新定时任务（macOS launchd）
# 每 4 小时自动更新 K 线数据

PLIST_PATH="$HOME/Library/LaunchAgents/com.btc.dataupdater.plist"
SCRIPT_DIR="$(cd "$(dirname "$0")/.." && pwd)"

cat > "$PLIST_PATH" << EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.btc.dataupdater</string>
    <key>ProgramArguments</key>
    <array>
        <string>${SCRIPT_DIR}/freqtrade/.venv/bin/python</string>
        <string>${SCRIPT_DIR}/scripts/auto_updater.py</string>
    </array>
    <key>StartInterval</key>
    <integer>14400</integer>
    <key>RunAtLoad</key>
    <true/>
    <key>StandardOutPath</key>
    <string>${SCRIPT_DIR}/logs/updater.log</string>
    <key>StandardErrorPath</key>
    <string>${SCRIPT_DIR}/logs/updater_err.log</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>/usr/local/bin:/usr/bin:/bin</string>
        <key>HTTPS_PROXY</key>
        <string>http://127.0.0.1:1087</string>
        <key>HTTP_PROXY</key>
        <string>http://127.0.0.1:1087</string>
    </dict>
</dict>
</plist>
EOF

# 创建日志目录
mkdir -p "${SCRIPT_DIR}/logs"

# 加载定时任务
launchctl load "$PLIST_PATH"

echo "✅ 数据自动更新器已安装"
echo "   ⏱  每 4 小时运行一次"
echo "   📋 日志: ${SCRIPT_DIR}/logs/updater.log"
echo ""
echo "手动控制:"
echo "  启动: launchctl start com.btc.dataupdater"
echo "  停止: launchctl stop com.btc.dataupdater"
echo "  卸载: launchctl unload $PLIST_PATH"
