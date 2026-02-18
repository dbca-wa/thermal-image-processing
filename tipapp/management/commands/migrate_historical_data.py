"""
Management command to migrate historical thermal processing data.

This command scans the thermal_data_processing directory for already-processed
flights and creates ThermalProcessingJob records for them, allowing historical
data to be tracked in the job tracking system.
"""

import os
import re
import json
import logging
from pathlib import Path
from datetime import datetime
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from django.contrib.auth import get_user_model

from tipapp.models import ThermalProcessingJob
from tipapp import settings

logger = logging.getLogger(__name__)
User = get_user_model()


class Command(BaseCommand):
    """Migrate historical thermal processing data to job tracking system."""
    
    help = "Creates ThermalProcessingJob records for already-processed flights"
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be migrated without actually creating records',
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Recreate records even if they already exist',
        )
    
    def handle(self, *args, **options):
        """Execute the migration."""
        dry_run = options['dry_run']
        force = options['force']
        
        self.stdout.write(self.style.SUCCESS('=' * 70))
        self.stdout.write(self.style.SUCCESS('Historical Data Migration - Phase 7'))
        self.stdout.write(self.style.SUCCESS('=' * 70))
        
        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN MODE - No records will be created'))
        
        # Paths
        processed_dir = Path(settings.DATA_STORAGE)
        uploads_dir = Path(settings.UPLOADS_HISTORY_PATH)
        logs_dir = Path(settings.BASE_DIR) / 'logs'
        
        if not processed_dir.exists():
            raise CommandError(f"Processed directory not found: {processed_dir}")
        
        # Find all processed flights
        flight_dirs = [d for d in processed_dir.iterdir() if d.is_dir()]
        self.stdout.write(f"\nFound {len(flight_dirs)} processed flight directories")
        
        migrated_count = 0
        skipped_count = 0
        failed_count = 0
        
        for flight_dir in sorted(flight_dirs):
            flight_name = flight_dir.name
            
            # Check if record already exists
            existing_job = ThermalProcessingJob.objects.filter(
                flight_name=flight_name
            ).first()
            
            if existing_job and not force:
                self.stdout.write(
                    self.style.WARNING(f"  ⏭  {flight_name} - Already exists (ID: {existing_job.id})")
                )
                skipped_count += 1
                continue
            
            try:
                # Gather data from various sources
                data = self._gather_flight_data(
                    flight_name, 
                    flight_dir, 
                    uploads_dir, 
                    logs_dir
                )
                
                if dry_run:
                    self._display_dry_run_info(flight_name, data)
                    migrated_count += 1
                else:
                    # Create or update the job record
                    if existing_job and force:
                        self._update_job(existing_job, data)
                        self.stdout.write(
                            self.style.SUCCESS(f"  ✓  {flight_name} - Updated (ID: {existing_job.id})")
                        )
                    else:
                        job = self._create_job(data)
                        self.stdout.write(
                            self.style.SUCCESS(f"  ✓  {flight_name} - Created (ID: {job.id})")
                        )
                    migrated_count += 1
                    
            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(f"  ✗  {flight_name} - Failed: {str(e)}")
                )
                logger.exception(f"Failed to migrate {flight_name}")
                failed_count += 1
        
        # Summary
        self.stdout.write("\n" + "=" * 70)
        self.stdout.write(self.style.SUCCESS("Migration Summary:"))
        self.stdout.write(f"  Total flights found: {len(flight_dirs)}")
        self.stdout.write(f"  Migrated: {migrated_count}")
        self.stdout.write(f"  Skipped (already exist): {skipped_count}")
        self.stdout.write(f"  Failed: {failed_count}")
        self.stdout.write("=" * 70)
    
    def _gather_flight_data(self, flight_name, flight_dir, uploads_dir, logs_dir):
        """Gather all available data for a flight."""
        data = {
            'flight_name': flight_name,
            'original_filename': None,
            'status': 'COMPLETED',
            'progress_percentage': 100,
            'current_step': 'Processing completed',
            'file_size': 0,
            'file_path': str(flight_dir),
            'uploaded_by': None,
            'uploaded_by_email': None,
            'created_at': None,
            'processing_started_at': None,
            'processing_completed_at': None,
            'output_geopackage_path': '',
            'error_message': '',
            'log_file_path': '',
            'total_images_processed': None,
            'hotspots_detected': None,
            'districts_covered': [],
        }
        
        # 1. Try to find and parse metadata file
        meta_data = self._find_metadata(flight_name, uploads_dir)
        if meta_data:
            data['original_filename'] = meta_data.get('original_filename', flight_name)
            data['uploaded_by_email'] = meta_data.get('uploaded_by')
            data['created_at'] = meta_data.get('uploaded_at')
            
            # Try to find user by email
            if data['uploaded_by_email']:
                try:
                    user = User.objects.get(email=data['uploaded_by_email'])
                    data['uploaded_by'] = user
                except User.DoesNotExist:
                    pass
        
        if not data['original_filename']:
            data['original_filename'] = f"{flight_name}.7z"
        
        if not data['uploaded_by_email']:
            data['uploaded_by_email'] = 'unknown@system.migration'
        
        # 2. Find archived file for file size
        archive_path = self._find_archive(flight_name, uploads_dir)
        if archive_path and archive_path.exists():
            data['file_size'] = archive_path.stat().st_size
            data['file_path'] = str(archive_path)
        
        # 3. Find and parse log file
        log_data = self._find_and_parse_log(flight_name, logs_dir)
        if log_data:
            data.update(log_data)
        
        # 4. Find output GeoPackage
        gpkg_path = flight_dir / 'Processed' / 'output.gpkg'
        if gpkg_path.exists():
            data['output_geopackage_path'] = str(gpkg_path)
        
        # 5. Find log file path
        log_path = logs_dir / f"{flight_name}.txt"
        if log_path.exists():
            data['log_file_path'] = str(log_path)
        
        # 6. Set timestamps if not found in metadata
        if not data['created_at']:
            # Use directory creation time as fallback
            data['created_at'] = datetime.fromtimestamp(
                flight_dir.stat().st_ctime, 
                tz=timezone.get_current_timezone()
            )
        
        return data
    
    def _get_base_flight_name(self, flight_name):
        """Strip trailing _N suffix from flight name (e.g. FireFlight_..._7 -> FireFlight_...) """
        base_match = re.match(r'^(FireFlight_\d{8}_\d{6}(?:\s\d+)?)(_\d+)?$', flight_name)
        if base_match and base_match.group(2):
            return base_match.group(1)
        return None

    def _find_metadata(self, flight_name, uploads_dir):
        """Find and parse metadata JSON file."""
        # Try exact flight name first, then base name (without _N suffix)
        names_to_try = [flight_name]
        base = self._get_base_flight_name(flight_name)
        if base:
            names_to_try.append(base)

        for name in names_to_try:
            pattern = f"{name}*.meta.json"
            matches = list(uploads_dir.glob(pattern))
            if matches:
                meta_file = matches[0]
                try:
                    with open(meta_file, 'r') as f:
                        return json.load(f)
                except Exception as e:
                    logger.warning(f"Failed to parse metadata {meta_file}: {e}")

        return None

    def _find_archive(self, flight_name, uploads_dir):
        """Find the archived .7z file."""
        # Try exact flight name first, then base name (without _N suffix)
        names_to_try = [flight_name]
        base = self._get_base_flight_name(flight_name)
        if base:
            names_to_try.append(base)

        for name in names_to_try:
            pattern = f"{name}*.7z"
            matches = list(uploads_dir.glob(pattern))
            if matches:
                return matches[0]

        return None
    
    def _find_and_parse_log(self, flight_name, logs_dir):
        """Find and parse the processing log file."""
        log_file = logs_dir / f"{flight_name}.txt"
        
        if not log_file.exists():
            return {}
        
        try:
            with open(log_file, 'r') as f:
                content = f.read()
            
            return self._parse_log_content(content)
        except Exception as e:
            logger.warning(f"Failed to parse log {log_file}: {e}")
            return {}
    
    def _parse_log_content(self, content):
        """Extract useful information from log content."""
        data = {}
        
        # Find processing start time
        start_match = re.search(
            r'INFO (\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}),\d+ .+\[run_thermal_processing\] === STARTING PROCESSING',
            content
        )
        if start_match:
            try:
                data['processing_started_at'] = timezone.make_aware(
                    datetime.strptime(start_match.group(1), '%Y-%m-%d %H:%M:%S')
                )
            except Exception:
                pass
        
        # Find processing end time
        end_match = re.search(
            r'INFO (\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}),\d+ .+\[run_thermal_processing\] === FINISHED PROCESSING',
            content
        )
        if end_match:
            try:
                data['processing_completed_at'] = timezone.make_aware(
                    datetime.strptime(end_match.group(1), '%Y-%m-%d %H:%M:%S')
                )
            except Exception:
                pass
        
        # Find total images processed
        images_match = re.search(r'Merging (\d+) input files into:', content)
        if images_match:
            data['total_images_processed'] = int(images_match.group(1))
        
        # Find hotspots detected
        hotspots_match = re.search(r'Converting (\d+) Hotspot Images', content)
        if hotspots_match:
            data['hotspots_detected'] = int(hotspots_match.group(1))
        
        # Find districts
        districts_match = re.search(r"Footprint lies in district\(s\) (\[.+?\])", content)
        if districts_match:
            try:
                # Parse the list string
                districts_str = districts_match.group(1)
                data['districts_covered'] = eval(districts_str)  # Safe since it's from log
            except Exception:
                pass
        
        # Alternative districts pattern
        if not data.get('districts_covered'):
            alt_districts = re.search(r"district\(s\) \['([^']+)'\]", content)
            if alt_districts:
                data['districts_covered'] = [alt_districts.group(1)]
        
        return data
    
    def _create_job(self, data):
        """Create a new ThermalProcessingJob record."""
        job = ThermalProcessingJob.objects.create(
            flight_name=data['flight_name'],
            original_filename=data['original_filename'],
            status=data['status'],
            progress_percentage=data['progress_percentage'],
            current_step=data['current_step'],
            file_size=data['file_size'],
            file_path=data['file_path'],
            uploaded_by=data['uploaded_by'],
            uploaded_by_email=data['uploaded_by_email'],
            processing_started_at=data['processing_started_at'],
            processing_completed_at=data['processing_completed_at'],
            output_geopackage_path=data['output_geopackage_path'],
            error_message=data['error_message'],
            log_file_path=data['log_file_path'],
            total_images_processed=data['total_images_processed'],
            hotspots_detected=data['hotspots_detected'],
            districts_covered=data['districts_covered'],
        )
        
        # Override created_at if we have it from metadata
        if data['created_at']:
            job.created_at = data['created_at']
            job.save(update_fields=['created_at'])
        
        return job
    
    def _update_job(self, job, data):
        """Update an existing job with new data."""
        job.original_filename = data['original_filename']
        job.status = data['status']
        job.progress_percentage = data['progress_percentage']
        job.current_step = data['current_step']
        job.file_size = data['file_size']
        job.file_path = data['file_path']
        job.uploaded_by = data['uploaded_by']
        job.uploaded_by_email = data['uploaded_by_email']
        job.processing_started_at = data['processing_started_at']
        job.processing_completed_at = data['processing_completed_at']
        job.output_geopackage_path = data['output_geopackage_path']
        job.error_message = data['error_message']
        job.log_file_path = data['log_file_path']
        job.total_images_processed = data['total_images_processed']
        job.hotspots_detected = data['hotspots_detected']
        job.districts_covered = data['districts_covered']
        
        if data['created_at']:
            job.created_at = data['created_at']
        
        job.save()
    
    def _display_dry_run_info(self, flight_name, data):
        """Display information about what would be migrated."""
        self.stdout.write(f"\n  📋 {flight_name}")
        self.stdout.write(f"      Original file: {data['original_filename']}")
        self.stdout.write(f"      Uploaded by: {data['uploaded_by_email']}")
        self.stdout.write(f"      File size: {self._format_size(data['file_size'])}")
        self.stdout.write(f"      Images processed: {data['total_images_processed'] or 'N/A'}")
        self.stdout.write(f"      Hotspots detected: {data['hotspots_detected'] or 'N/A'}")
        self.stdout.write(f"      Districts: {', '.join(data['districts_covered']) or 'N/A'}")
        
        if data['processing_started_at'] and data['processing_completed_at']:
            duration = data['processing_completed_at'] - data['processing_started_at']
            self.stdout.write(f"      Processing duration: {duration}")
    
    def _format_size(self, size_bytes):
        """Format file size in human-readable format."""
        if size_bytes == 0:
            return "0 B"
        
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size_bytes < 1024.0:
                return f"{size_bytes:.2f} {unit}"
            size_bytes /= 1024.0
        
        return f"{size_bytes:.2f} TB"
