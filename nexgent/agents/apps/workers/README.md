# Background workers

`weekly_report.py` is the independently scalable, durable execution boundary
for high-volume weekly-report exports. PostgreSQL leases coordinate a single
paged producer, bounded asynchronous consumers, and a recoverable finalizer.
Workers can be replicated on hosts that share the job database and private
artifact volume.

The worker is operator-only. It does not expose an HTTP port, schedule jobs, or
send Slack messages. See the weekly-report implementation specification for
submission, status, cancellation, export, cleanup, and capacity commands.
