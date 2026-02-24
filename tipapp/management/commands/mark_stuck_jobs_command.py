"""
Management command to detect and mark stuck PROCESSING jobs as FAILED.

A job is considered stuck if it has been in PROCESSING status for longer
than STUCK_JOB_TIMEOUT_HOURS without any update to its record. This
typically happens when the server crashes mid-processing.

The timeout can be configured via the STUCK_JOB_TIMEOUT_HOURS environment
variable (default: 2 hours).

Intended to be run from cron, e.g. every 10 minutes.
"""

import logging
from datetime import timedelta

import decouple
from django.core.management import base
from django.utils import timezone

logger = logging.getLogger(__name__)

# A job in PROCESSING state with no update for this long is assumed to be stuck.
# Override via environment variable STUCK_JOB_TIMEOUT_HOURS (e.g. in .env or docker-compose).
STUCK_JOB_TIMEOUT_HOURS = decouple.config('STUCK_JOB_TIMEOUT_HOURS', default=2, cast=float)


class Command(base.BaseCommand):
    help = "Mark PROCESSING jobs that have not been updated for too long as FAILED."

    def add_arguments(self, parser):
        parser.add_argument(
            '--timeout-hours',
            type=float,
            default=STUCK_JOB_TIMEOUT_HOURS,
            help=(
                f'Hours without an update before a PROCESSING job is considered stuck '
                f'(default: {STUCK_JOB_TIMEOUT_HOURS})'
            ),
        )

    def handle(self, *args, **kwargs):
        from tipapp.models import ThermalProcessingJob
        from tipapp import emails

        timeout_hours = kwargs['timeout_hours']
        cutoff = timezone.now() - timedelta(hours=timeout_hours)

        stuck_jobs = ThermalProcessingJob.objects.filter(
            status='PROCESSING',
            updated_at__lt=cutoff,
        )

        count = stuck_jobs.count()
        if count == 0:
            self.stdout.write("No stuck jobs found.")
            logger.info("mark_stuck_jobs: no stuck jobs found.")
            return

        self.stdout.write(f"Found {count} stuck job(s). Marking as FAILED...")
        logger.warning(f"mark_stuck_jobs: found {count} stuck job(s) (timeout={timeout_hours}h).")

        for job in stuck_jobs:
            error_msg = (
                f"Job was found stuck in PROCESSING status. "
                f"Last updated: {job.updated_at.strftime('%Y-%m-%d %H:%M:%S UTC')}. "
                f"The server likely crashed or was restarted during processing."
            )

            job.status = 'FAILED'
            job.processing_completed_at = timezone.now()
            job.error_message = error_msg
            job.current_step = 'Processing interrupted (server restart or crash)'
            job.save(update_fields=[
                'status', 'processing_completed_at', 'error_message', 'current_step'
            ])

            logger.warning(
                f"mark_stuck_jobs: job {job.id} ({job.flight_name}) "
                f"marked FAILED (stuck since {job.updated_at})."
            )
            self.stdout.write(f"  -> Job {job.id} ({job.flight_name}) marked as FAILED.")

            # Send failure notification so the uploader is informed.
            try:
                recipient = job.uploaded_by_email or None
                emails.send_failure_notification(
                    flight_name=job.flight_name,
                    error_message=error_msg,
                    recipient_email=recipient,
                )
            except Exception as e:
                logger.error(
                    f"mark_stuck_jobs: could not send failure notification for job {job.id}: {e}"
                )

        self.stdout.write(f"Done. {count} job(s) marked as FAILED.")
