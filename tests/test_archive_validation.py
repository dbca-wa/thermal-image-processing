"""
Unit tests for validate_archive_structure() in thermal_image_processing.py.

All tests mock subprocess.run so no real 7z binary or archive file is required.
The mock target is the module where subprocess is *used*:
    thermalimageprocessing.thermal_image_processing
"""
import subprocess
from unittest.mock import MagicMock, patch

import pytest

from thermalimageprocessing.thermal_image_processing import (
    ArchiveValidationError,
    validate_archive_structure,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

MOCK_ARCHIVE = "/fake/path/FireFlight_20240110_045153.7z"

# Minimal valid 7z listing output that passes all checks.
_VALID_LISTING = """\
7-Zip 22.01 (x64) : Copyright (c) 1999-2022 Igor Pavlov : 2022-07-15

Listing archive: /fake/path/FireFlight_20240110_045153.7z

   Date      Time    Attr         Size   Compressed  Name
------------------- ----- ------------ ------------  ------------------------
2024-01-10 04:51:53 D....            0            0  FireFlight_20240110_045153
2024-01-10 04:51:53 D....            0            0  FireFlight_20240110_045153/PNGs
2024-01-10 04:51:53 D....            0            0  FireFlight_20240110_045153/PNGs/CAMERA1
2024-01-10 04:51:53 D....            0            0  FireFlight_20240110_045153/KML Boundaries
2024-01-10 04:51:53 D....            0            0  FireFlight_20240110_045153/KML Boundaries/CAMERA1
2024-01-10 04:51:53 ....         12345         5678  FireFlight_20240110_045153/PNGs/CAMERA1/img001.png
------------------- ----- ------------ ------------  ------------------------
               12345         5678  1 files, 5 folders
"""

MODULE = "thermalimageprocessing.thermal_image_processing"


def _mock_run(stdout: str) -> MagicMock:
    """Return a mock that subprocess.run will return with the given stdout."""
    result = MagicMock()
    result.stdout = stdout
    return result


# ---------------------------------------------------------------------------
# Happy-path test
# ---------------------------------------------------------------------------


class TestValidArchive:
    def test_valid_archive_passes_without_exception(self):
        with patch(f"{MODULE}.subprocess.run", return_value=_mock_run(_VALID_LISTING)):
            # Should not raise
            validate_archive_structure(MOCK_ARCHIVE)

    def test_valid_archive_with_suffix_passes(self):
        """Optional _N suffix on flight folder name is accepted."""
        listing = _VALID_LISTING.replace(
            "FireFlight_20240110_045153", "FireFlight_20240110_045153_2"
        )
        with patch(f"{MODULE}.subprocess.run", return_value=_mock_run(listing)):
            validate_archive_structure(MOCK_ARCHIVE)


# ---------------------------------------------------------------------------
# Corrupt / unreadable archive
# ---------------------------------------------------------------------------


class TestCorruptArchive:
    def test_called_process_error_raises_archive_validation_error(self):
        error = subprocess.CalledProcessError(
            returncode=2,
            cmd=["7z", "l", MOCK_ARCHIVE],
            stderr="ERROR: Cannot open the file as archive",
        )
        with patch(f"{MODULE}.subprocess.run", side_effect=error):
            with pytest.raises(ArchiveValidationError, match="could not be opened"):
                validate_archive_structure(MOCK_ARCHIVE)

    def test_error_message_includes_archive_filename(self):
        error = subprocess.CalledProcessError(
            returncode=2,
            cmd=["7z", "l", MOCK_ARCHIVE],
            stderr="broken",
        )
        with patch(f"{MODULE}.subprocess.run", side_effect=error):
            with pytest.raises(ArchiveValidationError) as exc_info:
                validate_archive_structure(MOCK_ARCHIVE)
        assert "FireFlight_20240110_045153.7z" in str(exc_info.value)

    def test_error_message_includes_stderr_detail(self):
        error = subprocess.CalledProcessError(
            returncode=2,
            cmd=["7z", "l", MOCK_ARCHIVE],
            stderr="  some 7z error detail  ",
        )
        with patch(f"{MODULE}.subprocess.run", side_effect=error):
            with pytest.raises(ArchiveValidationError) as exc_info:
                validate_archive_structure(MOCK_ARCHIVE)
        assert "some 7z error detail" in str(exc_info.value)


# ---------------------------------------------------------------------------
# 7z not installed
# ---------------------------------------------------------------------------


class TestSevenZipNotInstalled:
    def test_file_not_found_raises_runtime_error(self):
        with patch(f"{MODULE}.subprocess.run", side_effect=FileNotFoundError):
            with pytest.raises(RuntimeError, match="7z is not installed"):
                validate_archive_structure(MOCK_ARCHIVE)


# ---------------------------------------------------------------------------
# Root-directory checks
# ---------------------------------------------------------------------------


class TestRootDirectoryChecks:
    def test_no_root_dir_raises_archive_validation_error(self):
        """Archive with no root-level directory should fail."""
        # Listing with only file entries, no D.... lines at root level
        listing = """\
   Date      Time    Attr         Size   Compressed  Name
------------------- ----- ------------ ------------  ------------------------
2024-01-10 04:51:53 ....         12345         5678  some_file.png
"""
        with patch(f"{MODULE}.subprocess.run", return_value=_mock_run(listing)):
            with pytest.raises(ArchiveValidationError, match="no root-level folder"):
                validate_archive_structure(MOCK_ARCHIVE)

    def test_multiple_root_dirs_raises_archive_validation_error(self):
        """Archive with more than one root directory should fail."""
        listing = """\
   Date      Time    Attr         Size   Compressed  Name
------------------- ----- ------------ ------------  ------------------------
2024-01-10 04:51:53 D....            0            0  FireFlight_20240110_045153
2024-01-10 04:51:53 D....            0            0  AnotherFolder
"""
        with patch(f"{MODULE}.subprocess.run", return_value=_mock_run(listing)):
            with pytest.raises(ArchiveValidationError, match="multiple root-level folders"):
                validate_archive_structure(MOCK_ARCHIVE)


# ---------------------------------------------------------------------------
# Flight folder name pattern checks
# ---------------------------------------------------------------------------


class TestFlightNamePattern:
    @pytest.mark.parametrize("bad_name", [
        "FireFlight_20240110",            # missing time
        "fireflight_20240110_045153",     # lowercase
        "FireFlight_20240110_045153_",    # trailing underscore
        "FireFlight_2024011_045153",      # wrong date length
        "Flight_20240110_045153",         # wrong prefix
        "FireFlight_20240110_0451531",    # time part too long
        "FireFlight20240110045153",       # missing underscores
    ])
    def test_invalid_folder_name_raises_archive_validation_error(self, bad_name):
        listing = (
            f"2024-01-10 04:51:53 D....            0            0  {bad_name}\n"
            f"2024-01-10 04:51:53 D....            0            0  {bad_name}/PNGs/CAMERA1\n"
            f"2024-01-10 04:51:53 D....            0            0  {bad_name}/KML Boundaries/CAMERA1\n"
        )
        with patch(f"{MODULE}.subprocess.run", return_value=_mock_run(listing)):
            with pytest.raises(ArchiveValidationError, match="does not match the required naming convention"):
                validate_archive_structure(MOCK_ARCHIVE)

    @pytest.mark.parametrize("good_name", [
        "FireFlight_20240110_045153",
        "FireFlight_20240110_045153_2",
        "FireFlight_20240110_045153_10",
    ])
    def test_valid_folder_name_patterns_pass(self, good_name):
        listing = (
            f"2024-01-10 04:51:53 D....            0            0  {good_name}\n"
            f"2024-01-10 04:51:53 D....            0            0  {good_name}/PNGs/CAMERA1\n"
            f"2024-01-10 04:51:53 D....            0            0  {good_name}/KML Boundaries/CAMERA1\n"
        )
        with patch(f"{MODULE}.subprocess.run", return_value=_mock_run(listing)):
            validate_archive_structure(MOCK_ARCHIVE)  # no exception expected


# ---------------------------------------------------------------------------
# Sub-folder presence checks
# ---------------------------------------------------------------------------


class TestSubFolderChecks:
    def _listing_without(self, *omit_keywords):
        """Build listing from the valid template, removing lines that contain any of the keywords."""
        lines = _VALID_LISTING.splitlines()
        filtered = [
            line for line in lines
            if not any(kw.lower() in line.lower() for kw in omit_keywords)
        ]
        return "\n".join(filtered)

    def test_missing_pngs_camera_raises(self):
        listing = self._listing_without("PNGs/CAMERA", "PNGs\\CAMERA")
        with patch(f"{MODULE}.subprocess.run", return_value=_mock_run(listing)):
            with pytest.raises(ArchiveValidationError, match="PNGs/CAMERA"):
                validate_archive_structure(MOCK_ARCHIVE)

    def test_missing_kml_boundaries_camera_raises(self):
        listing = self._listing_without("KML Boundaries/CAMERA", "KML Boundaries\\CAMERA")
        with patch(f"{MODULE}.subprocess.run", return_value=_mock_run(listing)):
            with pytest.raises(ArchiveValidationError, match="KML Boundaries"):
                validate_archive_structure(MOCK_ARCHIVE)

    def test_missing_both_subfolders_raises(self):
        listing = self._listing_without("PNGs/CAMERA", "KML Boundaries/CAMERA")
        with patch(f"{MODULE}.subprocess.run", return_value=_mock_run(listing)):
            with pytest.raises(ArchiveValidationError) as exc_info:
                validate_archive_structure(MOCK_ARCHIVE)
        msg = str(exc_info.value)
        assert "PNGs/CAMERA" in msg
        assert "KML Boundaries" in msg

    def test_pngs_camera_backslash_accepted(self):
        """Archives using backslash path separators (Windows-style) should pass."""
        listing = _VALID_LISTING.replace(
            "PNGs/CAMERA1", "PNGs\\CAMERA1"
        ).replace(
            "KML Boundaries/CAMERA1", "KML Boundaries\\CAMERA1"
        )
        with patch(f"{MODULE}.subprocess.run", return_value=_mock_run(listing)):
            validate_archive_structure(MOCK_ARCHIVE)  # no exception expected

    def test_subfolder_names_are_case_insensitive(self):
        """Folder name matching should be case-insensitive."""
        listing = _VALID_LISTING.replace(
            "PNGs/CAMERA1", "pngs/camera1"
        ).replace(
            "KML Boundaries/CAMERA1", "kml boundaries/camera1"
        )
        with patch(f"{MODULE}.subprocess.run", return_value=_mock_run(listing)):
            validate_archive_structure(MOCK_ARCHIVE)  # no exception expected
