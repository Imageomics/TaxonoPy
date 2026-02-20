import json
from pathlib import Path

from taxonopy.output_manager import (
    MANIFEST_FILENAME,
    read_output_manifest,
    write_output_manifest,
)


def test_write_output_manifest_creates_file(tmp_path):
    files = [str(tmp_path / "a.resolved.parquet"), str(tmp_path / "b.unsolved.parquet")]
    manifest_path = write_output_manifest(str(tmp_path), files)

    assert Path(manifest_path).exists()
    assert Path(manifest_path).name == MANIFEST_FILENAME


def test_write_output_manifest_stores_relative_paths(tmp_path):
    files = [str(tmp_path / "a.resolved.parquet"), str(tmp_path / "sub" / "b.unsolved.csv")]
    write_output_manifest(str(tmp_path), files)

    manifest = json.loads((tmp_path / MANIFEST_FILENAME).read_text())
    assert "a.resolved.parquet" in manifest["files"]
    assert str(Path("sub") / "b.unsolved.csv") in manifest["files"]
    # No absolute paths stored
    for f in manifest["files"]:
        assert not Path(f).is_absolute()


def test_read_output_manifest_returns_absolute_paths(tmp_path):
    files = [str(tmp_path / "a.resolved.parquet"), str(tmp_path / "resolution_stats.json")]
    write_output_manifest(str(tmp_path), files)

    result = read_output_manifest(str(tmp_path))
    assert sorted(result) == sorted(files)


def test_read_output_manifest_returns_empty_when_missing(tmp_path):
    result = read_output_manifest(str(tmp_path))
    assert result == []


def test_read_output_manifest_returns_empty_on_corrupt_json(tmp_path):
    (tmp_path / MANIFEST_FILENAME).write_text("not valid json{{{")
    result = read_output_manifest(str(tmp_path))
    assert result == []


def test_full_rerun_deletes_only_manifest_files(tmp_path):
    """Simulate the --full-rerun logic: only files listed in the manifest are removed."""
    taxonopy_file = tmp_path / "data.resolved.parquet"
    other_file = tmp_path / "important_user_data.csv"
    taxonopy_file.write_text("taxonopy output")
    other_file.write_text("user data")

    write_output_manifest(str(tmp_path), [str(taxonopy_file)])

    # Simulate --full-rerun behaviour
    manifest_files = read_output_manifest(str(tmp_path))
    manifest_path = tmp_path / MANIFEST_FILENAME
    for f in manifest_files:
        Path(f).unlink(missing_ok=True)
    manifest_path.unlink(missing_ok=True)

    assert not taxonopy_file.exists(), "TaxonoPy output file should have been removed"
    assert other_file.exists(), "Non-TaxonoPy file should NOT have been removed"
    assert not manifest_path.exists(), "Manifest should have been removed"
