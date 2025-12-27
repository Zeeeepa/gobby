SKILL_EXTRACTION_PROMPT = """
Analyze the following session transcript and extract any reusable skills.
A "skill" is a repeatable process or pattern that can be used in future sessions.

Transcript:
{transcript}

Return a list of skills in JSON format:
[
  {{
    "name": "short-kebab-case-name",
    "description": "Brief description of what the skill does",
    "trigger_pattern": "regex|pattern|to|match",
    "instructions": "Markdown instructions on how to perform the skill",
    "tags": ["tag1", "tag2"]
  }}
]
"""
