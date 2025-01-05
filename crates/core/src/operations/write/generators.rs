///! This module contains the datafusion generators used by the write operation
///
///
use arrow_array::RecordBatch;
use datafusion::physical_plan::memory::LazyBatchGenerator;

use std::collections::VecDeque;

/// Simple in-memory generator to demonstrate the [LazyBatchGenerator] concept
#[derive(Clone, Debug, Default)]
pub struct InMemoryGenerator {
    batches: VecDeque<RecordBatch>,
}

impl InMemoryGenerator {
    pub fn from(batches: Vec<RecordBatch>) -> Self {
        Self {
            batches: VecDeque::from(batches),
            ..Default::default()
        }
    }
}

impl std::fmt::Display for InMemoryGenerator {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(f, "InMemoryGenerator<{:?}>", self.batches[0].schema())
    }
}

impl LazyBatchGenerator for InMemoryGenerator {
    fn generate_next_batch(&mut self) -> datafusion::common::Result<Option<RecordBatch>> {
        Ok(self.batches.pop_front())
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::writer::test_utils::get_record_batch;

    #[test]
    fn test_in_memory() {
        let batches = vec![get_record_batch(None, false)];
        let mut generator = InMemoryGenerator::from(batches);

        let batch = generator.generate_next_batch();
        assert!(batch.is_ok());
        if let Ok(batch) = batch {
            assert_ne!(
                batch, None,
                "The first invocation should have returned a batch!"
            );
        }
        if let Ok(batch) = generator.generate_next_batch() {
            assert_eq!(batch, None, "There should have only been one match");
        }
    }
}
