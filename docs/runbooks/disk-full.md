# Runbook — disk filling up

P11-T08. Alarms: `mhrs-<env>-disk-root`, `-disk-docker` (> 80 %, EC-OPS-08), from the CloudWatch agent.
Documents live in S3 and the database in RDS, so the host disk only holds images, container logs, Redis/ClamAV
volumes, host logs and temporary files.

## Symptoms
The disk alarm; deploys fail (`no space left on device` pulling images); Redis cannot write its AOF; uploads or
OCR fail with I/O errors.

## Impact
At 100 %: Redis stops accepting writes (tasks cannot be queued), containers may fail to start. The API keeps
serving reads; submissions still commit to RDS (the outbox lives in the database), so nothing is lost — side
effects wait.

## Immediate actions (safe, in order)
```bash
df -h / /var/lib/docker
sudo docker system df                                   # images / containers / volumes / build cache
sudo docker image prune -af --filter "until=168h"       # images not used by a container, older than 7 days
sudo docker builder prune -af                           # build cache (never needed on a server)
sudo journalctl --vacuum-size=200M
sudo du -xh /var/log /var/lib/docker/containers 2>/dev/null | sort -rh | head -15
```
**Never** run `docker volume prune` or delete `redis-data` / `clamav-data`: the Redis volume holds queued tasks
(not lost data, but delayed work), the ClamAV volume its signatures (re-download takes minutes).

## Diagnosis
| Big item | Cause | Fix |
|---|---|---|
| `/var/lib/docker/containers/*/*-json.log` | log rotation not applied (container created before `daemon.json`) | recreate the container (`$DC up -d --force-recreate --no-deps <svc>`); compose sets 5 × 20 MB per container |
| many old images | deploys without pruning | `deploy.sh` prunes images older than 7 days after each release; run the prune above |
| `/var/log/mhrs/nginx/access.json` | logrotate not running | `sudo logrotate -f /etc/logrotate.d/mhrs` |
| `/tmp` in worker containers | OCR temp files of crashed tasks | restart the worker (`$DC up -d --force-recreate --no-deps worker-documents`) |
| Redis AOF large | huge backlog | `processing-backlog.md`; `$DC exec redis redis-cli BGREWRITEAOF` |
| backups in `/tmp` | a `backup.sh --local` run left files | delete them after confirming they are in S3 |

## Resolution (if cleanup is not enough)
Grow the EBS volume online: EC2 → Volumes → *Modify* (gp3, larger size) → on the host
`sudo growpart /dev/nvme0n1 1 && sudo resize2fs /dev/nvme0n1p1` (check device names with `lsblk`).

## Verification
`df -h` below 70 %; the alarm returns to OK; `$DC ps` all healthy; a test upload is processed.

## Follow-up
If growth is structural (more organisations), size the volume for 6 months of headroom and note it in the
capacity section of docs/10.
