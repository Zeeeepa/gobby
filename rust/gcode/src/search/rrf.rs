//! Reciprocal Rank Fusion: merges FTS5 + semantic + graph boost results.
//! score(rank) = 1.0 / (K + rank) where K = 60.
//! Ports logic from src/gobby/code_index/searcher.py.
