"""Tests for reading `data_change` from get_add_actions().

`data_change` is a first-class field on every Add action in the Delta
protocol.  It is `True` for normal data-producing writes and `False` for
compaction/optimize operations that rewrite files without changing the
logical data set.

These tests verify that `DeltaTable.get_add_actions()` surfaces that flag
so callers can distinguish compaction rewrites from real data changes.

NOTE: the `data_change` column is not yet emitted by `get_add_actions()`
(the underlying scan-row schema omits it).  Tests that assert the column is
present are marked `xfail` and will start passing once the bug is fixed —
at which point the `xfail` markers should be removed.
"""

from __future__ import annotations

import pathlib

import pytest
from arro3.core import Array, DataType, Table
from arro3.core import Field as ArrowField

from deltalake import DeltaTable, write_deltalake


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _two_column_table(values: list[int]) -> Table:
    """Minimal arro3 Table with columns ``id`` (int32) and ``val`` (int32)."""
    n = len(values)
    return Table(
        {
            "id": Array(values, ArrowField("id", type=DataType.int32(), nullable=False)),
            "val": Array(
                [v * 10 for v in values],
                ArrowField("val", type=DataType.int32(), nullable=True),
            ),
        }
    )


# ---------------------------------------------------------------------------
# Tests: normal write → data_change should be True
# ---------------------------------------------------------------------------


@pytest.mark.xfail(
    reason="data_change column not yet surfaced by get_add_actions() — see plan "
    "crates/core/.hermes/plans/2026-06-14_002000-fix-to-add-data-change.md",
    strict=True,
)
def test_get_add_actions_data_change_true_after_normal_write(
    tmp_path: pathlib.Path,
) -> None:
    """A regular append write must produce Add actions with data_change=True."""
    write_deltalake(tmp_path, _two_column_table([1, 2, 3]))

    dt = DeltaTable(tmp_path)
    actions = dt.get_add_actions()

    assert "data_change" in actions.schema.names, (
        "get_add_actions() must include a 'data_change' column"
    )

    data_change_values = actions.column("data_change").to_pylist()
    assert len(data_change_values) == 1, "one file was written"
    assert data_change_values[0] is True, (
        f"normal write must produce data_change=True, got {data_change_values[0]!r}"
    )


@pytest.mark.xfail(
    reason="data_change column not yet surfaced by get_add_actions() — see plan "
    "crates/core/.hermes/plans/2026-06-14_002000-fix-to-add-data-change.md",
    strict=True,
)
def test_get_add_actions_flatten_data_change_true_after_normal_write(
    tmp_path: pathlib.Path,
) -> None:
    """Same as above but with flatten=True."""
    write_deltalake(tmp_path, _two_column_table([1, 2, 3]))

    dt = DeltaTable(tmp_path)
    actions = dt.get_add_actions(flatten=True)

    assert "data_change" in actions.schema.names
    assert actions.column("data_change").to_pylist() == [True]


# ---------------------------------------------------------------------------
# Tests: optimize/compact → data_change should be False on the latest commit
# ---------------------------------------------------------------------------


@pytest.mark.xfail(
    reason="data_change column not yet surfaced by get_add_actions() — see plan "
    "crates/core/.hermes/plans/2026-06-14_002000-fix-to-add-data-change.md",
    strict=True,
)
def test_get_add_actions_data_change_false_after_optimize(
    tmp_path: pathlib.Path,
) -> None:
    """After optimize.compact() the surviving Add actions must have data_change=False.

    Optimize rewrites multiple small files into one larger file while keeping the
    logical data set identical.  The Delta protocol requires such rewrites to use
    data_change=False so that downstream consumers (CDC, streaming) can skip them.

    This test:
    1. Writes two separate files (two appends).
    2. Compacts them with ``optimize.compact()``.
    3. Reads ``get_add_actions()`` on the resulting table version.
    4. Asserts every surviving add action carries ``data_change=False``.
    """
    # Two separate appends → two Parquet files before compaction
    write_deltalake(tmp_path, _two_column_table([1, 2, 3]), mode="append")
    write_deltalake(tmp_path, _two_column_table([4, 5, 6]), mode="append")

    dt = DeltaTable(tmp_path)
    assert dt.version() == 1, "sanity: two appends = version 1"
    assert len(dt.get_add_actions().column("path").to_pylist()) == 2

    # Compact — this produces one new Add with dataChange=false and two Removes
    dt.optimize.compact()
    assert dt.version() == 2, "sanity: optimize bumps to version 2"

    actions = dt.get_add_actions()

    # After compaction exactly one file is active
    assert actions.num_rows == 1, (
        f"expected 1 active file after compact, got {actions.num_rows}"
    )

    assert "data_change" in actions.schema.names, (
        "get_add_actions() must include a 'data_change' column"
    )

    data_change_values = actions.column("data_change").to_pylist()
    assert data_change_values == [False], (
        f"optimize produces data_change=False; got {data_change_values!r}"
    )


@pytest.mark.xfail(
    reason="data_change column not yet surfaced by get_add_actions() — see plan "
    "crates/core/.hermes/plans/2026-06-14_002000-fix-to-add-data-change.md",
    strict=True,
)
def test_get_add_actions_flatten_data_change_false_after_optimize(
    tmp_path: pathlib.Path,
) -> None:
    """Same as above but with flatten=True to cover the flattened schema path."""
    write_deltalake(tmp_path, _two_column_table([1, 2, 3]), mode="append")
    write_deltalake(tmp_path, _two_column_table([4, 5, 6]), mode="append")

    dt = DeltaTable(tmp_path)
    dt.optimize.compact()

    actions = dt.get_add_actions(flatten=True)

    assert "data_change" in actions.schema.names
    assert actions.column("data_change").to_pylist() == [False], (
        "optimize produces data_change=False in flattened schema"
    )


# ---------------------------------------------------------------------------
# Tests: mixed history — normal write after optimize resets data_change=True
# ---------------------------------------------------------------------------


@pytest.mark.xfail(
    reason="data_change column not yet surfaced by get_add_actions() — see plan "
    "crates/core/.hermes/plans/2026-06-14_002000-fix-to-add-data-change.md",
    strict=True,
)
def test_get_add_actions_data_change_mixed(tmp_path: pathlib.Path) -> None:
    """After optimize + a new append, get_add_actions() returns both flags.

    Layout after all writes:
      version 0 — append batch A  (file A, data_change=True)
      version 1 — append batch B  (file B, data_change=True)
      version 2 — optimize        (removes A+B, adds file C, data_change=False)
      version 3 — append batch D  (file D, data_change=True)

    Active files at version 3: C (data_change=False) and D (data_change=True).
    """
    write_deltalake(tmp_path, _two_column_table([1, 2]), mode="append")
    write_deltalake(tmp_path, _two_column_table([3, 4]), mode="append")

    dt = DeltaTable(tmp_path)
    dt.optimize.compact()

    # New real-data write after the compaction
    write_deltalake(tmp_path, _two_column_table([5, 6]), mode="append")

    dt = DeltaTable(tmp_path)
    assert dt.version() == 3

    actions = dt.get_add_actions()
    assert actions.num_rows == 2, "two active files: compacted + new append"

    assert "data_change" in actions.schema.names

    # Sort by path to get a deterministic order, then check values as a set
    data_change_values = set(actions.column("data_change").to_pylist())
    assert data_change_values == {True, False}, (
        f"expected {{True, False}}, got {data_change_values!r}"
    )
