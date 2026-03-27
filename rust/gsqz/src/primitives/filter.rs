use regex::Regex;

/// Remove lines matching any of the given regex patterns.
pub fn filter_lines(lines: Vec<String>, patterns: &[String]) -> Vec<String> {
    if patterns.is_empty() {
        return lines;
    }

    let compiled: Vec<Regex> = patterns
        .iter()
        .filter_map(|p| Regex::new(p).ok())
        .collect();

    lines
        .into_iter()
        .filter(|line| !compiled.iter().any(|r| r.is_match(line)))
        .collect()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_filter_removes_matching() {
        let lines = vec![
            "keep this".into(),
            "  ".into(),
            "also keep".into(),
            "On branch main".into(),
        ];
        let patterns = vec![r"^\s*$".into(), r"^On branch ".into()];
        let result = filter_lines(lines, &patterns);
        assert_eq!(result, vec!["keep this", "also keep"]);
    }

    #[test]
    fn test_filter_empty_patterns() {
        let lines = vec!["a".into(), "b".into()];
        let result = filter_lines(lines, &[]);
        assert_eq!(result, vec!["a", "b"]);
    }
}
