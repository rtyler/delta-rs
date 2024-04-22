//! Allow for modification of operations
//!
//! The goal of the middleware module is to define a modular mechanism for modification
//! of writes to a Delta table without requiring all code to live in _one_ place to do so.
//!
//! These middleware should also allow for re-use of common functionality between flavors
//! of writers in the Delta Lake ecosystem
//!
//! # Example
//! ```rust
//! ```

use async_trait::async_trait;
use std::sync::Arc;

use crate::kernel::Action;

/// TransactionalContext is responsible for accumulating information about a transaction
/// by middleware
#[derive(Clone, Debug, Default)]
pub(crate) struct TransactionalContext<State> {
    actions: Vec<Action>,
    state: State,
}

#[async_trait]
pub(crate) trait Transactional<State>: Send + Sync {
    async fn call(&self, ctx: TransactionalContext<State>) -> TransactionalContext<State>;
}

pub(crate) type TransactionalRef<State> = Arc<dyn Transactional<State>>;

#[cfg(test)]
mod tests {
    use super::*;

    #[tokio::test]
    async fn test_simple() {
        struct Readonly {}
        #[async_trait]
        impl Transactional<()> for Readonly {
            async fn call(&self, ctx: TransactionalContext<()>) -> TransactionalContext<()> {
                ctx
            }
        }
    }
}
