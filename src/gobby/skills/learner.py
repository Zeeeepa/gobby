import collections
import json
import logging

from gobby.config.app import SkillConfig
from gobby.llm.service import LLMService
from gobby.storage.session_messages import LocalSessionMessageManager
from gobby.storage.sessions import Session
from gobby.storage.skills import LocalSkillManager, Skill

logger = logging.getLogger(__name__)


class SkillLearner:
    """
    Learns and retrieves skills for Gobby.
    """

    def __init__(
        self,
        storage: LocalSkillManager,
        message_manager: LocalSessionMessageManager,
        llm_service: LLMService,
        config: SkillConfig,
    ):
        self.storage = storage
        self.message_manager = message_manager
        self.llm_service = llm_service
        self.config = config

    async def learn_from_session(self, session: Session) -> list[Skill]:
        """
        Extract skills from a completed session.

        Args:
            session: The session to analyze.

        Returns:
            List of newly created skills.
        """
        if not self.config.enabled:
            return []

        try:
            # Fetch session messages
            messages = await self.message_manager.get_messages(session.id)

            # Heuristic: only learn from sessions with sufficient activity
            if len(messages) < 4:
                return []

            # Format transcript for extraction
            # Assuming message works like dict based on get_messages return type
            transcript_text = "\n".join([f"{msg['role']}: {msg['content']}" for msg in messages])

            # Get provider for skill learning
            provider, model, _ = self.llm_service.get_provider_for_feature(self.config)

            # Enhanced prompt with strict quality criteria
            base_prompt = self.config.prompt
            exclusion_criteria = """
CRITICAL QUALITY FILTER:
You must ONLY extract a skill if it represents a HIGH-VALUE, REUSABLE CAPABILITY.
REJECT the following (return empty list):
- Specific bug fixes (e.g., "Fix mypy error in file X")
- One-off refactors
- Basic logic (e.g., "How to use a loop")
- Project-specific tweaks

A valid skill must be:
1. GENERALIZABLE: Applicable to any Python project or the general agent architecture.
2. PROCEDURAL: A series of steps, not just a snippet.
3. WORTH KEEPING: Something you would want to look up 6 months from now.
"""
            prompt_subs = collections.defaultdict(lambda: "", {"transcript": transcript_text})
            full_prompt = f"{exclusion_criteria}\n\n{base_prompt}".format_map(prompt_subs)

            response = await provider.generate_text(
                prompt=full_prompt,
                model=model,
            )

            # Parse JSON response
            cleaned_response = response.strip()
            if cleaned_response.startswith("```json"):
                cleaned_response = cleaned_response[7:]
            if cleaned_response.endswith("```"):
                cleaned_response = cleaned_response[:-3]

            cleaned_response = cleaned_response.strip()

            try:
                skills_data = json.loads(cleaned_response)
            except json.JSONDecodeError:
                logger.warning(f"Failed to parse skill extraction JSON for session {session.id}")
                return []

            # Check if returns a list
            if not isinstance(skills_data, list):
                logger.warning(f"Skill extraction returned non-list for session {session.id}")
                return []

            new_skills = []
            for skill_data in skills_data:
                # Basic validation
                if not all(k in skill_data for k in ["name", "instructions"]):
                    continue

                try:
                    skill = self.storage.create_skill(
                        name=skill_data["name"],
                        instructions=skill_data["instructions"],
                        description=skill_data.get("description"),
                        trigger_pattern=skill_data.get("trigger_pattern"),
                        source_session_id=session.id,
                        tags=skill_data.get("tags"),
                        project_id=session.project_id,
                    )
                    new_skills.append(skill)
                    logger.info(f"Learned new skill: {skill.name} ({skill.id})")
                except Exception as e:
                    logger.error(f"Error creating skill {skill_data.get('name')}: {e}")

            return new_skills

        except Exception as e:
            logger.error(f"Error learning skills from session {session.id}: {e}")
            return []
