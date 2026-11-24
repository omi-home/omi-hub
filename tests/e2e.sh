#!/usr/bin/env bash
# E2E trên repo sandbox thuộc org, mô hình workspace: chạy trong thư mục workspace,
# clone sandbox (repo trống, đã có remote) nằm ở ./repo.
# Dùng: bash <omi-hub>/tests/e2e.sh <omi-hub>
set -euo pipefail
OMI="python $1/scripts/omi.py"
$OMI init --repo-dir repo --milestone "e2e" \
  --test-cmd "python -c \"import os,sys; sys.exit(not os.path.exists('e2e.txt'))\"" \
  --accept-cmd "python -c \"print('test_ac{n}_1 ok')\""

cat > /tmp/omi-e2e-plan.json <<'EOF'
{"milestone": "e2e", "items": [
  {"key": "E001", "type": "Epic", "title": "Kiểm thử e2e omi",
   "body": "### Mục tiêu\nXác nhận pipeline omi\n\n### Phạm vi\n- một story, một task", "children": [
    {"key": "E001.S001", "type": "User Story", "title": "Dev có thể chạy e2e",
     "body": "### Story\nLà dev, tôi muốn chạy e2e để kiểm tra omi.\n\n### Acceptance criteria\n- [ ] file e2e.txt tồn tại",
     "children": [
      {"key": "E001.S001.T001", "type": "Task", "title": "Tạo file e2e.txt",
       "body": "### Việc cần làm\nTạo e2e.txt\n\n### Definition of done\n- [ ] Test pass"}]}]}]}
EOF
$OMI plan-show /tmp/omi-e2e-plan.json
$OMI apply /tmp/omi-e2e-plan.json --approve
$OMI apply /tmp/omi-e2e-plan.json --approve   # idempotent: không tạo thêm
if $OMI new Task "x" --parent 1 2>/dev/null; then echo "template FAIL: title sai mẫu vẫn tạo được"; exit 1; fi

E=$($OMI tree | grep "Kiểm thử e2e omi" | sed -E 's/^ *#([0-9]+).*/\1/')
T=$($OMI start | grep -oE 'START #[0-9]+' | grep -oE '[0-9]+')
echo ok > repo/e2e.txt && git -C repo add e2e.txt && git -C repo commit -m "#$T: e2e"
test ! -e repo/AGENTS.md && test ! -e repo/.omi             # file agent/omi không lọt vào repo
$OMI check | grep -q "CHECK PASS"
SUB=$($OMI submit "$T"); echo "$SUB" | grep -q "reviewers=code"
PR=$(echo "$SUB" | grep -oE 'PR #[0-9]+' | grep -oE '[0-9]+')
$OMI pr-lint "$PR" | grep -q "PR OK"              # PR do script sinh đúng template
$OMI rework "$T" --reason "e2e rework"
$OMI submit "$T" | grep -q "reviewers=none"       # review LLM chỉ 1 lượt
$OMI qa "$T" | tee /tmp/omi-e2e-qa.out
grep -q "DONE #$T" /tmp/omi-e2e-qa.out
grep -q "ACCEPT PASS" /tmp/omi-e2e-qa.out
$OMI tree "$E" | grep -q "Kiểm thử e2e omi — Done" && echo "rollup OK"
$OMI audit && echo "audit OK"
