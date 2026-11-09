from pathlib import Path

from diskcache_community import Cache, Disk

from taxonopy import input_parser
from taxonopy.cache_manager import (
    _close_cache,
    clear_cache,
    compute_file_metadata_hash,
    configure_cache_namespace,
    load_cache,
    save_cache,
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
        cache_file = tmp_path / "dataset.csv"
        cache_file.write_text("uuid,kingdom\n1,animalia\n")
        namespace = configure_cache_namespace("resolve", "test", [str(cache_file)])
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
        assert Path(config.cache_base_dir).exists()
        assert Path(config.cache_dir).exists()


planted_calls = []


def planted():
    planted_calls.append(True)
    return []


class Planted:
    def __reduce__(self):
        return (planted, ())


def test_planted_cache_entry_is_a_miss(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "cache_dir", str(tmp_path))
    input_file = tmp_path / "sample.csv"
    input_file.write_text(
        "uuid,kingdom,phylum,class,order,family,genus,species,scientific_name\n"
        "1,Animalia,,,Hymenoptera,Apidae,Apis,Apis mellifera,Apis mellifera\n"
    )
    expected = input_parser.parse_input_list(str(input_file))

    with Cache(str(tmp_path), disk=Disk) as other_writer:
        (key,) = [key for key in other_writer if not key.endswith("::meta")]
        other_writer.set(key, Planted())

    assert input_parser.parse_input_list(str(input_file)) == expected
    assert planted_calls == []
    _close_cache()
