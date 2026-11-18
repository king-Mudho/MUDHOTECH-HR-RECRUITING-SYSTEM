#!/usr/bin/env bash
# CloudWatch alarms for MHRS (P11-T07, docs/10 §8, docs/deployment/AWS_SETUP.md §10). Idempotent: re-running
# updates every alarm in place. Owner step (needs AWS credentials with CloudWatch/SNS/Logs rights).
#
#   ENV=production ONCALL_EMAIL=oncall@example.co.zw INSTANCE_ID=i-0123 DB_INSTANCE=mhrs-production-db \
#     infrastructure/monitoring/alarms.sh
#   ENV=production infrastructure/monitoring/alarms.sh --test     # fire one test alarm end to end (go-live gate)
#
# Sources: application metrics from apps/core/ops_metrics.py (every minute), host metrics from the CloudWatch
# agent and infrastructure/monitoring/host-checks.sh, backup.sh's BackupSucceeded, the nginx access log
# (metric filters below), and AWS/EC2 + AWS/RDS + AWS/SES.
set -euo pipefail

ENV="${ENV:?set ENV=staging|production}"
[[ $ENV =~ ^(staging|production)$ ]] || { echo "ENV must be staging or production" >&2; exit 1; }
NS="MHRS/$ENV"
REGION="${AWS_REGION:-af-south-1}"
TOPIC_NAME="mhrs-$ENV-alerts"
export AWS_DEFAULT_REGION="$REGION"

topic_arn=$(aws sns create-topic --name "$TOPIC_NAME" --query TopicArn --output text)   # idempotent

if [[ ${1:-} == --test ]]; then
  name="mhrs-$ENV-dead-letters"
  aws cloudwatch set-alarm-state --alarm-name "$name" --state-value ALARM \
    --state-reason "Test alarm from alarms.sh --test ($(date -u +%FT%TZ)) - no action needed"
  echo "set $name to ALARM: an email should reach the on-call address within a few minutes."
  echo "It returns to OK at the next evaluation (1 minute)."
  exit 0
fi

if [[ -n ${ONCALL_EMAIL:-} ]]; then
  aws sns subscribe --topic-arn "$topic_arn" --protocol email --notification-endpoint "$ONCALL_EMAIL" >/dev/null
  echo "subscribed $ONCALL_EMAIL to $TOPIC_NAME (confirm the email AWS sends)"
fi

