"""Tests of file IO (reads and writes)"""


import os
import shutil

import numpy.testing as npt
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

import hipscat.io.file_io as file_io
import hipscat.io.write_metadata as io
import hipscat.pixel_math as hist


def test_write_json_file(assert_text_file_matches, tmp_path):
    """Test of arbitrary json dictionary with strings and numbers"""

    expected_lines = [
        "{\n",
        '    "first_english": "a",',
        '    "first_greek": "alpha",',
        '    "first_number": 1,',
        r'    "first_five_fib": \[',
        "        1,",
        "        1,",
        "        2,",
        "        3,",
        "        5",
        "    ]",
        "}",
    ]

    dictionary = {}
    dictionary["first_english"] = "a"
    dictionary["first_greek"] = "alpha"
    dictionary["first_number"] = 1
    dictionary["first_five_fib"] = [1, 1, 2, 3, 5]

    json_filename = os.path.join(tmp_path, "dictionary.json")
    io.write_json_file(dictionary, json_filename)
    assert_text_file_matches(expected_lines, json_filename)


def test_write_catalog_info(assert_text_file_matches, tmp_path, basic_catalog_info):
    """Test that we accurately write out catalog metadata"""
    expected_lines = [
        "{",
        '    "catalog_name": "small_sky",',
        '    "catalog_type": "object",',
        '    "epoch": "J2000",',
        '    "ra_kw": "ra",',
        '    "dec_kw": "dec",',
        '    "total_rows": 131',
        "}",
    ]

    io.write_catalog_info(basic_catalog_info)
    metadata_filename = os.path.join(tmp_path, "small_sky", "catalog_info.json")
    assert_text_file_matches(expected_lines, metadata_filename)


def test_write_provenance_info(assert_text_file_matches, tmp_path, basic_catalog_info):
    """Test that we accurately write out tool-provided generation metadata"""
    expected_lines = [
        "{",
        '    "catalog_name": "small_sky",',
        '    "catalog_type": "object",',
        r'    "version": ".*",',  # version matches digits
        r'    "generation_date": "[.\d]+",',  # date matches date format
        '    "epoch": "J2000",',
        '    "ra_kw": "ra",',
        '    "dec_kw": "dec",',
        '    "total_rows": 131,',
        '    "tool_args": {',
        '        "tool_name": "hipscat-import",',
        '        "tool_version": "1.0.0",',
        r'        "input_file_names": \[',
        '            "file1",',
        '            "file2",',
        '            "file3"',
        "        ]",
        "    }",
        "}",
    ]

    tool_args = {
        "tool_name": "hipscat-import",
        "tool_version": "1.0.0",
        "input_file_names": ["file1", "file2", "file3"],
    }

    io.write_provenance_info(basic_catalog_info, tool_args)
    metadata_filename = os.path.join(tmp_path, "small_sky", "provenance_info.json")
    assert_text_file_matches(expected_lines, metadata_filename)


def test_write_partition_info(assert_text_file_matches, tmp_path, basic_catalog_info):
    """Test that we accurately write out the individual partition stats"""
    expected_lines = [
        "Norder,Dir,Npix,num_objects",
        "0,0,11,131",
    ]
    pixel_map = {tuple([0, 11, 131]): [44, 45, 46]}
    io.write_partition_info(basic_catalog_info, pixel_map)
    metadata_filename = os.path.join(tmp_path, "small_sky", "partition_info.csv")
    assert_text_file_matches(expected_lines, metadata_filename)

    expected_lines = [
        "Norder,Dir,Npix,num_objects",
        "1,0,44,42",
        "1,0,45,29",
        "1,0,46,42",
        "1,0,47,18",
    ]
    pixel_map = {
        tuple([1, 44, 42]): [44],
        tuple([1, 45, 29]): [45],
        tuple([1, 46, 42]): [46],
        tuple([1, 47, 18]): [47],
    }
    io.write_partition_info(basic_catalog_info, pixel_map)
    metadata_filename = os.path.join(tmp_path, "small_sky", "partition_info.csv")
    assert_text_file_matches(expected_lines, metadata_filename)


def test_write_partition_info_float(
    assert_text_file_matches, tmp_path, basic_catalog_info
):
    """Test that we accurately write out the individual partition stats
    even when the input is floats instead of ints"""
    expected_lines = [
        "Norder,Dir,Npix,num_objects",
        "0,0,11,131",
    ]
    pixel_map = {tuple([0.0, 11.0, 131.0]): [44.0, 45.0, 46.0]}
    io.write_partition_info(basic_catalog_info, pixel_map)
    metadata_filename = os.path.join(tmp_path, "small_sky", "partition_info.csv")
    assert_text_file_matches(expected_lines, metadata_filename)


