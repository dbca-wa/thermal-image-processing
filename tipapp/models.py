"""
Thermal Image Processing Models

Models for tracking thermal image processing jobs and their status.
"""

from django.db import models
from django.contrib.auth import get_user_model

User = get_user_model()


class ThermalProcessingJob(models.Model):
    """
    Tracks the status and progress of thermal image processing jobs.
    
    This model maintains a record of each uploaded file and its processing
    lifecycle, from upload through processing to completion or failure.
    """
    
    # Status choices for the job lifecycle
    STATUS_CHOICES = [
        ('UPLOADED', 'Uploaded'),           # File uploaded, pending processing
        ('QUEUED', 'Queued'),               # In pending_imports folder, waiting for cron job
        ('PROCESSING', 'Processing'),       # Currently being processed
        ('COMPLETED', 'Completed'),         # Successfully processed
        ('FAILED', 'Failed'),               # Processing failed with errors
        ('RETIRED', 'Retired'),             # Deliberately retired: folder renamed, GeoServer and PostGIS data removed
    ]
    
    # Note: id field uses Django's default BigAutoField (auto-incrementing integer)
    
    # Flight identification
    flight_name = models.CharField(
        max_length=255, 
        unique=True, 
        db_index=True,
        help_text="Flight identifier (e.g., FireFlight_20211203_052327)"
    )
    
    original_filename = models.CharField(
        max_length=255,
        help_text="Original filename when uploaded"
    )
    
    # Job status tracking
    status = models.CharField(
        max_length=20, 
        choices=STATUS_CHOICES, 
        default='UPLOADED',
        db_index=True,
        help_text="Current status of the processing job"
    )
    
    progress_percentage = models.IntegerField(
        default=0,
        help_text="Processing progress from 0 to 100"
    )
    
    current_step = models.CharField(
        max_length=255, 
        blank=True,
        help_text="Description of current processing step (e.g., 'Unzipping', 'Creating mosaic')"
    )
    
    # File information
    file_size = models.BigIntegerField(
        help_text="File size in bytes"
    )
    
    file_path = models.CharField(
        max_length=500,
        help_text="Current file system path"
    )
    
    # User tracking
    uploaded_by = models.ForeignKey(
        User, 
        on_delete=models.SET_NULL, 
        null=True,
        related_name='thermal_processing_jobs',
        help_text="User who uploaded this file"
    )
    
    uploaded_by_email = models.EmailField(
        help_text="Email address of the uploader (preserved even if user deleted)"
    )
    
    # Timestamps
    created_at = models.DateTimeField(
        auto_now_add=True,
        help_text="When the job was created (file uploaded)"
    )
    
    updated_at = models.DateTimeField(
        auto_now=True,
        help_text="Last time this record was updated"
    )
    
    processing_started_at = models.DateTimeField(
        null=True, 
        blank=True,
        help_text="When processing actually began"
    )
    
    processing_completed_at = models.DateTimeField(
        null=True, 
        blank=True,
        help_text="When processing finished (success or failure)"
    )

    retired_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the job was retired (folder renamed, GeoServer and PostGIS data removed)"
    )
    
    # Processing results
    output_geopackage_path = models.CharField(
        max_length=500, 
        blank=True,
        help_text="Path to the output GeoPackage file"
    )
    
    error_message = models.TextField(
        blank=True,
        help_text="Error message if processing failed"
    )
    
    log_file_path = models.CharField(
        max_length=500, 
        blank=True,
        help_text="Path to the processing log file"
    )
    
    # Processing statistics
    total_images_processed = models.IntegerField(
        null=True, 
        blank=True,
        help_text="Total number of thermal images processed"
    )
    
    hotspots_detected = models.IntegerField(
        null=True, 
        blank=True,
        help_text="Number of hotspots detected"
    )
    
    districts_covered = models.JSONField(
        default=list, 
        blank=True,
        help_text="List of DBCA districts covered by this flight"
    )
    
    class Meta:
        ordering = ['-created_at']
        verbose_name = "Thermal Processing Job"
        verbose_name_plural = "Thermal Processing Jobs"
        indexes = [
            models.Index(fields=['status', '-created_at']),
            models.Index(fields=['uploaded_by', '-created_at']),
            models.Index(fields=['-created_at']),
        ]
    
    def __str__(self):
        return f"{self.flight_name} - {self.get_status_display()}"
    
    def get_processing_duration(self):
        """
        Calculate the total processing duration.
        Returns None if processing hasn't started or completed.
        """
        if self.processing_started_at and self.processing_completed_at:
            return self.processing_completed_at - self.processing_started_at
        return None
    
    def is_processing(self):
        """Check if the job is currently being processed."""
        return self.status == 'PROCESSING'
    
    def is_completed(self):
        """Check if the job completed successfully."""
        return self.status == 'COMPLETED'
    
    def is_failed(self):
        """Check if the job failed."""
        return self.status == 'FAILED'

    def is_retired(self):
        """Check if the job has been retired (folder renamed, GeoServer and PostGIS data removed)."""
        return self.status == 'RETIRED'
