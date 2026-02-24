# Third-Party
import os
import logging
import subprocess
import shutil
from datetime import datetime
# Local
from tipapp import settings, emails
from thermalimageprocessing.thermal_image_processing import (
    unzip_and_prepare,
    run_thermal_processing,
    ArchiveValidationError,
)

logger = logging.getLogger(__name__)

class ImportsProcessor():

    def __init__(self, source_path, dest_path):
        self.source_path = source_path
        self.history_path = dest_path

    def process_files(self):
        logger.info(f"Processing pending Imports from : {self.source_path}")
        print(f"Starting to process pending imports from: {self.source_path}")

        try:
            # --- Get a list of files to process first for better feedback ---
            # We check for files ending with .7z or .zip, case-insensitively.
            files_to_process = [
                entry for entry in os.scandir(self.source_path) 
                if entry.is_file() and entry.name.lower().endswith(('.7z', '.zip'))
            ]
            
            if not files_to_process:
                print("\nNo new .7z or .zip files found in the import directory. Nothing to do.")
                logger.info("No new files found to process.")
                return

            print(f"\nFound {len(files_to_process)} file(s) to process.")
            print("-" * 50) # A separator for readability

            for entry in files_to_process:
                filename = entry.name

                # log watch
                print(f"\nProcessing file: {filename}")
                logger.info ("File to be processed: " + str(entry.path))   

                # Phase 3: Find and update job record
                from tipapp.models import ThermalProcessingJob
                from django.utils import timezone
                import re
                
                job = None
                
                # Try to find job by file_path first (handles duplicate uploads with suffixed flight_names)
                try:
                    job = ThermalProcessingJob.objects.get(file_path=entry.path)
                    logger.info(f"Job found by file_path: {job.id} (flight_name={job.flight_name})")
                except ThermalProcessingJob.DoesNotExist:
                    # Fallback: try to find by flight_name extracted from filename
                    flight_name = filename
                    # Remove .7z or .zip extension
                    if flight_name.lower().endswith('.7z'):
                        flight_name = flight_name[:-3]
                    elif flight_name.lower().endswith('.zip'):
                        flight_name = flight_name[:-4]
                    # Remove timestamp if present (format: .YYYYMMDD_HHMMSS)
                    flight_name = re.sub(r'\.\d{8}_\d{6}$', '', flight_name)
                    
                    try:
                        job = ThermalProcessingJob.objects.get(flight_name=flight_name)
                        logger.info(f"Job found by flight_name: {job.id}")
                    except ThermalProcessingJob.DoesNotExist:
                        logger.warning(f"Job record not found for file {filename} (tried file_path and flight_name={flight_name}), processing will continue without tracking")
                except Exception as e:
                    logger.error(f"Error searching for job record: {e}", exc_info=True)
                
                # Update job status to PROCESSING if found
                if job:
                    # Skip files whose job is already FAILED — prevents infinite retry loops
                    # (e.g. when a previous validation error left the file in pending_imports).
                    if job.status == 'FAILED':
                        logger.info(
                            f"Skipping {filename}: job {job.id} is already in FAILED status. "
                            "Remove the file from pending_imports to clear it."
                        )
                        print(f"  -> Skipping {filename}: job already FAILED.")
                        continue

                    try:
                        job.status = 'PROCESSING'
                        job.processing_started_at = timezone.now()
                        job.current_step = 'Starting file preparation'
                        job.progress_percentage = 5
                        job.save()
                        logger.info(f"Job {job.id} status updated to PROCESSING")
                    except Exception as e:
                        logger.error(f"Error updating job status: {e}", exc_info=True)

                try:
                    # =========================================================
                    # Call Python functions directly instead of .sh
                    # =========================================================
                    print(f"  -> Starting file preparation (unzip and move)...")
                    logger.info(f"Starting direct Python processing for: {filename}")
                    
                    # Phase 4: Update progress before unzipping
                    if job:
                        try:
                            job.current_step = 'Unzipping file'
                            job.progress_percentage = 10
                            job.save(update_fields=['current_step', 'progress_percentage'])
                        except Exception as e:
                            logger.error(f"Error updating unzip progress: {e}")
                    
                    # 1. Unzip and Prepare (Replaces shell script logic)
                    # entry.path: The full path to the pending .7z file
                    # dest_path: Where to move the original .7z file after extraction
                    # Pass flight_name to handle duplicate uploads with suffix
                    processed_dir_path = unzip_and_prepare(entry.path, target_dirname=job.flight_name if job else None)
                    
                    print(f"  -> File successfully unzipped to: {processed_dir_path}")
                    logger.info(f"Unzipped and prepared at: {processed_dir_path}")
                    
                    # 2. Run Main Thermal Processing
                    # This runs the GDAL/PostGIS/GeoServer pipeline
                    print(f"  -> Starting main thermal processing pipeline...")
                    run_thermal_processing(processed_dir_path, job_id=job.id if job else None)
                    
                    print(f"  -> Thermal processing pipeline completed successfully.")
                    logger.info(f"Successfully finished processing for: {filename}")
                    
                    # Phase 3: Job status has already been updated by run_thermal_processing
                    # No need to update here as it may have been set to FAILED if there were errors
                    if job:
                        try:
                            job.refresh_from_db()
                            logger.info(f"Job {job.id} final status: {job.status}")
                        except Exception as e:
                            logger.error(f"Error refreshing job status: {e}", exc_info=True)
                    
                    print(f"  => FINISHED: Processing {filename} with status: {job.status if job else 'N/A'}")

                # Since we are running python code directly, we catch standard Exceptions
                except Exception as e:
                    print(f"  => ERROR: An error occurred while processing {filename}: {e}")
                    logger.error(f"Error processing file {filename}: {e}", exc_info=True)

                    # --- Validation errors happen BEFORE run_thermal_processing is called, ---
                    # --- so that function never sends its failure email. We send it here.   ---
                    if isinstance(e, ArchiveValidationError):
                        # Move the invalid file to archives so the cron doesn't retry it
                        # endlessly on subsequent runs.
                        try:
                            if not os.path.exists(settings.UPLOADS_HISTORY_PATH):
                                os.makedirs(settings.UPLOADS_HISTORY_PATH, exist_ok=True)
                            dest = os.path.join(settings.UPLOADS_HISTORY_PATH, filename)
                            shutil.move(entry.path, dest)
                            logger.info(f"Invalid archive moved to archives: {dest}")
                        except Exception as move_err:
                            logger.error(f"Could not move invalid archive to archives: {move_err}")

                        # Send failure notification with the validation error detail
                        try:
                            recipient = job.uploaded_by_email if job and job.uploaded_by_email else None
                            flight_label = job.flight_name if job else os.path.splitext(filename)[0]
                            emails.send_failure_notification(
                                flight_name=flight_label,
                                error_message=str(e),
                                recipient_email=recipient,
                            )
                        except Exception as email_err:
                            logger.error(
                                f"Could not send validation-failure notification: {email_err}"
                            )
                    
                    # Phase 3: Check if job status was already set by run_thermal_processing
                    if job:
                        try:
                            # Refresh from DB to get latest values
                            job.refresh_from_db()
                            
                            # Only update if not already set to FAILED by run_thermal_processing
                            if job.status != 'FAILED':
                                job.status = 'FAILED'
                                job.processing_completed_at = timezone.now()
                                job.error_message = str(e)
                                job.current_step = 'Processing failed'
                                # Save only the fields we're updating
                                job.save(update_fields=['status', 'processing_completed_at', 'error_message', 'current_step'])
                                logger.info(f"Job {job.id} status updated to FAILED")
                            else:
                                logger.info(f"Job {job.id} already marked as FAILED by run_thermal_processing")
                        except Exception as update_error:
                            logger.error(f"Error updating job failure status: {update_error}", exc_info=True)

            print("-" * 50)
            print("All pending files have been processed.")

        except Exception as e:
            print(f"\nA critical error occurred: {e}")
            logger.error(f"A critical error occurred in ImportsProcessor: {e}", exc_info=True)
