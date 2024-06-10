import json
import os

import pandas as pd
import pytest

from hipscat.catalog import CatalogType
from hipscat.catalog.association_catalog.association_catalog import AssociationCatalog
from hipscat.catalog.association_catalog.partition_join_info import PartitionJoinInfo
from hipscat.loaders import read_from_hipscat
from hipscat.pixel_math import HealpixPixel


def test_init_catalog(association_catalog_info, association_catalog_join_pixels):
    catalog = AssociationCatalog(
        association_catalog_info, [HealpixPixel(0, 11)], association_catalog_join_pixels
    )
    assert catalog.catalog_name == association_catalog_info.catalog_name
    pd.testing.assert_frame_equal(catalog.get_join_pixels(), association_catalog_join_pixels)
    assert catalog.get_healpix_pixels() == [HealpixPixel(0, 11)]
    assert catalog.catalog_info == association_catalog_info

    assert len(catalog.get_healpix_pixels()) == len([HealpixPixel(0, 11)])
    for hp_pixel in catalog.get_healpix_pixels():
        assert hp_pixel in [HealpixPixel(0, 11)]
        assert hp_pixel in catalog.pixel_tree


def test_wrong_catalog_type(association_catalog_info, association_catalog_join_pixels):
    association_catalog_info.catalog_type = CatalogType.OBJECT
    with pytest.raises(ValueError, match="catalog_type"):
        AssociationCatalog(association_catalog_info, [HealpixPixel(0, 11)], association_catalog_join_pixels)


def test_wrong_catalog_info_type(catalog_info, association_catalog_join_pixels):
    catalog_info.catalog_type = CatalogType.ASSOCIATION
    with pytest.raises(TypeError, match="catalog_info"):
        AssociationCatalog(catalog_info, [HealpixPixel(0, 11)], association_catalog_join_pixels)


def test_wrong_join_pixels_type(association_catalog_info):
    with pytest.raises(TypeError, match="join_pixels"):
        AssociationCatalog(association_catalog_info, [HealpixPixel(0, 11)], "test")


def test_different_join_pixels_type(association_catalog_info, association_catalog_join_pixels):
    partition_join_info = PartitionJoinInfo(association_catalog_join_pixels)
    catalog = AssociationCatalog(association_catalog_info, [HealpixPixel(0, 11)], partition_join_info)
    pd.testing.assert_frame_equal(catalog.get_join_pixels(), association_catalog_join_pixels)


def test_read_from_file(association_catalog_path, association_catalog_join_pixels):
    catalog = read_from_hipscat(association_catalog_path)

    assert isinstance(catalog, AssociationCatalog)
    assert catalog.on_disk
    assert catalog.catalog_path == str(association_catalog_path)
    assert len(catalog.get_join_pixels()) == 4
    assert len(catalog.get_healpix_pixels()) == 1
    pd.testing.assert_frame_equal(catalog.get_join_pixels(), association_catalog_join_pixels)
    assert catalog.get_healpix_pixels() == [HealpixPixel(0, 11)]

    info = catalog.catalog_info
    assert info.primary_catalog == "small_sky"
    assert info.primary_column == "id"
    assert info.join_catalog == "small_sky_order1"
    assert info.join_column == "id"


def test_empty_directory(tmp_path, association_catalog_info_data, association_catalog_join_pixels):
    """Test loading empty or incomplete data"""
    ## Path doesn't exist
    with pytest.raises(FileNotFoundError):
        read_from_hipscat(os.path.join("path", "empty"))

    catalog_path = tmp_path / "empty"
    os.makedirs(catalog_path, exist_ok=True)

    ## Path exists but there's nothing there
    with pytest.raises(FileNotFoundError, match="catalog info"):
        AssociationCatalog.read_from_hipscat(catalog_path)

    ## catalog_info file exists - getting closer
    file_name = catalog_path / "catalog_info.json"
    with open(file_name, "w", encoding="utf-8") as metadata_file:
        metadata_file.write(json.dumps(association_catalog_info_data))

    with pytest.raises(FileNotFoundError, match="metadata"):
        read_from_hipscat(catalog_path)

    ## Now we create the needed _metadata and everything is right.
    part_info = PartitionJoinInfo(association_catalog_join_pixels)
    part_info.write_to_metadata_files(catalog_path=catalog_path)
    with pytest.warns(UserWarning, match="slow"):
        catalog = read_from_hipscat(catalog_path)
    assert catalog.catalog_name == association_catalog_info_data["catalog_name"]


def test_csv_round_trip(tmp_path, association_catalog_info_data, association_catalog_join_pixels):
    ## Path doesn't exist
    with pytest.raises(FileNotFoundError):
        read_from_hipscat(os.path.join("path", "empty"))

    catalog_path = tmp_path / "empty"
    os.makedirs(catalog_path, exist_ok=True)

    file_name = catalog_path / "catalog_info.json"
    with open(file_name, "w", encoding="utf-8") as metadata_file:
        metadata_file.write(json.dumps(association_catalog_info_data))

    with pytest.raises(FileNotFoundError, match="partition"):
        read_from_hipscat(catalog_path)

    file_name = catalog_path / "partition_info.csv"
    with open(file_name, "w", encoding="utf-8") as metadata_file:
        # dump some garbage in there - just needs to exist.
        metadata_file.write(json.dumps(association_catalog_info_data))
    with pytest.raises(FileNotFoundError, match="partition"):
        read_from_hipscat(catalog_path)

    part_info = PartitionJoinInfo(association_catalog_join_pixels)
    part_info.write_to_csv(catalog_path=catalog_path)

    catalog = read_from_hipscat(catalog_path)
    pd.testing.assert_frame_equal(catalog.get_join_pixels(), association_catalog_join_pixels)
