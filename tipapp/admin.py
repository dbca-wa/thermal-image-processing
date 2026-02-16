"""
Django Admin Configuration for Thermal Image Processing
"""

from django.contrib import admin
from tipapp.models import ThermalProcessingJob


@admin.register(ThermalProcessingJob)
class ThermalProcessingJobAdmin(admin.ModelAdmin):
    """
    Admin interface for ThermalProcessingJob model.
    Provides a read-only view of job status and details.
    """
    
    list_display = [
        'flight_name',
        'status',
        'progress_percentage',
        'uploaded_by_email',
        'created_at',
        'processing_started_at',
        'processing_completed_at',
    ]
    
    list_filter = [
        'status',
        'created_at',
        'processing_started_at',
    ]
    
    search_fields = [
        'flight_name',
        'uploaded_by_email',
        'original_filename',
    ]
    
    readonly_fields = [
        'id',
        'flight_name',
        'original_filename',
        'status',
        'progress_percentage',
        'current_step',
        'file_size',
        'file_path',
        'uploaded_by',
        'uploaded_by_email',
        'created_at',
        'updated_at',
        'processing_started_at',
        'processing_completed_at',
        'output_geopackage_path',
        'error_message',
        'log_file_path',
        'total_images_processed',
        'hotspots_detected',
        'districts_covered',
    ]
    
    fieldsets = (
        ('Job Identification', {
            'fields': ('id', 'flight_name', 'original_filename')
        }),
        ('Status', {
            'fields': ('status', 'progress_percentage', 'current_step')
        }),
        ('File Information', {
            'fields': ('file_size', 'file_path')
        }),
        ('User Information', {
            'fields': ('uploaded_by', 'uploaded_by_email')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at', 'processing_started_at', 'processing_completed_at')
        }),
        ('Processing Results', {
            'fields': ('output_geopackage_path', 'error_message', 'log_file_path')
        }),
        ('Statistics', {
            'fields': ('total_images_processed', 'hotspots_detected', 'districts_covered')
        }),
    )
    
    def has_add_permission(self, request):
        """Disable manual job creation through admin."""
        return False
    
    def has_delete_permission(self, request, obj=None):
        """Allow deletion of job records."""
        return request.user.is_superuser
