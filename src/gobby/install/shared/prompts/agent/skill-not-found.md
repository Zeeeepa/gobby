---
name: agent/skill-not-found
description: Message when a requested skill is not found
version: "1.0"
required_variables: [skill_name]
optional_variables: [close_matches]
---
Skill '{{ skill_name }}' not found.
{% if close_matches %}

Did you mean:
{% for match in close_matches %}
  - `/gobby:{{ match }}`
{% endfor %}
{% endif %}

Run `/gobby` or `/gobby help` to see all available skills.
