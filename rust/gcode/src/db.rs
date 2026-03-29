use std::path::Path;

use anyhow::Context as _;
use rusqlite::Connection;

/// Open gobby-hub.db in read-write mode with WAL and busy timeout.
pub fn open_readwrite(path: &Path) -> anyhow::Result<Connection> {
    let conn = Connection::open(path)
        .with_context(|| format!("failed to open database: {}", path.display()))?;
    conn.busy_timeout(std::time::Duration::from_millis(5000))?;
    conn.execute_batch("PRAGMA journal_mode=WAL; PRAGMA foreign_keys=ON;")?;
    Ok(conn)
}

/// Open gobby-hub.db in read-only mode with busy timeout.
pub fn open_readonly(path: &Path) -> anyhow::Result<Connection> {
    let conn = Connection::open_with_flags(
        path,
        rusqlite::OpenFlags::SQLITE_OPEN_READ_ONLY | rusqlite::OpenFlags::SQLITE_OPEN_NO_MUTEX,
    )
    .with_context(|| format!("failed to open database (read-only): {}", path.display()))?;
    conn.busy_timeout(std::time::Duration::from_millis(5000))?;
    Ok(conn)
}
