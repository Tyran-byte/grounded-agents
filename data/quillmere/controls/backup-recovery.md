# Backup and recovery

## backups — Backups
Production databases are backed up every 6 hours. Backups are encrypted and stored in a
second region, separate from the primary hosting region. Backups are retained for 35 days.

## restore-tests — Restore tests
A full restore from backup is tested every quarter, and the result is recorded in the
operations log.

## objectives — Recovery objectives
The recovery point objective (RPO) is 6 hours and the recovery time objective (RTO) is 12
hours for the analytics service. These objectives are internal targets, not contractual
commitments.
