#!/usr/bin/env bash
# End-to-end smoke test for auto-opt microservices
# Usage: ./tests/e2e_smoke.sh [RECIPE_BASE_URL]
#
# Requires: curl, jq
set -euo pipefail

BASE="${1:-http://localhost:9002}"
PASS=0
FAIL=0

green()  { printf "\033[32m%s\033[0m\n" "$*"; }
red()    { printf "\033[31m%s\033[0m\n" "$*"; }
header() { printf "\n\033[1;36m=== %s ===\033[0m\n" "$*"; }

assert_status() {
  local label="$1" expected="$2" actual="$3"
  if [[ "$actual" == "$expected" ]]; then
    green "  PASS: $label (HTTP $actual)"
    PASS=$((PASS + 1))
  else
    red "  FAIL: $label — expected $expected, got $actual"
    FAIL=$((FAIL + 1))
  fi
}

assert_json_field() {
  local label="$1" json="$2" field="$3" expected="$4"
  local actual
  actual=$(echo "$json" | jq -r "$field")
  if [[ "$actual" == "$expected" ]]; then
    green "  PASS: $label ($field=$actual)"
    PASS=$((PASS + 1))
  else
    red "  FAIL: $label — $field expected '$expected', got '$actual'"
    FAIL=$((FAIL + 1))
  fi
}

assert_json_field_exists() {
  local label="$1" json="$2" field="$3"
  local val
  val=$(echo "$json" | jq "$field")
  if [[ "$val" != "null" && -n "$val" ]]; then
    green "  PASS: $label ($field exists)"
    PASS=$((PASS + 1))
  else
    red "  FAIL: $label — $field is null or missing"
    FAIL=$((FAIL + 1))
  fi
}

# ── 0. Health checks ──────────────────────────────────────────────
header "Health Checks"

for svc_port in "optics-sim:9001" "recipe-service:9002" "position-service:9004" "bolt-service:9005"; do
  svc="${svc_port%%:*}"
  port="${svc_port##*:}"
  status=$(curl -s -o /dev/null -w "%{http_code}" "http://localhost:${port}/health")
  assert_status "$svc /health" "200" "$status"
done

# ── 1. Create experiment ──────────────────────────────────────────
header "1. Create Experiment"

BODY='{
  "name": "e2e_smoke_test",
  "optical_system": {
    "wavelength": 780, "ld_tilt": 0.0,
    "ld_div_fast": 25.0, "ld_div_slow": 8.0,
    "ld_div_fast_err": 0.0, "ld_div_slow_err": 0.0,
    "ld_emit_w": 3.0, "ld_emit_h": 1.0, "num_rays": 100,
    "coll_r1": -3.5, "coll_r2": -15.0,
    "coll_k1": -1.0, "coll_k2": 0.0,
    "coll_t": 2.0, "coll_n": 1.517, "dist_ld_coll": 4.0,
    "obj_f": 4.0, "dist_coll_obj": 50.0, "sensor_pos": 4.0
  },
  "bolt_model": {
    "upper": {"shift_x_per_nm": 0.001, "shift_y_per_nm": 0.003, "noise_std_x": 0.002, "noise_std_y": 0.005},
    "lower": {"shift_x_per_nm": -0.0005, "shift_y_per_nm": 0.002, "noise_std_x": 0.001, "noise_std_y": 0.003}
  },
  "camera": {
    "pixel_w": 640, "pixel_h": 480,
    "pixel_pitch_um": 5.3, "gaussian_sigma_px": 3.0
  }
}'

RESP=$(curl -s -w "\n%{http_code}" -X POST "$BASE/experiments" -H "Content-Type: application/json" -d "$BODY")
HTTP_CODE=$(echo "$RESP" | tail -1)
JSON=$(echo "$RESP" | sed '$d')
assert_status "POST /experiments" "201" "$HTTP_CODE"
assert_json_field "experiment_id format" "$JSON" ".experiment_id" "exp_001"

EXP_ID=$(echo "$JSON" | jq -r ".experiment_id")
echo "  → experiment_id=$EXP_ID"

