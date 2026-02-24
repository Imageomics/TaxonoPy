import json
import os

import pytest

from taxonopy.manifest import (
    MANIFEST_FILENAMES,
    RESOLUTION_STATS_FILENAME,
    delete_from_manifest,
    get_intended_files_for_common_names,
    get_intended_files_for_resolve,
    read_manifest,
    write_manifest,
)


class TestManifestFilenames:
    def test_resolve_filename(self):
        assert MANIFEST_FILENAMES["resolve"] == "taxonopy_resolve_manifest.json"

    def test_common_names_filename(self):
        assert MANIFEST_FILENAMES["common-names"] == "taxonopy_common_names_manifest.json"

    def test_filenames_are_distinct(self):
        assert MANIFEST_FILENAMES["resolve"] != MANIFEST_FILENAMES["common-names"]


class TestGetIntendedFilesForResolve:
    def test_single_file_normal(self, tmp_path):
        input_file = tmp_path / "sample.csv"
        input_file.write_text("uuid,kingdom\n1,Animalia\n")
        out = str(tmp_path / "out")

        files = get_intended_files_for_resolve(str(tmp_path), [str(input_file)], out, "csv")

        assert "sample.resolved.csv" in files
        assert "sample.unsolved.csv" in files
        assert RESOLUTION_STATS_FILENAME in files
        assert MANIFEST_FILENAMES["resolve"] in files

    def test_single_file_force_input(self, tmp_path):
        input_file = tmp_path / "sample.csv"
        input_file.write_text("uuid,kingdom\n1,Animalia\n")
        out = str(tmp_path / "out")

        files = get_intended_files_for_resolve(
            str(tmp_path), [str(input_file)], out, "parquet", force_input=True
        )

        assert "sample.forced.parquet" in files
        assert "sample.resolved.parquet" not in files
        assert "sample.unsolved.parquet" not in files
        assert RESOLUTION_STATS_FILENAME not in files
        assert MANIFEST_FILENAMES["resolve"] in files

    def test_subdirectory_structure_preserved(self, tmp_path):
        subdir = tmp_path / "sub"
        subdir.mkdir()
        input_file = subdir / "sample.csv"
        input_file.write_text("uuid,kingdom\n1,Animalia\n")
        out = str(tmp_path / "out")

        files = get_intended_files_for_resolve(str(tmp_path), [str(input_file)], out, "csv")

        assert any("sub" in f and "sample.resolved.csv" in f for f in files)
        assert any("sub" in f and "sample.unsolved.csv" in f for f in files)

    def test_parquet_format(self, tmp_path):
        input_file = tmp_path / "sample.csv"
        input_file.write_text("uuid,kingdom\n1,Animalia\n")
        out = str(tmp_path / "out")

        files = get_intended_files_for_resolve(str(tmp_path), [str(input_file)], out, "parquet")

        assert "sample.resolved.parquet" in files
        assert "sample.unsolved.parquet" in files


class TestGetIntendedFilesForCommonNames:
    def test_lists_output_files_and_manifest(self, tmp_path):
        annotation_dir = tmp_path / "resolved"
        annotation_dir.mkdir()
        p = annotation_dir / "sample.resolved.parquet"
        p.write_text("")

        files = get_intended_files_for_common_names(str(annotation_dir), [str(p)])

        assert "sample.resolved.parquet" in files
        assert MANIFEST_FILENAMES["common-names"] in files

    def test_subdirectory_structure_preserved(self, tmp_path):
        annotation_dir = tmp_path / "resolved"
        sub = annotation_dir / "sub"
        sub.mkdir(parents=True)
        p = sub / "sample.resolved.parquet"
        p.write_text("")

        files = get_intended_files_for_common_names(str(annotation_dir), [str(p)])

        import os
        assert os.path.join("sub", "sample.resolved.parquet") in files


class TestWriteManifest:
    def test_creates_file_with_correct_content(self, tmp_path):
        write_manifest(str(tmp_path), "resolve", "0.2.0", "input/", "cache/ns", ["a.csv"])

        manifest_path = tmp_path / MANIFEST_FILENAMES["resolve"]
        assert manifest_path.exists()
        data = json.loads(manifest_path.read_text())
        assert data["command"] == "resolve"
        assert data["taxonopy_version"] == "0.2.0"
        assert data["input"] == "input/"
        assert data["cache_namespace"] == "cache/ns"
        assert "a.csv" in data["files"]
        assert "created_at" in data

    def test_common_names_uses_correct_filename(self, tmp_path):
        write_manifest(str(tmp_path), "common-names", "0.2.0", "input/", None, [])

        assert (tmp_path / MANIFEST_FILENAMES["common-names"]).exists()
        assert not (tmp_path / MANIFEST_FILENAMES["resolve"]).exists()

    def test_cache_namespace_can_be_none(self, tmp_path):
        write_manifest(str(tmp_path), "common-names", "0.2.0", "input/", None, [])

        data = json.loads((tmp_path / MANIFEST_FILENAMES["common-names"]).read_text())
        assert data["cache_namespace"] is None


class TestReadManifest:
    def test_returns_none_when_missing(self, tmp_path):
        assert read_manifest(str(tmp_path), "resolve") is None

    def test_returns_none_for_wrong_command(self, tmp_path):
        write_manifest(str(tmp_path), "resolve", "0.2.0", "input/", None, [])
        assert read_manifest(str(tmp_path), "common-names") is None

    def test_reads_existing_manifest(self, tmp_path):
        write_manifest(str(tmp_path), "resolve", "0.2.0", "input/", None, ["a.csv"])

        data = read_manifest(str(tmp_path), "resolve")
        assert data is not None
        assert data["command"] == "resolve"
        assert "a.csv" in data["files"]


