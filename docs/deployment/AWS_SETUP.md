# AWS setup — MUDHOTECH HR RECRUITING SYSTEM (P11-T04)

Step-by-step setup of the AWS account for **staging** and **production** (docs/10 §3). Every step that needs AWS
credentials, a domain or a payment method is an **owner step** (CLAUDE.md STOP condition): the owner (or an
administrator the owner appoints) runs it in their own account. Nothing here contains secrets.

Defaults (change only with an ADR in docs/11): region **`af-south-1` (Cape Town)** (D-07), domain
**`hr.mudhotech.co.zw`** (placeholder, D-09), email **SES** (D-10). Commands use the AWS CLI v2 with a profile that has
administrator rights for the setup only; day-to-day operation uses the instance role below.

```bash
export AWS_PROFILE=mhrs-admin AWS_REGION=af-south-1
export ENV=production            # or staging
export DOMAIN=hr.mudhotech.co.zw # staging: staging.hr.mudhotech.co.zw
export ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
```

| Item | Staging | Production |
|---|---|---|
| EC2 | `t3.large` (2 vCPU / 8 GB), 60 GB gp3 | `t3.xlarge` (4 vCPU / 16 GB), 100 GB gp3 |
| RDS PostgreSQL 16 | `db.t4g.small`, single-AZ, 7-day backups | `db.t4g.medium`, Multi-AZ optional (owner), 14–35-day backups + PITR |
| S3 | `mhrs-staging-*` | `mhrs-prod-*` |
| Data | synthetic seed only | real candidates (CDPA, D-08 legal sign-off first) |