alarm() {
  # alarm <name> <namespace> <metric> <stat> <period> <evals> <op> <threshold> <missing> [dimensions...]
  local name="$1" ns="$2" metric="$3" stat="$4" period="$5" evals="$6" op="$7" threshold="$8" missing="$9"
  shift 9
  local -a dims=()
  (($#)) && dims=(--dimensions "$@")   # each "Name=<n>,Value=<v>"
  aws cloudwatch put-metric-alarm --alarm-name "mhrs-$ENV-$name" --namespace "$ns" --metric-name "$metric" \
    --statistic "$stat" --period "$period" --evaluation-periods "$evals" --comparison-operator "$op" \
    --threshold "$threshold" --treat-missing-data "$missing" \
    --alarm-actions "$topic_arn" --ok-actions "$topic_arn" "${dims[@]}"
  echo "alarm mhrs-$ENV-$name"
}

# --- application (apps/core/ops_metrics.py) --------------------------------------------------------------
alarm documents-queue "$NS" QueueDepth Maximum 300 1 GreaterThanThreshold 500 notBreaching Name=Queue,Value=documents
alarm processing-backlog "$NS" ProcessingBacklogAgeSeconds Maximum 300 1 GreaterThanThreshold 900 notBreaching
alarm outbox-lag "$NS" OutboxLagSeconds Maximum 300 1 GreaterThanThreshold 300 notBreaching
alarm dead-letters "$NS" DeadLettersOpen Maximum 300 1 GreaterThanThreshold 10 notBreaching
alarm email-failures "$NS" EmailFailureRatePercent Maximum 3600 1 GreaterThanThreshold 5 notBreaching
alarm clamav-signatures "$NS" ClamavSignatureAgeHours Maximum 3600 1 GreaterThanThreshold 48 breaching
# the metrics task itself stopped (beat/worker down): no data for 10 minutes
alarm ops-metrics-missing "$NS" DeadLettersOpen SampleCount 300 2 LessThanThreshold 1 breaching
alarm ops-metric-sources "$NS" OpsMetricSourceErrors Maximum 300 2 GreaterThanThreshold 0 notBreaching

# --- host (CloudWatch agent, host-checks.sh, backup.sh) ---------------------------------------------------
alarm cert-expiry "$NS" CertDaysLeft Minimum 3600 1 LessThanThreshold 14 breaching
alarm unhealthy-containers "$NS" UnhealthyContainers Maximum 900 1 GreaterThanThreshold 0 breaching
# weekly backup: host-checks.sh publishes the hours since backup.sh last succeeded (alarm after 8 days)
alarm backup-age "$NS" BackupAgeHours Maximum 3600 1 GreaterThanThreshold 192 breaching
alarm backup-failed "$NS" BackupSucceeded Minimum 3600 1 LessThanThreshold 1 notBreaching
if [[ -n ${INSTANCE_ID:-} ]]; then
  alarm memory "$NS" mem_used_percent Average 300 2 GreaterThanThreshold 90 missing "Name=InstanceId,Value=$INSTANCE_ID"
  alarm disk-root "$NS" disk_used_percent Maximum 300 1 GreaterThanThreshold 80 missing \
    "Name=InstanceId,Value=$INSTANCE_ID" "Name=path,Value=/"
  alarm disk-docker "$NS" disk_used_percent Maximum 300 1 GreaterThanThreshold 80 missing \
    "Name=InstanceId,Value=$INSTANCE_ID" "Name=path,Value=/var/lib/docker"
fi

# --- nginx: 5xx rate > 2 % over 5 minutes (with at least 50 requests) -------------------------------------
LOG_GROUP="/mhrs/$ENV/nginx"
aws logs create-log-group --log-group-name "$LOG_GROUP" 2>/dev/null || true
aws logs put-metric-filter --log-group-name "$LOG_GROUP" --filter-name requests \
  --filter-pattern '{ $.status = * }' \
  --metric-transformations "metricName=Requests,metricNamespace=$NS,metricValue=1,defaultValue=0"
aws logs put-metric-filter --log-group-name "$LOG_GROUP" --filter-name server-errors \
  --filter-pattern '{ $.status >= 500 }' \
  --metric-transformations "metricName=Server5xx,metricNamespace=$NS,metricValue=1,defaultValue=0"
aws cloudwatch put-metric-alarm --alarm-name "mhrs-$ENV-5xx-rate" --evaluation-periods 1 \
  --comparison-operator GreaterThanThreshold --threshold 2 --treat-missing-data notBreaching \
  --alarm-actions "$topic_arn" --ok-actions "$topic_arn" --metrics "$(cat <<EOF
[
  {"Id": "e", "MetricStat": {"Metric": {"Namespace": "$NS", "MetricName": "Server5xx"}, "Period": 300, "Stat": "Sum"}, "ReturnData": false},
  {"Id": "r", "MetricStat": {"Metric": {"Namespace": "$NS", "MetricName": "Requests"}, "Period": 300, "Stat": "Sum"}, "ReturnData": false},
  {"Id": "rate", "Expression": "IF(r >= 50, 100 * e / r, 0)", "Label": "5xx rate (%)", "ReturnData": true}
]
EOF
)"
echo "alarm mhrs-$ENV-5xx-rate"

# --- AWS services ---------------------------------------------------------------------------------------
if [[ -n ${INSTANCE_ID:-} ]]; then
  aws cloudwatch put-metric-alarm --alarm-name "mhrs-$ENV-ec2-status" --namespace AWS/EC2 \
    --metric-name StatusCheckFailed_System --statistic Maximum --period 60 --evaluation-periods 2 \
    --comparison-operator GreaterThanOrEqualToThreshold --threshold 1 --dimensions "Name=InstanceId,Value=$INSTANCE_ID" \
    --alarm-actions "$topic_arn" "arn:aws:automate:$REGION:ec2:recover"
  alarm ec2-cpu AWS/EC2 CPUUtilization Average 300 3 GreaterThanThreshold 85 missing "Name=InstanceId,Value=$INSTANCE_ID"
fi
if [[ -n ${DB_INSTANCE:-} ]]; then
  alarm rds-cpu AWS/RDS CPUUtilization Average 300 3 GreaterThanThreshold 80 missing "Name=DBInstanceIdentifier,Value=$DB_INSTANCE"
  alarm rds-storage AWS/RDS FreeStorageSpace Minimum 300 1 LessThanThreshold 10737418240 missing "Name=DBInstanceIdentifier,Value=$DB_INSTANCE"
  alarm rds-connections AWS/RDS DatabaseConnections Maximum 300 2 GreaterThanThreshold 200 missing "Name=DBInstanceIdentifier,Value=$DB_INSTANCE"
fi
alarm ses-bounces AWS/SES Reputation.BounceRate Maximum 3600 1 GreaterThanThreshold 0.04 notBreaching
alarm ses-complaints AWS/SES Reputation.ComplaintRate Maximum 3600 1 GreaterThanThreshold 0.0008 notBreaching

echo "done: alarms notify $topic_arn"