class TestDeleteFromManifest:
    def test_deletes_listed_files_and_manifest(self, tmp_path):
        (tmp_path / "sample.resolved.csv").write_text("data")
        (tmp_path / "sample.unsolved.csv").write_text("data")
        (tmp_path / RESOLUTION_STATS_FILENAME).write_text("{}")
        files = [
            "sample.resolved.csv",
            "sample.unsolved.csv",
            RESOLUTION_STATS_FILENAME,
            MANIFEST_FILENAMES["resolve"],
        ]
        write_manifest(str(tmp_path), "resolve", "0.2.0", "input/", None, files)

        result = delete_from_manifest(str(tmp_path), "resolve")

        assert result is True
        assert not (tmp_path / "sample.resolved.csv").exists()
        assert not (tmp_path / "sample.unsolved.csv").exists()
        assert not (tmp_path / RESOLUTION_STATS_FILENAME).exists()
        assert not (tmp_path / MANIFEST_FILENAMES["resolve"]).exists()

    def test_returns_false_when_no_manifest(self, tmp_path):
        assert delete_from_manifest(str(tmp_path), "resolve") is False

    def test_tolerates_missing_listed_files(self, tmp_path):
        files = ["missing.resolved.csv", MANIFEST_FILENAMES["resolve"]]
        write_manifest(str(tmp_path), "resolve", "0.2.0", "input/", None, files)

        result = delete_from_manifest(str(tmp_path), "resolve")

        assert result is True
        assert not (tmp_path / MANIFEST_FILENAMES["resolve"]).exists()

    def test_does_not_delete_unlisted_files(self, tmp_path):
        (tmp_path / "user_file.txt").write_text("keep me")
        (tmp_path / "sample.resolved.csv").write_text("data")
        files = ["sample.resolved.csv", MANIFEST_FILENAMES["resolve"]]
        write_manifest(str(tmp_path), "resolve", "0.2.0", "input/", None, files)

        delete_from_manifest(str(tmp_path), "resolve")

        assert (tmp_path / "user_file.txt").exists()

    def test_scoped_to_command(self, tmp_path):
        (tmp_path / "sample.resolved.csv").write_text("data")
        write_manifest(
            str(tmp_path), "resolve", "0.2.0", "input/", None,
            ["sample.resolved.csv", MANIFEST_FILENAMES["resolve"]],
        )
        write_manifest(
            str(tmp_path), "common-names", "0.2.0", "input/", None,
            [MANIFEST_FILENAMES["common-names"]],
        )

        delete_from_manifest(str(tmp_path), "resolve")

        assert not (tmp_path / MANIFEST_FILENAMES["resolve"]).exists()
        assert (tmp_path / MANIFEST_FILENAMES["common-names"]).exists()

    def test_manifest_written_before_output_files(self, tmp_path):
        """Manifest must exist before any output file is created."""
        manifest_path = tmp_path / MANIFEST_FILENAMES["resolve"]
        output_file = tmp_path / "sample.resolved.csv"

        write_manifest(
            str(tmp_path), "resolve", "0.2.0", "input/", None,
            ["sample.resolved.csv", MANIFEST_FILENAMES["resolve"]],
        )
        assert manifest_path.exists()
        assert not output_file.exists()

        output_file.write_text("data")
        assert manifest_path.exists()
        assert output_file.exists()

    def test_skips_non_string_entries_in_manifest(self, tmp_path):
        (tmp_path / "valid.csv").write_text("data")
        files = [42, None, "valid.csv", MANIFEST_FILENAMES["resolve"]]
        write_manifest(str(tmp_path), "resolve", "0.2.0", "input/", None, files)

        result = delete_from_manifest(str(tmp_path), "resolve")

        assert result is True
        assert not (tmp_path / "valid.csv").exists()
        assert not (tmp_path / MANIFEST_FILENAMES["resolve"]).exists()

    def test_rejects_path_traversal_in_manifest(self, tmp_path):
        outside = tmp_path.parent / "outside.txt"
        outside.write_text("keep me")
        files = ["../outside.txt", MANIFEST_FILENAMES["resolve"]]
        write_manifest(str(tmp_path), "resolve", "0.2.0", "input/", None, files)

        delete_from_manifest(str(tmp_path), "resolve")

        assert outside.exists()

    def test_rejects_absolute_path_in_manifest(self, tmp_path):
        outside = tmp_path.parent / "outside_abs.txt"
        outside.write_text("keep me")
        files = [str(outside.resolve()), MANIFEST_FILENAMES["resolve"]]
        write_manifest(str(tmp_path), "resolve", "0.2.0", "input/", None, files)

        delete_from_manifest(str(tmp_path), "resolve")

        assert outside.exists()

    def test_rejects_symlink_escape_in_manifest(self, tmp_path):
        outside = tmp_path.parent / "outside_sym.txt"
        outside.write_text("keep me")
        link = tmp_path / "link.txt"
        try:
            link.symlink_to(outside)
        except OSError:
            pytest.skip("symlink creation not permitted on this platform")
        files = ["link.txt", MANIFEST_FILENAMES["resolve"]]
        write_manifest(str(tmp_path), "resolve", "0.2.0", "input/", None, files)

        delete_from_manifest(str(tmp_path), "resolve")

        assert outside.exists()
