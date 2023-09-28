import os

import pytest

from hipscat.catalog.dataset.dataset import Dataset
from hipscat.io.file_io import file_io, file_pointer


def test_read_from_hipscat(dataset_path_abfs, base_catalog_info_file_abfs, example_abfs_storage_options, assert_catalog_info_matches_dict):
    dataset = Dataset.read_from_hipscat(dataset_path_abfs, storage_options=example_abfs_storage_options)
    assert dataset.on_disk
    assert dataset.catalog_path == dataset_path_abfs
    assert str(dataset.catalog_base_dir) == dataset_path_abfs
    catalog_info_json = file_io.load_json_file(base_catalog_info_file_abfs, storage_options=example_abfs_storage_options)
    assert_catalog_info_matches_dict(dataset.catalog_info, catalog_info_json)


def test_read_from_missing_folder(tmp_dir_abfs, example_abfs_storage_options):
    wrong_path = os.path.join(tmp_dir_abfs, "wrong")
    with pytest.raises(FileNotFoundError, match="directory"):
        Dataset.read_from_hipscat(wrong_path, storage_options=example_abfs_storage_options)


#commenting out since relies on making directories
#def test_read_from_empty_folder(example_abfs_path, example_abfs_storage_options):
#    dataset_path = os.path.join(example_abfs_path, "empty_dataset")
#    file_io.make_directory(dataset_path, exist_ok=True, storage_options=example_abfs_storage_options)
#    with pytest.raises(FileNotFoundError, match="catalog info"):
#        Dataset.read_from_hipscat(dataset_path, storage_options=example_abfs_storage_options)
#    
#    file_io.remove_directory(dataset_path, storage_options=example_abfs_storage_options)
