#!/usr/bin/env bash
# maya-test.sh — 验证 Maya 远程开发基础设施
# 用法: bash maya-test.sh [--quick]

set +e  # manual error handling
PASS=0; FAIL=0; TOTAL=0
MEXEC="bash ${HOME}/.hermes/scripts/maya-exec"
MSS="bash ${HOME}/.hermes/scripts/maya-screenshot.sh"
MPUSH="bash ${HOME}/.hermes/scripts/maya-push.sh"

green() { echo -e "\033[32m✓ PASS\033[0m $1"; ((PASS+=1)); }
red()   { echo -e "\033[31m✗ FAIL\033[0m $1"; ((FAIL+=1)); }
test_banner() { echo ""; echo "── $1 ──"; ((TOTAL+=1)); }

echo "╔══════════════════════════════════╗"
echo "║  Maya Remote Infrastructure Test ║"
echo "╚══════════════════════════════════╝"

# ── 1. SSH Connectivity ──
test_banner "1. SSH Connectivity"
ssh -o ConnectTimeout=5 19183@192.168.0.101 "echo OK" 2>/dev/null \
  && green "SSH to Windows" \
  || red "SSH to Windows"

# ── 2. Listener Ping ──
test_banner "2. Listener /ping"
PONG=$($MEXEC -r "/ping" 2>/dev/null)
if [[ "$PONG" == PONG:* ]]; then
    green "/ping → $PONG"
else
    red "/ping → $PONG"
fi

# ── 3. Listener /status ──
test_banner "3. Listener /status"
STATUS=$($MEXEC -r "/status" 2>/dev/null)
if [[ "$STATUS" == STATUS* ]]; then
    green "/status → $STATUS"
else
    red "/status → $STATUS"
fi

# ── 4. Python Execution ──
test_banner "4. Python code execution"
RES=$($MEXEC "print(1+1)" 2>/dev/null)
if [ "$RES" = "2" ]; then
    green "print(1+1) = 2"
else
    red "print(1+1) → $RES"
fi

# ── 5. Maya Command ──
test_banner "5. Maya command (cmds.polySphere)"
RES=$($MEXEC "cmds.polySphere(r=1)" 2>/dev/null)
if [[ "$RES" == *(ok)* ]]; then
    green "polySphere created"
else
    red "polySphere → $RES"
fi

# ── 6. Batch Execution ──
test_banner "6. Batch execution"
RES=$(printf "/batch\nprint(2+2)\nprint(3+3)" | $MEXEC -r "" 2>/dev/null)
if [[ "$RES" == *"4"* && "$RES" == *"6"* ]]; then
    green "batch: 2+2=4, 3+3=6"
else
    red "batch → $RES"
fi

# ── 7. Screenshot ──
test_banner "7. Screenshot"
SS_OUTPUT=$($MSS 2>/dev/null)
SS_FILE=$(echo "$SS_OUTPUT" | grep "^SS_FILE=" | sed 's/^SS_FILE=//')
if [ -n "$SS_FILE" ] && [ -f "$SS_FILE" ]; then
    SIZE=$(stat -c%s "$SS_FILE" 2>/dev/null || echo 0)
    if [ "$SIZE" -gt 10000 ]; then
        green "screenshot ${SIZE}B"
    else
        red "screenshot too small: ${SIZE}B"
    fi
else
    red "screenshot failed"
fi

# ── 8. File Push ──
test_banner "8. File push"
echo "# PUSH-TEST" > /tmp/_mtest_push.py
$MPUSH /tmp/_mtest_push.py "D:\\maya_projects\\output\\_mtest_push.py" >/dev/null 2>&1
EXISTS=$(ssh 19183@192.168.0.101 "powershell -NoProfile -Command \"if (Test-Path 'D:\\maya_projects\\output\\_mtest_push.py') { 'TRUE' } else { 'FALSE' }\"" 2>/dev/null | tr -d '\r')
if [ "$EXISTS" = "TRUE" ]; then
    green "file pushed to Windows"
else
    red "push failed"
fi

# ── 9. File Pull ──
test_banner "9. File pull"
bash ${HOME}/.hermes/scripts/maya-pull.sh "D:\\maya_projects\\output\\_mtest_push.py" /tmp/_mtest_pull.py >/dev/null 2>&1
if [ -f /tmp/_mtest_pull.py ] && grep -q "PUSH-TEST" /tmp/_mtest_pull.py; then
    green "file pulled from Windows"
else
    red "pull failed"
fi

# ── Cleanup ──
ssh 19183@192.168.0.101 "powershell -NoProfile -Command \"Remove-Item 'D:\\maya_projects\\output\\_mtest_push.py' -Force -ErrorAction SilentlyContinue\"" 2>/dev/null || true
rm -f /tmp/_mtest_push.py /tmp/_mtest_pull.py

# ── Summary ──
echo ""
echo "╔══════════════════════════════════╗"
echo "║  Results: ${PASS}/${TOTAL} passed, ${FAIL} failed     ║"
echo "╚══════════════════════════════════╝"
[ "$FAIL" -eq 0 ] || exit 1