def test_write_parquet_metadata(
    tmp_path, small_sky_dir, basic_catalog_parquet_metadata
):
    """Copy existing catalog and create new metadata files for it"""
    temp_path = os.path.join(tmp_path, "catalog")
    shutil.copytree(
        small_sky_dir,
        temp_path,
    )
    io.write_parquet_metadata(temp_path)
    check_parquet_schema(
        os.path.join(temp_path, "_metadata"), basic_catalog_parquet_metadata
    )
    ## _common_metadata has 0 row groups
    check_parquet_schema(
        os.path.join(temp_path, "_common_metadata"),
        basic_catalog_parquet_metadata,
        0,
    )
    ## Re-write - should still have the same properties.
    io.write_parquet_metadata(temp_path)
    check_parquet_schema(
        os.path.join(temp_path, "_metadata"), basic_catalog_parquet_metadata
    )
    ## _common_metadata has 0 row groups
    check_parquet_schema(
        os.path.join(temp_path, "_common_metadata"),
        basic_catalog_parquet_metadata,
        0,
    )


def test_write_parquet_metadata_order1(
    tmp_path, small_sky_order1_dir, basic_catalog_parquet_metadata
):
    """Copy existing catalog and create new metadata files for it,
    using a catalog with multiple files."""
    temp_path = os.path.join(tmp_path, "catalog")
    shutil.copytree(
        small_sky_order1_dir,
        temp_path,
    )

    io.write_parquet_metadata(temp_path)
    ## 4 row groups for 4 partitioned parquet files
    check_parquet_schema(
        os.path.join(temp_path, "_metadata"),
        basic_catalog_parquet_metadata,
        4,
    )
    ## _common_metadata has 0 row groups
    check_parquet_schema(
        os.path.join(temp_path, "_common_metadata"),
        basic_catalog_parquet_metadata,
        0,
    )


def test_write_index_parquet_metadata(tmp_path):
    """Create an index-like catalog, and test metadata creation."""
    temp_path = os.path.join(tmp_path, "index")

    index_parquet_path = os.path.join(temp_path, "Parts=0", "part_000_of_001.parquet")
    os.makedirs(os.path.join(temp_path, "Parts=0"))
    basic_index = pd.DataFrame({"_hipscat_id": [4000, 4001], "ps1_objid": [700, 800]})
    basic_index.to_parquet(index_parquet_path)

    index_catalog_parquet_metadata = pa.schema(
        [
            pa.field("_hipscat_id", pa.int64()),
            pa.field("ps1_objid", pa.int64()),
        ]
    )

    io.write_parquet_metadata(temp_path)
    check_parquet_schema(
        os.path.join(tmp_path, "index", "_metadata"), index_catalog_parquet_metadata
    )
    ## _common_metadata has 0 row groups
    check_parquet_schema(
        os.path.join(tmp_path, "index", "_common_metadata"),
        index_catalog_parquet_metadata,
        0,
    )


def check_parquet_schema(file_name, expected_schema, expected_num_row_groups=1):
    """Check parquet schema against expectations"""
    assert os.path.exists(file_name), f"file not found [{file_name}]"

    single_metadata = pq.read_metadata(file_name)
    schema = single_metadata.schema.to_arrow_schema()

    assert len(schema) == len(
        expected_schema
    ), f"object list not the same size ({len(schema)} vs {len(expected_schema)})"

    npt.assert_array_equal(schema.names, expected_schema.names)

    assert schema.equals(expected_schema, check_metadata=False)

    parquet_file = pq.ParquetFile(file_name)
    assert parquet_file.metadata.num_row_groups == expected_num_row_groups

    for row_index in range(0, parquet_file.metadata.num_row_groups):
        row_md = parquet_file.metadata.row_group(row_index)
        for column_index in range(0, row_md.num_columns):
            column_metadata = row_md.column(column_index)
            assert column_metadata.file_path.endswith(".parquet")


def test_read_write_fits_point_map(tmp_path):
    """Check that we write and can read a FITS file for spatial distribution."""
    initial_histogram = hist.empty_histogram(1)
    filled_pixels = [51, 29, 51, 0]
    initial_histogram[44:] = filled_pixels[:]
    io.write_fits_map(tmp_path, initial_histogram)

    output_file = os.path.join(tmp_path, "point_map.fits")

    output = file_io.read_fits_image(output_file)
    npt.assert_array_equal(output, initial_histogram)
