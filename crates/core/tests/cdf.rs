///
/// This file contains the high-level acceptance tests for all CDF (Change Data Feed) functionality
/// in the delta-rs codebase
use arrow_array::RecordBatch;
use arrow_schema::Schema as ArrowSchema;
use datafusion::assert_batches_sorted_eq;
use datafusion::prelude::*;
use datafusion_expr::{case, col, lit, when, Expr};
use deltalake_core::kernel::{DataType, PrimitiveType};
use deltalake_core::protocol::SaveMode;
use deltalake_core::*;

use std::sync::Arc;

async fn setup_simple_cdf_table() -> DeltaResult<DeltaTable> {
    DeltaOps::new_in_memory()
        .create()
        .with_column(
            "id",
            DataType::Primitive(PrimitiveType::Integer),
            true,
            None,
        )
        .with_column(
            "name",
            DataType::Primitive(PrimitiveType::String),
            true,
            None,
        )
        .with_configuration_property(DeltaConfigKey::EnableChangeDataFeed, Some("true"))
        .await
}

#[tokio::test]
async fn test_create_cdc_enabled_table() {
    let table = setup_simple_cdf_table()
        .await
        .expect("Failed to create the table");
    assert_eq!(table.version(), 0);
    let metadata = table.metadata().expect("Failed to load metadata");
    assert_eq!(
        true,
        metadata
            .configuration
            .contains_key("delta.enableChangeDataFeed")
    );
    if let Some(value) = metadata.configuration.get("delta.enableChangeDataFeed") {
        assert_eq!(*value, Some("true".to_string()));
    }

    if let Ok(protocol) = table.protocol() {
        assert_eq!(
            protocol.min_writer_version, 4,
            "When CDF is enabled, the writer version should be elevated to 4"
        );
    }
}

#[tokio::test]
async fn test_unsupported_writes_to_cdf_table() -> DeltaResult<()> {
    let table = setup_simple_cdf_table()
        .await
        .expect("Failed to create table");
    assert_eq!(table.version(), 0);
    let schema: ArrowSchema =
        ArrowSchema::try_from(table.get_schema()?).expect("Failed to convert schema");
    let batches = vec![RecordBatch::try_new(
        Arc::new(schema),
        vec![
            Arc::new(arrow::array::Int32Array::from(vec![0, 1, 2])),
            Arc::new(arrow::array::StringArray::from(vec![
                "Stephen", "Denny", "Will",
            ])),
        ],
    )?];

    // WRITE
    let result = deltalake_core::operations::write::WriteBuilder::new(
        table.log_store(),
        table.state.clone(),
    )
    .with_input_batches(batches)
    .with_save_mode(SaveMode::Append)
    .await;
    assert!(result.is_ok(), "Expected the append write to succeed");
    let table = result.unwrap();
    assert_eq!(table.version(), 1, "Initial write seems to not have worked");

    // UPDATE
    let (table, _metrics) = deltalake_core::operations::update::UpdateBuilder::new(
        table.log_store(),
        table.state.unwrap(),
    )
    .with_predicate(col("id").eq(lit(1)))
    .with_update("name", lit("Carly"))
    .await?;
    assert_eq!(table.version(), 2);

    let log_store = table.log_store();
    let ctx = SessionContext::new();
    let table = Arc::new(table);
    ctx.register_table("test", table.clone()).unwrap();

    let df = ctx.sql("select * from test").await.unwrap();
    let actual = df.collect().await.unwrap();
    let expected = vec![
        "+----+---------+",
        "| id | name    |",
        "+----+---------+",
        "| 0  | Stephen |",
        "| 1  | Carly   |",
        "| 2  | Will    |",
        "+----+---------+",
    ];
    assert_batches_sorted_eq!(&expected, &actual);

    //println!("{:?}", table.as_ref().state);
    //assert!(false);

    Ok(())
}