# ── 2. List experiments ───────────────────────────────────────────
header "2. List Experiments"

RESP=$(curl -s -w "\n%{http_code}" "$BASE/experiments")
HTTP_CODE=$(echo "$RESP" | tail -1)
JSON=$(echo "$RESP" | sed '$d')
assert_status "GET /experiments" "200" "$HTTP_CODE"

COUNT=$(echo "$JSON" | jq '.experiments | length')
if [[ "$COUNT" -ge 1 ]]; then
  green "  PASS: experiments count=$COUNT"
  PASS=$((PASS + 1))
else
  red "  FAIL: experiments count=$COUNT (expected >=1)"
  FAIL=$((FAIL + 1))
fi

# ── 3. Get experiment detail ──────────────────────────────────────
header "3. Get Experiment Detail"

RESP=$(curl -s -w "\n%{http_code}" "$BASE/experiments/$EXP_ID")
HTTP_CODE=$(echo "$RESP" | tail -1)
JSON=$(echo "$RESP" | sed '$d')
assert_status "GET /experiments/$EXP_ID" "200" "$HTTP_CODE"
assert_json_field "experiment name" "$JSON" ".name" "e2e_smoke_test"
assert_json_field "camera pixel_w" "$JSON" ".camera.pixel_w" "640"
assert_json_field "camera pixel_h" "$JSON" ".camera.pixel_h" "480"
assert_json_field "camera pixel_pitch_um" "$JSON" ".camera.pixel_pitch_um" "5.3"
assert_json_field "camera gaussian_sigma_px" "$JSON" ".camera.gaussian_sigma_px" "3.0"

# ── 4. Create trial ──────────────────────────────────────────────
header "4. Create Trial"

RESP=$(curl -s -w "\n%{http_code}" -X POST "$BASE/experiments/$EXP_ID/trials" \
  -H "Content-Type: application/json" -d '{"mode": "manual", "control": null}')
HTTP_CODE=$(echo "$RESP" | tail -1)
JSON=$(echo "$RESP" | sed '$d')
assert_status "POST .../trials" "201" "$HTTP_CODE"
assert_json_field "trial mode" "$JSON" ".mode" "manual"

TRIAL_ID=$(echo "$JSON" | jq -r ".trial_id")
echo "  → trial_id=$TRIAL_ID"

# ── 5. Execute step (Position → Sim → Bolt → Sim) ────────────────
header "5. Execute Step"

STEP_BODY='{
  "coll_x": 0.02, "coll_y": -0.05,
  "torque_upper": 0.5, "torque_lower": 0.5,
  "options": {"return_ray_hits": false, "return_images": false}
}'

RESP=$(curl -s -w "\n%{http_code}" -X POST \
  "$BASE/experiments/$EXP_ID/trials/$TRIAL_ID/steps" \
  -H "Content-Type: application/json" -d "$STEP_BODY")
HTTP_CODE=$(echo "$RESP" | tail -1)
JSON=$(echo "$RESP" | sed '$d')
assert_status "POST .../steps" "200" "$HTTP_CODE"
assert_json_field "step_index" "$JSON" ".step_index" "0"
assert_json_field_exists "after_position.coll_x_shift" "$JSON" ".after_position.coll_x_shift"
assert_json_field_exists "sim_after_position.spot_center_x" "$JSON" ".sim_after_position.spot_center_x"
assert_json_field_exists "bolt_shift.delta_x" "$JSON" ".bolt_shift.delta_x"
assert_json_field_exists "bolt_shift.used_seed" "$JSON" ".bolt_shift.used_seed"
assert_json_field_exists "sim_after_bolt.spot_center_x" "$JSON" ".sim_after_bolt.spot_center_x"
assert_json_field_exists "saved_to" "$JSON" ".saved_to"

SPOT_X=$(echo "$JSON" | jq ".sim_after_bolt.spot_center_x")
SPOT_Y=$(echo "$JSON" | jq ".sim_after_bolt.spot_center_y")
RMS=$(echo "$JSON" | jq ".sim_after_bolt.spot_rms_radius")
echo "  → spot=($SPOT_X, $SPOT_Y) rms=$RMS"

