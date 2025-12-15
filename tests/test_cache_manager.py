from pathlib import Path

from taxonopy.cache_manager import (
    clear_cache,
    compute_file_metadata_hash,
    load_cache,
    save_cache,
    set_cache_namespace,
)
from taxonopy.config import config


def test_compute_file_metadata_hash_changes_when_file_updates(tmp_path):
    data_file = tmp_path / "entries.csv"
    data_file.write_text("uuid,kingdom\n1,animalia\n")

    first = compute_file_metadata_hash([str(data_file)])
    # Ensure metadata (size + mtime) changes
    data_file.write_text("uuid,kingdom\n1,animalia\n2,plantae\n")
    second = compute_file_metadata_hash([str(data_file)])

    assert first != second


def test_diskcache_round_trip(tmp_path):
    original_base = config.cache_base_dir
    original_dir = config.cache_dir
    try:
        config.cache_base_dir = str(tmp_path)
        config.cache_dir = str(tmp_path)
        namespace = set_cache_namespace("pytest_cache")
        assert Path(namespace).exists()

        payload = {"value": 42}
        checksum = "unit-test-checksum"
        save_cache("unit_test_key", payload, checksum)
        cached = load_cache("unit_test_key", checksum)

        assert cached == payload
        clear_cache()
    finally:
        config.cache_base_dir = original_base
        config.cache_dir = original_dir
        config.ensure_directories()
