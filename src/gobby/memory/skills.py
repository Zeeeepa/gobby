import json
import logging
import re

from gobby.config.app import SkillConfig
from gobby.llm.service import LLMService
from gobby.storage.messages import LocalMessageManager
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
        message_manager: LocalMessageManager,
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
            provider = self.llm_service.get_default_provider()
            model = self.config.learning_model

            prompt = self.config.prompt.format(transcript=transcript_text)

            response = await provider.generate_text(
                prompt=prompt,
                system_prompt="You are an expert at extracting reusable developer skills from transcripts.",
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

    async def match_skills(self, user_prompt: str, project_id: str | None = None) -> list[Skill]:
        """
        Find skills matching the user prompt via trigger patterns.

        Args:
            user_prompt: The user's input/request.
            project_id: Optional project context.

        Returns:
            List of matching skills.
        """
        if not self.config.auto_suggest:
            return []

        # Get all relevant skills (global + project)
        all_skills = self.storage.list_skills(project_id=project_id, limit=1000)

        matches = []
        for skill in all_skills:
            if not skill.trigger_pattern:
                continue

            try:
                # Case-insensitive match
                if re.search(skill.trigger_pattern, user_prompt, re.IGNORECASE):
                    matches.append(skill)
            except re.error:
                logger.warning(
                    f"Invalid regex pattern for skill {skill.id}: {skill.trigger_pattern}"
                )
                continue

        # Sort by usage/success
        matches.sort(key=lambda s: s.usage_count, reverse=True)

        return matches[: self.config.max_suggestions]

    async def record_usage(self, skill_id: str, success: bool = True) -> None:
        """
        Record that a skill was used.

        Args:
            skill_id: The ID of the skill used.
            success: Whether the skill application was successful.
        """
        try:
            # Increment usage count
            self.storage.increment_usage(skill_id)

            if not success:
                logger.debug(f"Recorded failed usage for skill {skill_id}")

        except Exception as e:
            logger.error(f"Error recording usage for skill {skill_id}: {e}")