# ── 6. Execute a second step (verify step_index=1) ───────────────
header "6. Execute Second Step"

STEP2_BODY='{
  "coll_x": 0.01, "coll_y": -0.03,
  "torque_upper": 0.5, "torque_lower": 0.5,
  "options": {"return_ray_hits": true, "return_images": false}
}'

RESP=$(curl -s -w "\n%{http_code}" -X POST \
  "$BASE/experiments/$EXP_ID/trials/$TRIAL_ID/steps" \
  -H "Content-Type: application/json" -d "$STEP2_BODY")
HTTP_CODE=$(echo "$RESP" | tail -1)
JSON=$(echo "$RESP" | sed '$d')
assert_status "POST .../steps (step 2)" "200" "$HTTP_CODE"
assert_json_field "step_index=1" "$JSON" ".step_index" "1"

RAY_HITS_LEN=$(echo "$JSON" | jq '.sim_after_bolt.ray_hits | length')
if [[ "$RAY_HITS_LEN" -gt 0 ]]; then
  green "  PASS: ray_hits returned ($RAY_HITS_LEN hits)"
  PASS=$((PASS + 1))
else
  red "  FAIL: ray_hits empty or null"
  FAIL=$((FAIL + 1))
fi

# ── 7. List steps ─────────────────────────────────────────────────
header "7. List Steps"

RESP=$(curl -s -w "\n%{http_code}" "$BASE/experiments/$EXP_ID/trials/$TRIAL_ID/steps")
HTTP_CODE=$(echo "$RESP" | tail -1)
JSON=$(echo "$RESP" | sed '$d')
assert_status "GET .../steps" "200" "$HTTP_CODE"

STEP_COUNT=$(echo "$JSON" | jq '.steps | length')
if [[ "$STEP_COUNT" -eq 2 ]]; then
  green "  PASS: 2 steps listed"
  PASS=$((PASS + 1))
else
  red "  FAIL: expected 2 steps, got $STEP_COUNT"
  FAIL=$((FAIL + 1))
fi

# ── 8. Get step detail ────────────────────────────────────────────
header "8. Get Step Detail"

RESP=$(curl -s -w "\n%{http_code}" "$BASE/experiments/$EXP_ID/trials/$TRIAL_ID/steps/0")
HTTP_CODE=$(echo "$RESP" | tail -1)
JSON=$(echo "$RESP" | sed '$d')
assert_status "GET .../steps/0" "200" "$HTTP_CODE"
assert_json_field "step_index=0" "$JSON" ".step_index" "0"
assert_json_field_exists "command.coll_x" "$JSON" ".command.coll_x"

# ── 9. Get step images ────────────────────────────────────────────
header "9. Get Step Images (after_bolt)"

RESP=$(curl -s -w "\n%{http_code}" -X POST \
  "$BASE/experiments/$EXP_ID/trials/$TRIAL_ID/steps/0/images" \
  -H "Content-Type: application/json" -d '{"phase": "after_bolt"}')
HTTP_CODE=$(echo "$RESP" | tail -1)
JSON=$(echo "$RESP" | sed '$d')
assert_status "POST .../steps/0/images" "200" "$HTTP_CODE"

RAY_IMG_LEN=$(echo "$JSON" | jq -r '.ray_path_image | length')
SPOT_IMG_LEN=$(echo "$JSON" | jq -r '.spot_diagram_image | length')
if [[ "$RAY_IMG_LEN" -gt 100 ]]; then
  green "  PASS: ray_path_image returned (${RAY_IMG_LEN} chars)"
  PASS=$((PASS + 1))
else
  red "  FAIL: ray_path_image missing or too short ($RAY_IMG_LEN chars)"
  FAIL=$((FAIL + 1))
fi
if [[ "$SPOT_IMG_LEN" -gt 100 ]]; then
  green "  PASS: spot_diagram_image returned (${SPOT_IMG_LEN} chars)"
  PASS=$((PASS + 1))
