#!/usr/bin/env bash
# E2E trên repo sandbox thuộc org, mô hình workspace: chạy trong thư mục workspace,
# clone sandbox (repo trống hoặc đã chạy e2e trước đó, đã có remote) nằm ở ./repo.
# Chạy lại được: mỗi lần dùng key Epic mới và title có hậu tố RUN.
# Dùng: bash <omi-hub>/tests/e2e.sh <omi-hub>
set -euo pipefail
OMI="python $1/scripts/omi.py"
RUN=$(date +%s)
if git -C repo rev-parse -q --verify origin/main >/dev/null; then   # sandbox đã dùng: về main mới nhất
  git -C repo checkout -q main && git -C repo pull -q
fi
$OMI init --repo-dir repo --milestone "e2e" \
  --test-cmd "python -c \"import glob,sys; sys.exit(not glob.glob('e2e*.txt'))\"" \
  --accept-cmd "python -c \"print('test_ac{n}_1 ok')\""
# Việc của người sau init: commit .github/ (repo trống cần commit gốc để `gh issue develop` tạo branch)
git -C repo add .github
if ! git -C repo diff --cached --quiet; then
  git -C repo commit -m "chore: omi init" && git -C repo branch -M main && git -C repo push -u origin main
fi

K=$(printf 'E%03d' $(( $($OMI tree | grep -c '\[Epic\]' || true) + 1 )))
cat > /tmp/omi-e2e-plan.json <<EOF
{"milestone": "e2e", "items": [
  {"key": "$K", "type": "Epic", "title": "Kiểm thử e2e omi $RUN",
   "body": "### Mục tiêu\nXác nhận pipeline omi\n\n### Phạm vi\n- một story, một task", "children": [
    {"key": "$K.S001", "type": "User Story", "title": "Dev có thể chạy e2e $RUN",
     "body": "### Story\nLà dev, tôi muốn chạy e2e để kiểm tra omi.\n\n### Acceptance criteria\n- [ ] file e2e-$RUN.txt tồn tại",
     "children": [
      {"key": "$K.S001.T001", "type": "Task", "title": "Tạo file e2e-$RUN.txt",
       "body": "### Việc cần làm\nTạo e2e-$RUN.txt\n\n### Definition of done\n- [ ] Test pass"}]}]}]}
EOF
$OMI plan-show /tmp/omi-e2e-plan.json
$OMI apply /tmp/omi-e2e-plan.json --approve
test -z "$($OMI apply /tmp/omi-e2e-plan.json --approve)"   # idempotent: không tạo thêm
if $OMI new Task "x" --parent 1 2>/dev/null; then echo "template FAIL: title sai mẫu vẫn tạo được"; exit 1; fi

E=$($OMI tree | grep "Kiểm thử e2e omi $RUN" | sed -E 's/^ *#([0-9]+).*/\1/')
T=$($OMI start | grep -oE 'START #[0-9]+' | grep -oE '[0-9]+')
echo ok > "repo/e2e-$RUN.txt" && git -C repo add "e2e-$RUN.txt" && git -C repo commit -m "#$T: e2e"
test ! -e repo/AGENTS.md && test ! -e repo/.omi             # file agent/omi không lọt vào repo
$OMI check | grep -q "CHECK PASS"
SUB=$($OMI submit "$T"); echo "$SUB" | grep -q "reviewers=code"
PR=$(echo "$SUB" | grep -oE 'PR #[0-9]+' | grep -oE '[0-9]+')
$OMI pr-lint "$PR" | grep -q "PR OK"              # PR do script sinh đúng template
$OMI review-done "$T" --fail "e2e rework"     # review FAIL: ghi marker + rework
$OMI submit "$T" | grep -q "reviewers=none"       # review LLM chỉ 1 lượt
$OMI qa "$T" | tee /tmp/omi-e2e-qa.out
grep -q "DONE #$T" /tmp/omi-e2e-qa.out
grep -q "ACCEPT PASS" /tmp/omi-e2e-qa.out
$OMI tree "$E" | grep -q "Kiểm thử e2e omi $RUN — Done" && echo "rollup OK"
$OMI audit && echo "audit OK"
