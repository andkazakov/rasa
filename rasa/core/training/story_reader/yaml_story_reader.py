from pathlib import Path
from typing import Dict, Text, List, Any, Optional, Union, Tuple

import rasa.utils.common as common_utils
import rasa.utils.io
from rasa.constants import DOCS_URL_STORIES
from rasa.core.constants import INTENT_MESSAGE_PREFIX, RULE_SNIPPET_ACTION_NAME
from rasa.core.events import UserUttered, SlotSet, Form
from rasa.core.training.story_reader.story_reader import StoryReader
from rasa.core.training.structures import StoryStep
from rasa.data import YAML_FILE_EXTENSIONS

KEY_STORIES = "stories"
KEY_STORY_NAME = "story"
KEY_RULES = "rules"
KEY_RULE_NAME = "rule"
KEY_STEPS = "steps"
KEY_USER_UTTERANCE = "user"
KEY_ENTITIES = "entities"
KEY_SLOT_NAME = "slot"
KEY_SLOT_VALUE = "value"
KEY_FORM = "form"
KEY_ACTION = "action"
KEY_CHECKPOINT = "checkpoint"
KEY_CHECKPOINT_SLOTS = "slots"
KEY_METADATA = "metadata"
KEY_OR = "or"


class YAMLStoryReader(StoryReader):
    """Class that reads Core training data and rule data in YAML format"""

    async def read_from_file(self, filename: Text) -> List[StoryStep]:
        """Read stories or rules from file.

        Args:
            filename: Path to the story/rule file.

        Returns:
            `StoryStep`s read from `filename`.
        """
        try:
            yaml_content = rasa.utils.io.read_yaml_file(filename)
        except ValueError as e:
            common_utils.raise_warning(
                f"Failed to read YAML from '{filename}', it will be skipped. Error: {e}"
            )
            return []

        if not isinstance(yaml_content, dict):
            common_utils.raise_warning(
                f"Failed to read '{filename}'. It should be a YAML dictionary."
            )
            return []

        stories = yaml_content.get(KEY_STORIES, [])
        self._parse_stories(stories)

        rules = yaml_content.get(KEY_RULES, [])
        self._parse_rules(rules)

        self._add_current_stories_to_result()

        return self.story_steps

    def _parse_stories(self, stories: List[Dict[Text, Any]]) -> None:
        self._parse_items(
            stories,
            key=KEY_STORIES,
            docs=DOCS_URL_STORIES,
            item_key_name=KEY_STORY_NAME,
            is_rule_data=False,
        )

    def _parse_rules(self, rules: List[Dict[Text, Any]]) -> None:
        self._parse_items(
            rules,
            key=KEY_RULES,
            docs=DOCS_URL_STORIES,
            item_key_name=KEY_RULE_NAME,
            is_rule_data=True,
        )

    def _parse_items(
        self,
        items: List[Dict[Text, Any]],
        key: Text,
        docs: Text,
        item_key_name: Text,
        is_rule_data: bool,
    ) -> None:
        for item in items:
            if not isinstance(item, dict):
                common_utils.raise_warning(
                    f"Unexpected block found in '{self.source_name}':\n"
                    f"{item}\nItems under the '{key}' key must be YAML dictionaries. "
                    f"It will be skipped.",
                    docs=docs,
                )
                continue

            if item_key_name in item.keys():
                self._parse_plain_item(item, is_rule_data)

    def _parse_plain_item(self, item: Dict[Text, Any], is_rule_data: bool) -> None:
        item_name = item.get(self._get_item_title(is_rule_data), "")

        if not item_name:
            common_utils.raise_warning(
                f"Issue found in '{self.source_name}': \n"
                f"{item}\n"
                f"The {self._get_item_title(is_rule_data)} has an empty name. "
                f"{self._get_plural_item_title(is_rule_data).capitalize()} should "
                f"have a name defined under '{self._get_item_title(is_rule_data)}' "
                f"key. It will be skipped.",
                docs=self._get_docs_link(is_rule_data),
            )

        steps: List[Union[Text, Dict[Text, Any]]] = item.get(KEY_STEPS, [])

        if not steps:
            common_utils.raise_warning(
                f"Issue found in '{self.source_name}': "
                f"The {self._get_item_title(is_rule_data)} has no steps. "
                "It will be skipped.",
                docs=self._get_docs_link(is_rule_data),
            )
            return

        if is_rule_data:
            self._new_rule_part(item_name, self.source_name)
        else:
            self._new_story_part(item_name, self.source_name)

        for step in steps:
            self._parse_step(step, is_rule_data)

    def _parse_step(
        self, step: Union[Text, Dict[Text, Any]], is_rule_data: bool
    ) -> None:

        if step == RULE_SNIPPET_ACTION_NAME:
            self._parse_rule_snippet_action()
        elif isinstance(step, str):
            common_utils.raise_warning(
                f"Issue found in '{self.source_name}':\n"
                f"Found an unexpected step in the {self._get_item_title(is_rule_data)} "
                f"description:\n{step}\nThe step is of type `str` "
                f"which is only allowed for the rule snippet action "
                f"'{RULE_SNIPPET_ACTION_NAME}'. It will be skipped.",
                docs=self._get_docs_link(is_rule_data),
            )
        elif KEY_USER_UTTERANCE in step.keys():
            self._parse_user_utterance(step, is_rule_data)
        elif KEY_OR in step.keys():
            self._parse_or_statement(step, is_rule_data)
        elif KEY_SLOT_NAME in step.keys():
            self._parse_slot(step, is_rule_data)
        elif KEY_ACTION in step.keys():
            self._parse_action(step, is_rule_data)
        elif KEY_CHECKPOINT in step.keys():
            self._parse_checkpoint(step, is_rule_data)
        elif KEY_FORM in step.keys():
            self._parse_form(step[KEY_FORM])
        elif KEY_METADATA in step.keys():
            pass
        else:
            common_utils.raise_warning(
                f"Issue found in '{self.source_name}':\n"
                f"Found an unexpected step in the {self._get_item_title(is_rule_data)} "
                f"description:\n{step}\nIt will be skipped.",
                docs=self._get_docs_link(is_rule_data),
            )

    @staticmethod
    def _get_item_title(is_rule_data: bool) -> Text:
        return KEY_RULE_NAME if is_rule_data else KEY_STORY_NAME

    @staticmethod
    def _get_plural_item_title(is_rule_data: bool) -> Text:
        return KEY_RULES if is_rule_data else KEY_STORIES

    @staticmethod
    def _get_docs_link(is_rule_data: bool) -> Text:
        # TODO: update docs link to point to rules
        return "" if is_rule_data else DOCS_URL_STORIES

    def _parse_user_utterance(self, step: Dict[Text, Any], is_rule_data: bool) -> None:

        if self.use_e2e:
            # TODO
            return

        utterance = self._parse_raw_user_utterance(step, is_rule_data=is_rule_data)
        if utterance:
            self.current_step_builder.add_user_messages([utterance])

    def _parse_or_statement(self, step: Dict[Text, Any], is_rule_data: bool) -> None:
        utterances = []

        for utterance in step.get(KEY_OR):
            if KEY_USER_UTTERANCE in utterance.keys():
                utterance = self._parse_raw_user_utterance(utterance, is_rule_data)
                if utterance:
                    utterances.append(utterance)
            else:
                common_utils.raise_warning(
                    f"Issue found in '{self.source_name}': \n"
                    f"`OR` statement can only have '{KEY_USER_UTTERANCE}' "
                    f"as a sub-element. This step will be skipped:\n"
                    f"'{utterance}'\n",
                    docs=self._get_docs_link(is_rule_data),
                )
                return

        self.current_step_builder.add_user_messages(utterances)

    def _parse_raw_user_utterance(
        self, step: Dict[Text, Any], is_rule_data: bool
    ) -> Optional[UserUttered]:
        user_utterance = step.get(KEY_USER_UTTERANCE, "").strip()

        if not user_utterance:
            common_utils.raise_warning(
                f"Issue found in '{self.source_name}':\n"
                f"User utterance cannot be empty. "
                f"This {self._get_item_title(is_rule_data)} step will be skipped:\n"
                f"{step}",
                docs=self._get_docs_link(is_rule_data),
            )

        raw_entities = step.get(KEY_ENTITIES, [])
        final_entities = YAMLStoryReader._parse_raw_entities(raw_entities)

        if not user_utterance.startswith(INTENT_MESSAGE_PREFIX):
            common_utils.raise_warning(
                f"Issue found in '{self.source_name}':\n"
                f"User intent '{user_utterance}' should start with "
                f"'{INTENT_MESSAGE_PREFIX}'. "
                f"This {self._get_item_title(is_rule_data)} step will be skipped.",
                docs=self._get_docs_link(is_rule_data),
            )
            return None

        user_utterance = user_utterance[1:]

        intent = {"name": user_utterance, "confidence": 1.0}

        return UserUttered(user_utterance, intent, final_entities)

    @staticmethod
    def _parse_raw_entities(
        raw_entities: Union[List[Dict[Text, Text]], List[Text]]
    ) -> List[Dict[Text, Text]]:
        final_entities = []
        for entity in raw_entities:
            if isinstance(entity, dict):
                for key, value in entity.items():
                    final_entities.append({"entity": key, "value": value})
            else:
                final_entities.append({"entity": entity, "value": ""})

        return final_entities

    def _parse_slot(self, step: Dict[Text, Any], is_rule_data: bool) -> None:

        slot_name = step.get(KEY_SLOT_NAME, "")
        slot_value = step.get(KEY_SLOT_VALUE, "")

        if not slot_name or not slot_value:
            common_utils.raise_warning(
                f"Issue found in '{self.source_name}': \n"
                f"Slots should have a name and a value. "
                f"This {self._get_item_title(is_rule_data)} step will be skipped:\n"
                f"{step}",
                docs=self._get_docs_link(is_rule_data),
            )
            return

        self._add_event(SlotSet.type_name, {slot_name: slot_value})

    def _parse_action(self, step: Dict[Text, Any], is_rule_data: bool) -> None:

        action_name = step.get(KEY_ACTION, "")
        if not action_name:
            common_utils.raise_warning(
                f"Issue found in '{self.source_name}': \n"
                f"Action name cannot be empty. "
                f"This {self._get_item_title(is_rule_data)} step will be skipped:\n"
                f"{step}",
                docs=self._get_docs_link(is_rule_data),
            )
            return

        self._add_event(action_name, {})

    def _parse_rule_snippet_action(self) -> None:
        self._add_event(RULE_SNIPPET_ACTION_NAME, {})

    def _parse_form(self, form_name: Optional[Text]) -> None:
        self._add_event(Form.type_name, {"name": form_name})

    def _parse_checkpoint(self, step: Dict[Text, Any], is_rule_data: bool) -> None:

        checkpoint_name = step.get(KEY_CHECKPOINT, "")
        slots = step.get(KEY_CHECKPOINT_SLOTS, [])

        slots_dict = {}

        for slot in slots:
            if not isinstance(slot, dict):
                common_utils.raise_warning(
                    f"Issue found in '{self.source_name}':\n"
                    f"Checkpoint '{checkpoint_name}' has an invalid slot: "
                    f"{slots}\nItems under the '{KEY_CHECKPOINT_SLOTS}' key must be "
                    f"YAML dictionaries. The checkpoint will be skipped.",
                    docs=self._get_docs_link(is_rule_data),
                )
                return

            for key, value in slot.items():
                slots_dict[key] = value

        self._add_checkpoint(checkpoint_name, slots_dict)

    @staticmethod
    def is_yaml_story_file(file_path: Text) -> bool:
        """Check if file contains Core training data or rule data in YAML format.

        Args:
            file_path: Path of the file to check.

        Returns:
            `True` in case the file is a Core YAML training data or rule data file,
            `False` otherwise.
        """
        suffix = Path(file_path).suffix

        if suffix and suffix not in YAML_FILE_EXTENSIONS:
            return False

        try:
            content = rasa.utils.io.read_yaml_file(file_path)
            return any(key in content for key in [KEY_STORIES, KEY_RULES])
        except Exception as e:
            # Using broad `Exception` because yaml library is not exposing all Errors
            common_utils.raise_warning(
                f"Tried to check if '{file_path}' is a story or rule file, but failed "
                f"to read it. If this file contains story or rule data, you should "
                f"investigate this error, otherwise it is probably best to "
                f"move the file to a different location. Error: {e}"
            )
            return False
