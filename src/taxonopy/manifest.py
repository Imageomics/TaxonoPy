"""Manifest tracking for TaxonoPy output files.

Each TaxonoPy command writes a manifest file to its output directory listing
every file it intends to produce. The manifest is written before any output
files are created, so interrupted runs leave a complete record of what should
be cleaned up on the next --full-rerun.

Manifest files are command-scoped to avoid collisions when multiple commands
share an output directory.
"""

import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from taxonopy.output_manager import compute_output_paths

logger = logging.getLogger(__name__)

MANIFEST_FILENAMES = {
    "resolve": "taxonopy_resolve_manifest.json",
    "common-names": "taxonopy_common_names_manifest.json",
}

RESOLUTION_STATS_FILENAME = "resolution_stats.json"


def get_intended_files_for_resolve(
    input_path: str,
    input_files: List[str],
    output_dir: str,
    output_format: str,
    force_input: bool = False,
) -> List[str]:
    """Return the full list of files a resolve run intends to write.

    Delegates output path naming to compute_output_paths (single source of
    truth in output_manager), then appends the fixed outputs.

    Args:
        input_path: The --input argument (file or directory).
        input_files: Expanded list of input file paths from find_input_files.
        output_dir: The --output-dir argument.
        output_format: 'csv' or 'parquet'.
        force_input: True when --force-input is set.

    Returns:
        List of relative file paths (relative to output_dir).
    """
    files = compute_output_paths(input_path, input_files, output_dir, output_format, force_input)
    if not force_input:
        files.append(RESOLUTION_STATS_FILENAME)
    files.append(MANIFEST_FILENAMES["resolve"])
    return files


def get_intended_files_for_common_names(
    annotation_dir: str,
    annotation_paths: List[str],
) -> List[str]:
    """Return the full list of files a common-names run intends to write.

    Output files preserve the input directory structure, so paths are simply
    the relative paths of the annotation files. No naming convention is
    encoded here.

    Args:
        annotation_dir: The --resolved-dir argument.
        annotation_paths: Expanded list of resolved parquet paths.

    Returns:
        List of relative file paths (relative to output_dir).
    """
    files = [os.path.relpath(p, annotation_dir) for p in annotation_paths]
    files.append(MANIFEST_FILENAMES["common-names"])
    return files


def write_manifest(
    output_dir: str,
    command: str,
    version: str,
    input_path: str,
    cache_namespace: Optional[str],
    files: List[str],
) -> Path:
    """Write a manifest file to output_dir before any output files are created.

    Args:
        output_dir: Directory where the manifest will be written.
        command: TaxonoPy command name ('resolve' or 'common-names').
        version: TaxonoPy version string.
        input_path: Value of the --input or --resolved-dir argument.
        cache_namespace: Active cache namespace path, or None.
        files: Relative paths (relative to output_dir) of all intended outputs.

    Returns:
        Path to the written manifest file.
    """
    manifest = {
        "taxonopy_version": version,
        "command": command,
        "created_at": datetime.now().isoformat(),
        "input": input_path,
        "cache_namespace": cache_namespace,
        "files": files,
    }
    manifest_path = Path(output_dir) / MANIFEST_FILENAMES[command]
    manifest_path.write_text(json.dumps(manifest, indent=4))
    logger.info("Manifest written to %s", manifest_path)
    return manifest_path


def read_manifest(output_dir: str, command: str) -> Optional[dict]:
    """Read the manifest for a given command from output_dir.

    Args:
        output_dir: Directory to look for the manifest.
        command: TaxonoPy command name ('resolve' or 'common-names').

    Returns:
        Parsed manifest dict, or None if no manifest file is present.
    """
    manifest_path = Path(output_dir) / MANIFEST_FILENAMES[command]
    if not manifest_path.exists():
        return None
    return json.loads(manifest_path.read_text())


def delete_from_manifest(output_dir: str, command: str) -> bool:
    """Delete all files listed in the manifest, then delete the manifest itself.

    Only deletes files that actually exist; missing files are silently skipped
    so that interrupted runs can be cleaned up without error.

    Args:
        output_dir: Directory containing the manifest.
        command: TaxonoPy command name ('resolve' or 'common-names').

    Returns:
        True if a manifest was found and cleanup was performed, False otherwise.
    """
    manifest = read_manifest(output_dir, command)
    if manifest is None:
        return False
    output_dir_path = Path(output_dir)
    removed = 0
    for rel_path in manifest.get("files", []):
        f = output_dir_path / rel_path
        if f.exists():
            f.unlink()
            removed += 1
    manifest_path = output_dir_path / MANIFEST_FILENAMES[command]
    if manifest_path.exists():
        manifest_path.unlink()
    logger.info("Removed %d file(s) listed in manifest for command '%s'.", removed, command)
    return True
