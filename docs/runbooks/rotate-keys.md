# Runbook — rotate the field-encryption key

P11-T08. ADR-011. Code: `apps/core/crypto.py` (key-id prefixed Fernet, MultiFernet), `apps/core/keyrotation.py`,
command `rotate_field_keys`. Encrypted columns: CV text and extracted claims, evaluation explanations and evidence
snippets, human verifications, claim corrections, privacy-request texts, legal-hold reasons (discovered
automatically: every `EncryptedTextField`).

`FIELD_ENCRYPTION_KEYS` (SSM SecureString) is a comma-separated list `id:key`: the **first** key encrypts, **all**
keys decrypt. Each stored value starts with the id of the key that encrypted it.

## When
- Scheduled: yearly (or as the security policy says).
- Immediately: the key may have been exposed (`credential-compromise.md`), a person with access left.

## Impact
None for users when done in this order. **Never replace the key in one step** — values encrypted with a key that
is no longer listed cannot be read again (CV evidence and explanations would be lost).

## Procedure
1. Generate a new key with the **next id** (ids must be unique; check the current list first):
   ```bash
   docker compose -f /opt/mhrs/docker-compose.prod.yml run --rm --no-deps backend \
     python -c "from apps.core.crypto import generate_key; print(generate_key('k2'))"
   ```
2. Store it **first** in the list, keep the old key(s) after it, e.g. `k2:<new>,k1:<old>`:
   `aws ssm put-parameter --name /mhrs/<env>/FIELD_ENCRYPTION_KEYS --type SecureString --overwrite --value '<list>'`
   and keep an offline copy of the new key with the owner (losing every copy = losing the encrypted data).
3. Deploy (`deploy.sh <current tag>`): new writes now use `k2`; old values remain readable.
4. Re-encrypt existing values (safe while the application runs; a value rewritten by the app meanwhile is
   skipped, never overwritten):
   ```bash
   $DC exec backend python manage.py rotate_field_keys --dry-run   # counts per column and key id
   $DC exec backend python manage.py rotate_field_keys             # re-encrypts in batches of 500
   ```
   Repeat until it prints `done: 0 value(s) still on an old key`.
5. Wait for the oldest **backup** that still contains `k1` values to expire (35 days for the weekly dumps; RDS
   snapshots per the retention setting) — or keep `k1` in an offline vault for restores.
6. Remove the old key from the list (`k2:<new>`), deploy, and run `rotate_field_keys --dry-run` once more: it
   must report 0 and no decryption errors.

## Verification
`rotate_field_keys --dry-run` → 0 on old keys; open an application's evidence view and an evaluation explanation
(they decrypt); `deploy.sh` smoke tests pass.

## If something goes wrong
- `rotate_field_keys` stops with *Unable to decrypt value encrypted with key 'k1'*: the old key was removed too early
  → put it back in the list, deploy, rerun.
- A restore from an older backup needs every key that was primary when it was taken (step 5).

## Follow-up
Record the rotation (date, new key id, who) in the security log; the audit log holds no key material.
