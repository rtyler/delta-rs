"""Regression test for delta-io/delta-rs#5074.

delta-rs wrote float/double min/max statistics that excluded NaN. Delta Spark
trusts those bounds for data skipping, so a file holding [998.0, NaN] was
skipped for `WHERE d > 998.0` even though Spark matches the NaN row.
"""

import pathlib

import pyarrow as pa
import pytest

from deltalake import write_deltalake

from .utils import get_spark


@pytest.mark.pyspark
@pytest.mark.pyarrow
@pytest.mark.integration
def test_nan_row_not_skipped_by_spark_data_skipping(tmp_path: pathlib.Path):
    table_path = str(tmp_path / "nan_stats")

    data = pa.table(
        {
            "id": pa.array([1, 2], pa.int64()),
            "d": pa.array([998.0, float("nan")], pa.float64()),
        }
    )
    write_deltalake(table_path, data)

    spark = get_spark()
    # Turn off Parquet row-group filtering so only Delta file-level skipping
    # based on the Delta log statistics is exercised.
    spark.conf.set("spark.sql.parquet.filterPushdown", "false")
    try:
        spark.conf.set("spark.databricks.delta.stats.skipping", "true")
        skipped = [
            row[0]
            for row in spark.sql(
                f"SELECT id FROM delta.`{table_path}` WHERE d > 998.0"
            ).collect()
        ]
    finally:
        spark.conf.unset("spark.databricks.delta.stats.skipping")
        spark.conf.unset("spark.sql.parquet.filterPushdown")

    # Spark orders NaN above every other value, so the NaN row must be returned.
    assert skipped == [2], f"Delta data skipping dropped NaN rows: {skipped}"
