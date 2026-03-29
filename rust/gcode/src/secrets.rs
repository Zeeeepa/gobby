//! Fernet decryption of gobby's SecretStore.
//!
//! Replicates the Python chain:
//! 1. Read ~/.gobby/machine_id
//! 2. Read ~/.gobby/.secret_salt (16 bytes)
//! 3. PBKDF2-HMAC-SHA256 (600,000 iterations, 32-byte key) → base64url → Fernet key
//! 4. Decrypt encrypted_value from secrets table

use anyhow::{Context as _, bail};

/// Placeholder — will implement in Sprint 1 when needed for Neo4j auth.
pub fn resolve_secret(_db_path: &std::path::Path, _secret_name: &str) -> anyhow::Result<String> {
    bail!("secret resolution not yet implemented")
}

/// Resolve $secret:NAME and ${VAR} patterns in a config value.
pub fn resolve_config_value(
    value: &str,
    _db_path: &std::path::Path,
) -> anyhow::Result<String> {
    // Pass through values without patterns
    if !value.contains("$secret:") && !value.contains("${") {
        return Ok(value.to_string());
    }

    // $secret:NAME pattern
    if let Some(name) = value.strip_prefix("$secret:") {
        return resolve_secret(_db_path, name);
    }

    // ${VAR} pattern — try env var
    if value.starts_with("${") && value.ends_with('}') {
        let var_name = &value[2..value.len() - 1];
        // Check for default: ${VAR:-default}
        if let Some((var, default)) = var_name.split_once(":-") {
            return Ok(std::env::var(var).unwrap_or_else(|_| default.to_string()));
        }
        return std::env::var(var_name)
            .with_context(|| format!("environment variable {var_name} not set"));
    }

    Ok(value.to_string())
}
