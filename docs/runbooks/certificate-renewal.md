# Runbook — TLS certificate renewal

P11-T08. Script: `infrastructure/deployment/certbot.sh`. Certificates: Let's Encrypt, lineage `mhrs`
(`/etc/letsencrypt/live/mhrs/`, read by nginx). Renewal: host `certbot.timer` twice a day (certificates renew
30 days before expiry), webroot `/var/www/certbot`, deploy hook reloads nginx. Alarm: `mhrs-<env>-cert-expiry`
(< 14 days left, from `host-checks.sh`).

## Symptoms
The expiry alarm; browsers warn about the certificate; `CertDaysLeft` falling below 30 (renewal should have
happened by then).

## Impact
After expiry every visitor gets a browser error (HSTS preload means they cannot click through) — a full outage.
14 days of warning leaves plenty of time.

## Immediate actions
```bash
sudo /opt/mhrs/infrastructure/deployment/certbot.sh status        # expiry date + timer
sudo certbot renew --dry-run                                     # does a renewal work right now?
sudo journalctl -u certbot.service --since -3d | tail -50        # why did the timer's renewals fail?
```

## Diagnosis
| Error | Cause | Fix |
|---|---|---|
| `Connection refused` / timeout on port 80 | nginx down, ufw/security group blocks 80 | `$DC ps nginx`; port 80 must stay open (ACME + redirect) |
| `404` for `/.well-known/acme-challenge/...` | webroot not mounted / wrong path | `docker-compose.prod.yml` mounts `/var/www/certbot` read-only into nginx; the template serves it on port 80 |
| `DNS problem: NXDOMAIN` / wrong IP | DNS changed, Elastic IP moved | fix the A record (AWS_SETUP §8) |
| CAA forbids issuance | CAA record changed | `CAA 0 issue "letsencrypt.org"` |
| Rate limited | too many failed attempts | wait (1 h for failed validations); use `--staging` to test |
| Renewed but nginx still serves the old one | deploy hook missing | `sudo ls /etc/letsencrypt/renewal-hooks/deploy/`; reload: `$DC exec nginx nginx -s reload` |

## Resolution
`sudo certbot renew --cert-name mhrs` (then the hook reloads nginx). If the lineage is broken beyond repair:
`sudo certbot.sh issue <domain> <email>` (stops nginx for ~30 s for a standalone issuance).

## Verification
`echo | openssl s_client -connect <domain>:443 -servername <domain> 2>/dev/null | openssl x509 -noout -enddate`
shows the new date; SSL Labs grade still A+; `CertDaysLeft` jumps to ~89 at the next host check (15 min).

## Follow-up
If the timer had silently failed: why did the 14-day alarm not fire earlier (host-checks timer running?
`systemctl list-timers mhrs-host-checks.timer`).