Contents: [0 Account](#0-account-baseline) · [1 Network](#1-network-vpc-subnets-security-groups) ·
[2 IAM](#2-iam-instance-role) · [3 RDS](#3-rds-postgresql-16-with-pgvector) · [4 S3](#4-s3-buckets) ·
[5 SES](#5-ses-domain-dkim-spf-dmarc-bounces) · [6 SSM](#6-ssm-parameter-store) · [7 EC2](#7-ec2-instance) ·
[8 DNS/TLS](#8-dns-and-tls) · [9 Sentry](#9-sentry) · [10 Budgets/alarms](#10-budgets-and-alarms) ·
[11 Checklist](#11-verification-checklist)

---

## 0. Account baseline
1. **Enable the region.** `af-south-1` is an opt-in region: *Account → AWS Regions → Africa (Cape Town) → Enable*.
2. Root user: hardware/virtual MFA, no access keys, contact + security contacts set (*Account → Alternate contacts*).
3. Create an administrators group with MFA enforced; daily work never uses root.
4. Turn on **CloudTrail** (management events, all regions, S3 bucket with SSE + 365-day lifecycle) and
   **IAM Access Analyzer**. Optional but recommended: GuardDuty (low cost at this size).
5. Set the default EBS encryption: `aws ec2 enable-ebs-encryption-by-default`.

## 1. Network (VPC, subnets, security groups)
Use a dedicated VPC (not the default one): `10.40.0.0/16`, two AZs.

| Subnet | CIDR | Use |
|---|---|---|
| public-a / public-b | `10.40.0.0/24`, `10.40.1.0/24` | EC2 host (public IP / Elastic IP) |
| private-a / private-b | `10.40.10.0/24`, `10.40.11.0/24` | RDS (DB subnet group, no internet route) |

No NAT gateway is needed (only the EC2 host reaches the internet). Add **gateway VPC endpoints** for S3 (free) so
document traffic stays on the AWS network.

| Security group | Inbound | Outbound |
|---|---|---|
| `mhrs-<env>-web` (EC2) | 80, 443 from `0.0.0.0/0` and `::/0`; 22 **only** from the operator IP (or none: use SSM Session Manager) | all |
| `mhrs-<env>-db` (RDS) | 5432 **only** from `mhrs-<env>-web` | none |

## 2. IAM instance role
Role `mhrs-<env>-ec2` (trusted entity: EC2) with the AWS managed policies **`AmazonSSMManagedInstanceCore`** (Session
Manager, Run Command) and **`CloudWatchAgentServerPolicy`**, plus this inline policy (replace `<env>`, `<account>`):

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "AppBuckets",
      "Effect": "Allow",
      "Action": ["s3:GetObject", "s3:PutObject", "s3:DeleteObject", "s3:GetObjectTagging", "s3:PutObjectTagging"],
      "Resource": [
        "arn:aws:s3:::mhrs-<env>-uploads-quarantine/*", "arn:aws:s3:::mhrs-<env>-documents/*",
        "arn:aws:s3:::mhrs-<env>-exports/*", "arn:aws:s3:::mhrs-<env>-public/*"
      ]
    },
    {
      "Sid": "AppBucketList",
      "Effect": "Allow",
      "Action": ["s3:ListBucket", "s3:GetBucketLocation"],
      "Resource": [
        "arn:aws:s3:::mhrs-<env>-uploads-quarantine", "arn:aws:s3:::mhrs-<env>-documents",
        "arn:aws:s3:::mhrs-<env>-exports", "arn:aws:s3:::mhrs-<env>-public"
      ]
    },
    {
      "Sid": "Backups",
      "Effect": "Allow",
      "Action": ["s3:PutObject", "s3:GetObject", "s3:ListBucket"],
      "Resource": ["arn:aws:s3:::mhrs-<env>-backups", "arn:aws:s3:::mhrs-<env>-backups/*"]
    },
    {
      "Sid": "ReadOwnParameters",
      "Effect": "Allow",
      "Action": ["ssm:GetParametersByPath", "ssm:GetParameters", "ssm:GetParameter"],
      "Resource": "arn:aws:ssm:af-south-1:<account>:parameter/mhrs/<env>/*"
    },
    {
      "Sid": "DecryptParameters",
      "Effect": "Allow",
      "Action": "kms:Decrypt",
      "Resource": "arn:aws:kms:af-south-1:<account>:alias/aws/ssm"
    },
    {
      "Sid": "SendEmail",
      "Effect": "Allow",
      "Action": ["ses:SendEmail", "ses:SendRawEmail"],
      "Resource": "*",
      "Condition": { "StringLike": { "ses:FromAddress": "*@<domain>" } }
    }
  ]
}
```

The application never holds long-lived AWS keys: boto3 uses the instance role when `S3_ACCESS_KEY` is empty. The
role cannot delete backups (no `s3:DeleteObject` on the backups bucket) — lifecycle rules expire them.
Pulling images from GHCR needs no AWS permission (a read-only GHCR token lives in SSM, §6).

## 3. RDS PostgreSQL 16 with pgvector
1. DB subnet group `mhrs-<env>-db` with the two private subnets.
2. Parameter group `mhrs-<env>-pg16` (family `postgres16`): `rds.force_ssl=1`, `log_min_duration_statement=1000`,
   `idle_in_transaction_session_timeout=60000`, `statement_timeout=0` (the app sets its own),
   `shared_preload_libraries=pg_stat_statements`.
3. Create the instance: engine PostgreSQL **16.x** (latest minor), class per the table above, gp3 50 GB with storage
   autoscaling to 200 GB, **encryption on** (aws/rds KMS key), security group `mhrs-<env>-db`, no public access,
   automated backups (staging 7 days, production 14–35 days), backup window 01:00–02:00 UTC, maintenance window
   Sun 02:30–03:30 UTC, deletion protection **on** (production), Performance Insights (7 days, free tier),
   Enhanced Monitoring off (CloudWatch metrics are enough for the pilot).
4. Master user `mhrs_admin` with a long random password kept by the owner (password manager / RDS-managed secret).
   It is used only for the one-time SQL below and break-glass maintenance — never by the application.
5. From the EC2 host (`psql` is installed by the bootstrap), create the database, extensions and the **application
   role without `BYPASSRLS`** (docs/10 §3.1, ADR-012):

```sql
-- connect as mhrs_admin to the default "postgres" database
CREATE DATABASE mhrs;
\c mhrs
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE EXTENSION IF NOT EXISTS unaccent;
CREATE EXTENSION IF NOT EXISTS pg_stat_statements;
-- the app connects as mhrs_app; row-level security applies to it (never grant rds_superuser / BYPASSRLS)
CREATE ROLE mhrs_app LOGIN PASSWORD '<generated>' NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE;
GRANT CONNECT, TEMPORARY ON DATABASE mhrs TO mhrs_app;
GRANT USAGE, CREATE ON SCHEMA public TO mhrs_app;
ALTER DATABASE mhrs SET timezone TO 'UTC';
```

Migrations run as `mhrs_app` (it owns the objects it creates, so `FORCE ROW LEVEL SECURITY` keeps applying to it).
Verify after the first deploy: `SELECT rolbypassrls, rolsuper FROM pg_roles WHERE rolname = 'mhrs_app';` → `f, f`.
Connection budget (docs/10 §3.2): `3 web workers × 10 + 7 Celery processes + 20` ≈ 57 ≪ `max_connections` (~400).

## 4. S3 buckets
Create five buckets in `af-south-1`: `mhrs-<env>-uploads-quarantine`, `mhrs-<env>-documents`, `mhrs-<env>-exports`,
`mhrs-<env>-public`, `mhrs-<env>-backups`. For **every** bucket:

- **Block Public Access: all four settings on** (the job board serves logos through the app/presigned URLs; if a CDN
  is added later, use CloudFront with Origin Access Control, never a public bucket).
- Object Ownership: *Bucket owner enforced* (ACLs disabled).
- Default encryption: SSE-S3 (AES-256), bucket key on.
- A bucket policy that denies non-TLS requests:

```json
{
  "Version": "2012-10-17",
  "Statement": [{
    "Sid": "DenyInsecureTransport", "Effect": "Deny", "Principal": "*", "Action": "s3:*",
    "Resource": ["arn:aws:s3:::<bucket>", "arn:aws:s3:::<bucket>/*"],
    "Condition": { "Bool": { "aws:SecureTransport": "false" } }
  }]
}
```

| Bucket | Versioning | Lifecycle |
|---|---|---|
| uploads-quarantine | off | expire objects after **1 day**; abort incomplete multipart uploads after 1 day |
| documents | **on** | noncurrent versions expire after 30 days (erasure, docs/06 retention); abort incomplete uploads after 1 day |
| exports | off | expire after **1 day** (data-export bundles, P09) |
| public | on | noncurrent versions expire after 30 days |
| backups | **on** | current versions expire after **35 days**, noncurrent after 7 days; Object Lock (governance, 35 days) optional |

CORS on `uploads-quarantine` (browsers upload CVs there with presigned PUTs):

```json
[{ "AllowedOrigins": ["https://<domain>"], "AllowedMethods": ["PUT"], "AllowedHeaders": ["*"],
   "ExposeHeaders": ["ETag"], "MaxAgeSeconds": 3000 }]
```

## 5. SES (domain, DKIM, SPF, DMARC, bounces)
1. *SES → Identities → Create identity → Domain* `<domain>` with **Easy DKIM (RSA 2048)** and a custom MAIL FROM
   domain `mail.<domain>`. Publish the records SES shows:

| Record | Name | Value |
|---|---|---|
| CNAME × 3 | `<token>._domainkey.<domain>` | `<token>.dkim.amazonses.com` |
| MX | `mail.<domain>` | `10 feedback-smtp.af-south-1.amazonses.com` |
| TXT (SPF) | `mail.<domain>` | `"v=spf1 include:amazonses.com -all"` |
| TXT (DMARC) | `_dmarc.<domain>` | `"v=DMARC1; p=quarantine; rua=mailto:dmarc@<domain>; adkim=s; aspf=r"` (start with `p=none` for two weeks, then quarantine) |

2. Configuration set `mhrs-<env>` (reputation metrics on); set `AWS_SES_CONFIGURATION_SET`.
3. **Bounces and complaints:** SNS topic `mhrs-<env>-ses-feedback`; in the identity's *Notifications*, send Bounce and
   Complaint to it (include original headers: off). Subscribe the HTTPS endpoint
   `https://<domain>/api/v1/webhooks/ses/` — the app verifies the SNS signature and confirms the subscription itself
   (P05-T04). Put the topic ARN in `SES_SNS_TOPIC_ARNS`; until then the webhook refuses every message.
4. **SMTP credentials** (*SES → SMTP settings → Create SMTP credentials*) → `EMAIL_URL`
   `smtp+tls://<user>:<password>@email-smtp.af-south-1.amazonaws.com:587` (SSM SecureString). URL-encode the password.
5. **Production access** (leave the sandbox): request it with the use case "transactional recruiting notifications
   (application receipts, status updates, account security); no marketing; bounces/complaints suppressed
   automatically". Staging may stay in the sandbox with verified test recipients.
6. No-reply mailbox / receipt rule: docs/10 §6 (ADR-024).

## 6. SSM Parameter Store
All runtime configuration lives under `/mhrs/<env>/` (Standard tier, free). `deploy.sh` renders it into
`/opt/mhrs/.env` (mode 0600) on every deploy; parameter name = environment variable name. Secrets are
**SecureString** (aws/ssm key).

| Parameter | Type | Value / how to generate |
|---|---|---|
| `DJANGO_SETTINGS_MODULE` | String | `config.settings.prod` (staging: `config.settings.staging`) |
| `SECRET_KEY` | SecureString | `python -c "import secrets; print(secrets.token_urlsafe(64))"` |
| `FIELD_ENCRYPTION_KEYS` | SecureString | `k1:` + `Fernet.generate_key()` (ADR-011; **back this up offline** — losing it loses encrypted data) |
| `ALLOWED_HOSTS` | String | `<domain>,backend` |
| `CSRF_TRUSTED_ORIGINS` | String | `https://<domain>` |
| `FRONTEND_URL`, `NEXT_PUBLIC_SITE_URL` | String | `https://<domain>` |
| `DATABASE_URL` | SecureString | `postgres://mhrs_app:<pw>@<rds-endpoint>:5432/mhrs?sslmode=require` |
| `DB_POOL`, `DB_POOL_MAX` | String | `true`, `10` |
| `REDIS_URL`, `CELERY_BROKER_URL` | String | `redis://redis:6379/0` |
| `CACHE_URL` / `CELERY_RESULT_BACKEND` | String | `redis://redis:6379/1` / `redis://redis:6379/3` |
| `S3_REGION` | String | `af-south-1` (leave `S3_ENDPOINT_URL`, `S3_ACCESS_KEY`, `S3_SECRET_KEY` unset: instance role) |
| `S3_BUCKET_QUARANTINE` … `S3_BUCKET_PUBLIC` | String | the bucket names from §4 |
| `EMAIL_URL` | SecureString | SES SMTP URL (§5) |
| `DEFAULT_FROM_EMAIL`, `SUPPORT_EMAIL` | String | `MUDHOTECH HR RECRUITING SYSTEM <no-reply@<domain>>`, `support@<domain>` |
| `SES_SNS_TOPIC_ARNS`, `AWS_SES_REGION`, `AWS_SES_CONFIGURATION_SET` | String | §5 |
| `CLAMAV_HOST`, `CLAMAV_PORT`, `DOCUMENT_SCANNER` | String | `clamav`, `3310`, `clamd` |
| `SENTRY_DSN`, `NEXT_PUBLIC_SENTRY_DSN` | SecureString | §9 |
| `SENTRY_ENVIRONMENT` | String | `staging` / `production` |
| `MHRS_DOMAIN`, `MHRS_ENVIRONMENT` | String | `<domain>`, `staging` / `production` (nginx) |
| `LLM_PROVIDER` | String | `none` (D-06; an LLM needs an owner decision + DPA) |
| `TENANT_STRICT_MODE` | String | `true` |
| `GHCR_READ_TOKEN` | SecureString | fine-grained GitHub token with `read:packages` only (image pulls) |
| `DEMO_PASSWORD` | SecureString | **staging only** (synthetic seed); never set in production |

```bash
aws ssm put-parameter --name /mhrs/$ENV/SECRET_KEY --type SecureString --value "$(python3 -c 'import secrets;print(secrets.token_urlsafe(64))')"
aws ssm get-parameters-by-path --path /mhrs/$ENV/ --query 'Parameters[].Name' --output text   # review
```

## 7. EC2 instance
1. AMI: **Ubuntu Server 24.04 LTS** (Canonical, `amd64`), type per the table, root volume gp3 encrypted,
   subnet public-a, security group `mhrs-<env>-web`, instance profile `mhrs-<env>-ec2`,
   **IMDSv2 required** (hop limit 2 for containers), termination protection on (production).
2. Allocate an **Elastic IP** and associate it.
3. Connect with Session Manager (`aws ssm start-session --target <instance-id>`), clone the repository to
   `/opt/mhrs` and run the bootstrap (docs/10 §3.4):

```bash
sudo git clone https://github.com/king-Mudho/MUDHOTECH-HR-RECRUITING-SYSTEM.git /opt/mhrs
sudo MHRS_ENVIRONMENT=$ENV OPS_ALLOW_IPS="<operator-ip>/32" DEPLOY_SSH_KEY="<ci-deploy-public-key>" \
     bash /opt/mhrs/infrastructure/deployment/ec2-bootstrap.sh
sudo chown -R mhrs:mhrs /opt/mhrs
```

## 8. DNS and TLS
1. At the DNS provider for the domain: `A <domain> → <Elastic IP>` (and `AAAA` if IPv6 is enabled), TTL 300.
   Add a **CAA** record: `<domain> CAA 0 issue "letsencrypt.org"`.
2. When the record resolves: `sudo /opt/mhrs/infrastructure/deployment/certbot.sh issue <domain> <contact-email>`.
3. After the first deploy, check <https://www.ssllabs.com/ssltest/> → target **A+** (go-live gate, P11-T10).
   Submit to the HSTS preload list only after a few stable weeks (preload is hard to undo).

## 9. Sentry
Two projects per environment in the Sentry organisation: `mhrs-backend` (Django/Celery) and `mhrs-frontend`
(Next.js). Data scrubbing: *Settings → Security & Privacy*: **Data Scrubber on**, *Use Default Scrubbers on*,
*Prevent Storing of IP Addresses on*, extra sensitive fields `email, phone, cv, password, token`. The app already
sends `send_default_pii=False` and tags `release` = the image tag (`MHRS_VERSION`) and `environment`.
Alerts: new issue in production → owner email; error rate > 1 % over 5 minutes → owner email.

## 10. Budgets and alarms
- **AWS Budgets:** monthly cost budget for the account (e.g. USD 250 for staging + production) with alerts at 50 %,
  80 % and 100 % forecasted → owner email. Note: `af-south-1` prices are ~15–25 % above `us-east-1`.
- **SNS topic** `mhrs-<env>-alerts` (email subscription: on-call owner) — target of every alarm below.
- **CloudWatch alarms** (P11-T07 adds the application metrics):

| Alarm | Metric | Threshold |
|---|---|---|
| EC2 status check failed | `AWS/EC2 StatusCheckFailed` | ≥ 1 for 2 × 1 min → also *recover* action |
| Host CPU | `AWS/EC2 CPUUtilization` | > 85 % for 15 min |
| Host memory | `MHRS/<env> mem_used_percent` | > 90 % for 10 min |
| Disk | `MHRS/<env> disk used_percent` (`/`, `/var/lib/docker`) | > 80 % (EC-OPS-08) |
| RDS CPU / storage / connections | `AWS/RDS CPUUtilization`, `FreeStorageSpace`, `DatabaseConnections` | > 80 %, < 10 GB, > 200 |
| RDS replica/backup | RDS event subscription (backup failure, failover, low storage) | any |
| SES reputation | `AWS/SES Reputation.BounceRate`, `Reputation.ComplaintRate` | > 4 %, > 0.08 % |

## 11. Verification checklist
- [ ] Region enabled; CloudTrail on; root MFA; EBS encryption by default
- [ ] VPC with private DB subnets; RDS not publicly accessible; SG 5432 only from the web SG
- [ ] Instance role has no wildcard S3 resource and no long-lived keys exist for the app
- [ ] `mhrs_app` is `NOSUPERUSER NOBYPASSRLS`; `vector`, `pg_trgm`, `unaccent` installed; `rds.force_ssl=1`
- [ ] All buckets: Block Public Access ×4, SSE, TLS-only policy; lifecycle rules as in §4; versioning on documents/backups
- [ ] SES identity verified with DKIM; SPF + DMARC published; feedback SNS topic subscribed (confirmed in app logs); production access granted
- [ ] All SSM parameters present under `/mhrs/<env>/`; `FIELD_ENCRYPTION_KEYS` backed up offline by the owner
- [ ] Elastic IP + DNS; CAA; certificate issued; SSL Labs A+
- [ ] Sentry projects with scrubbing; first release visible after deploy
- [ ] Budget alerts and the alarms in §10 exist and point at the alerts topic
