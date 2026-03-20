import os
import json
import logging
from pathlib import Path
from gobby.sessions.transcripts.base import TranscriptParserErrorLog, ParsedMessage, BaseTranscriptParser
from gobby.sessions.transcript_renderer import render_transcript, RenderState
import pytest

def test_parser_error_log_creation(tmp_path):
    # Mock home directory for testing
    os.environ["HOME"] = str(tmp_path)
    
    cli_name = "test-cli"
    error_log = TranscriptParserErrorLog(cli_name)
    
    expected_path = tmp_path / ".gobby" / "logs" / f"{cli_name}-parser-error.log"
    assert error_log.log_path == expected_path
    
    # Trigger logging
    error_log.log_malformed_line(1, "session-1", '{"bad": "json"', "Unexpected EOF")
    
    assert expected_path.exists()
    content = expected_path.read_text()
    assert "line:1" in content
    assert "session:session-1" in content
    assert "Malformed line: Unexpected EOF" in content
    assert '{"bad": "json"' in content

def test_log_unknown_block(tmp_path):
    os.environ["HOME"] = str(tmp_path)
    cli_name = "test-cli-unknown"
    error_log = TranscriptParserErrorLog(cli_name)
    
    raw = {"type": "weird", "data": "value"}
    error_log.log_unknown_block(10, "session-2", "weird", raw)
    
    content = error_log.log_path.read_text()
    assert "line:10" in content
    assert "session:session-2" in content
    assert "Unknown block type: weird" in content
    assert json.dumps(raw) in content

def test_renderer_logs_unknown_block(tmp_path):
    os.environ["HOME"] = str(tmp_path)
    cli_name = "test-cli-renderer"
    error_log = TranscriptParserErrorLog(cli_name)
    
    # Mock a ParsedMessage with an unknown content_type
    from datetime import datetime
    msg = ParsedMessage(
        index=5,
        role="assistant",
        content="some content",
        content_type="magic_block",
        tool_name=None,
        tool_input=None,
        tool_result=None,
        timestamp=datetime.now(),
        raw_json={"type": "magic_block", "extra": "data"}
    )
    
    render_transcript([msg], session_id="session-3", error_log=error_log)
    
    content = error_log.log_path.read_text()
    assert "line:5" in content
    assert "session:session-3" in content
    assert "Unknown block type: magic_block" in content
    assert '"extra": "data"' in content

def test_parser_logs_malformed_line(tmp_path):
    os.environ["HOME"] = str(tmp_path)
    
    class MockParser(BaseTranscriptParser):
        def parse_line(self, line, index):
            try:
                return json.loads(line)
            except json.JSONDecodeError as e:
                self.error_log.log_malformed_line(index, self.session_id, line, str(e))
                return None

    parser = MockParser("mock-cli-malformed", session_id="session-4")
    parser.parse_line('{"valid": "json"}', 1)
    parser.parse_line('invalid json', 2)
    
    content = parser.error_log.log_path.read_text()
    assert "line:2" in content
    assert "session:session-4" in content
    assert "Malformed line" in content
    assert "invalid json" in content

def test_rotation(tmp_path):
    os.environ["HOME"] = str(tmp_path)
    cli_name = "test-cli-rotation"
    error_log = TranscriptParserErrorLog(cli_name)
    
    # We want to test rotation at 10MB, but creating 10MB of logs in a test is slow.
    # We can check if the handler is RotatingFileHandler with correct maxBytes.
    import logging
    from logging.handlers import RotatingFileHandler
    
    handler = error_log.logger.handlers[0]
    assert isinstance(handler, RotatingFileHandler)
    assert handler.baseFilename == str(error_log.log_path)
    assert handler.maxBytes == 10 * 1024 * 1024
    assert handler.backupCount == 5