else
  red "  FAIL: spot_diagram_image missing or too short ($SPOT_IMG_LEN chars)"
  FAIL=$((FAIL + 1))
fi

# ── 10. Complete trial ────────────────────────────────────────────
header "10. Complete Trial"

RESP=$(curl -s -w "\n%{http_code}" -X POST \
  "$BASE/experiments/$EXP_ID/trials/$TRIAL_ID/complete")
HTTP_CODE=$(echo "$RESP" | tail -1)
JSON=$(echo "$RESP" | sed '$d')
assert_status "POST .../complete" "200" "$HTTP_CODE"
assert_json_field "total_steps" "$JSON" ".total_steps" "2"

# ── 10b. Complete again → 409 ─────────────────────────────────────
header "10b. Complete Again (expect 409)"

RESP=$(curl -s -w "\n%{http_code}" -X POST \
  "$BASE/experiments/$EXP_ID/trials/$TRIAL_ID/complete")
HTTP_CODE=$(echo "$RESP" | tail -1)
assert_status "POST .../complete (duplicate)" "409" "$HTTP_CODE"

# ── 11. Sweep ─────────────────────────────────────────────────────
header "11. Parameter Sweep"

SWEEP_BODY="{
  \"experiment_id\": \"$EXP_ID\",
  \"base_command\": {
    \"coll_x\": 0.0, \"coll_y\": 0.0,
    \"torque_upper\": 0.5, \"torque_lower\": 0.5
  },
  \"sweep\": {
    \"param_name\": \"coll_y\",
    \"values\": [-0.05, 0.0, 0.05]
  }
}"

RESP=$(curl -s -w "\n%{http_code}" -X POST "$BASE/recipes/sweep" \
  -H "Content-Type: application/json" -d "$SWEEP_BODY")
HTTP_CODE=$(echo "$RESP" | tail -1)
JSON=$(echo "$RESP" | sed '$d')
assert_status "POST /recipes/sweep" "200" "$HTTP_CODE"
assert_json_field "sweep_param" "$JSON" ".sweep_param" "coll_y"

RESULT_COUNT=$(echo "$JSON" | jq '.results | length')
if [[ "$RESULT_COUNT" -eq 3 ]]; then
  green "  PASS: 3 sweep results"
  PASS=$((PASS + 1))
else
  red "  FAIL: expected 3 sweep results, got $RESULT_COUNT"
  FAIL=$((FAIL + 1))
fi

# ── 12. Trial list ────────────────────────────────────────────────
header "12. Trial List"

RESP=$(curl -s -w "\n%{http_code}" "$BASE/experiments/$EXP_ID/trials")
HTTP_CODE=$(echo "$RESP" | tail -1)
JSON=$(echo "$RESP" | sed '$d')
assert_status "GET .../trials" "200" "$HTTP_CODE"

TRIAL_COUNT=$(echo "$JSON" | jq '.trials | length')
if [[ "$TRIAL_COUNT" -eq 2 ]]; then
  green "  PASS: 2 trials (manual + sweep)"
  PASS=$((PASS + 1))
else
  red "  FAIL: expected 2 trials, got $TRIAL_COUNT"
  FAIL=$((FAIL + 1))
fi

# ── 13. 404 error paths ──────────────────────────────────────────
header "13. Error Paths"

status=$(curl -s -o /dev/null -w "%{http_code}" "$BASE/experiments/exp_999")
assert_status "GET nonexistent experiment" "404" "$status"

status=$(curl -s -o /dev/null -w "%{http_code}" "$BASE/experiments/$EXP_ID/trials/trial_999")
assert_status "GET nonexistent trial" "404" "$status"

# ── Summary ───────────────────────────────────────────────────────
header "Summary"
TOTAL=$((PASS + FAIL))
echo "  $PASS / $TOTAL passed"
if [[ "$FAIL" -gt 0 ]]; then
  red "  $FAIL FAILED"
  exit 1
else
  green "  All tests passed!"
  exit 0
fi
