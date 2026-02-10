import json
import base64
import re
import os
from io import BytesIO
from typing import Any, Optional, Union
from datetime import datetime
import requests
from PIL import Image, ImageFile

import structlog
logger = structlog.get_logger(__name__)

from ..utils.interface import UniInterface
from ..agent import AutoAgent


class FunctionHubLocal(UniInterface):
    def __init__(self, agent: AutoAgent):
        super().__init__(agent)
        self._tag = 'fm.function_hub'
        self._retry = 3

        self.fm_api_url = self.agent.config.ruyix_url
        self.fm_api_key = self.agent.config.ruyix_key
        self.fm_name = self.agent.config.ruyix_fm_name

        self.gui_vlm_api_url = self.agent.config.ruyix_url
        self.gui_vlm_api_key = self.agent.config.ruyix_key
        self.gui_vlm_name = self.agent.config.ruyix_gui_vlm_name

        if self.agent.config.use_custom_fm:
            self.fm_api_url = self.agent.config.custom_fm_url
            self.fm_api_key = self.agent.config.custom_fm_key
            self.fm_name = self.agent.config.custom_fm_name
        if self.agent.config.use_custom_gui_vlm:
            self.gui_vlm_api_url = self.agent.config.custom_gui_vlm_url
            self.gui_vlm_api_key = self.agent.config.custom_gui_vlm_key
            self.gui_vlm_name = self.agent.config.custom_gui_vlm_name

        self.save_query_for_debug = self.agent.config.save_query_for_debug

    def call_func(self, func, params, **kwargs):
        logger.info(f'calling function {func}')
        if func == 'file_retrieve_step':
            return self.file_retrieve_step(params=params)
        if func == 'file_archive_step':
            return self.file_archive_step(params=params)
        if func == 'task_step':
            return self.task_step(params=params)
        if func == 'query_model_formatted':
            return self.query_model_formatted(params=params)
        if func == 'query_model':
            return self.query_model(params=params)
        if func == 'device_use_step':
            return self.device_use_step(params=params)
        logger.warning(f'unknown function: {func}')
        return None

    def _save_debug_query(self, api_name: str, prompt: str, response: str, special_content = ""):
        """
        Save model query prompt and response to a markdown file for debugging.

        Args:
            api_name: Name of the API being called
            prompt: The prompt sent to the model
            response: The response from the model
        """
        if not self.save_query_for_debug:
            return

        try:
            # Get temp directory from agent.file
            temp_dir = self.agent.file.agent_temp_dir
            if not temp_dir:
                logger.warning("agent_temp_dir not available, skipping debug save")
                return

            # Create temp directory if it doesn't exist
            os.makedirs(temp_dir, exist_ok=True)

            # Generate filename with API name and timestamp
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
            filename = f"{api_name}_{timestamp}.md"
            filepath = os.path.join(temp_dir, filename)

            # Format content as markdown
            content = f"""# Debug Query Log: {api_name}

**Timestamp:** {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}

## Prompt

```
{prompt}
```

## Response

{response}

## Special Content

{special_content}

"""

            # Write to file
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(content)

            logger.debug(f"Saved debug query to {filepath}")
        except Exception as e:
            logger.warning(f"Failed to save debug query: {e}")

    def _call_api(self, messages: list[dict], model_name=None, retry=3, api_name='api_call') -> Optional[Any]:
        if api_name in ['device_use_step']:
            api_url = self.gui_vlm_api_url
            api_key = self.gui_vlm_api_key
            api_model_name = self.gui_vlm_name
        else:
            api_url = self.fm_api_url
            api_key = self.fm_api_key
            api_model_name = self.fm_name
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}"
        }

        if model_name and model_name != 'default':
            api_model_name = model_name
        data = {
            "model": api_model_name,
            "messages": messages
        }

        if not retry:
            retry = self._retry

        for _ in range(retry):
            try:
                logger.debug(f"Calling model at {api_url}, model_name={api_model_name}")

                response = requests.post(
                    api_url,
                    headers=headers,
                    json=data,
                    timeout=120  # 2分钟超时
                )

                # 记录响应状态码和内容长度
                logger.debug(f"Response code: {response.status_code}, length: {len(response.text) if response.text else 0}")

                if response.status_code != 200:
                    logger.error(f"❌ API call failed: {response.status_code} - {response.text[:500] if response.text else '(empty)'}")
                    continue

                # 检查响应内容是否为空
                if not response.text or len(response.text.strip()) == 0:
                    logger.error(f"❌ API empty return {response}")
                    continue

                # 尝试解析 JSON
                try:
                    result = response.json()
                except json.JSONDecodeError as json_err:
                    logger.error(f"❌ API returns invalid JSON: {json_err}: {response.text[:200] if response.text else '(empty)'}")
                    continue

                # 解析返回结果
                if "choices" in result and len(result["choices"]) > 0:
                    content = result["choices"][0]["message"]["content"]
                    logger.debug(f"API returned: {content[:200] if content else '(empty)'}...")

                    # Save debug query if enabled
                    if self.save_query_for_debug:
                        prompt_text = json.dumps(messages, indent=2, ensure_ascii=False)
                        special_content = ''
                        if api_name == 'task_step':
                            special_content = messages[0]['content'][0]['text']
                        elif api_name == 'device_use_step':
                            # Extract the main prompt text (first text content)
                            if messages and 'content' in messages[0]:
                                for content_part in messages[0]['content']:
                                    if content_part.get('type') == 'text':
                                        special_content = content_part['text']
                                        break
                        self._save_debug_query(api_name, prompt_text, content, special_content=special_content)

                    return content
                else:
                    logger.error(f"❌ API unexpected return format: {str(result)[:200]}")
                    continue

            except requests.exceptions.Timeout as e:
                logger.error(f"❌ API timeout: {e}")
            except requests.exceptions.ConnectionError as conn_err:
                logger.error(f"❌ API connection error: {conn_err}")
            except Exception as e:
                logger.error(f"❌ API exception: {type(e).__name__}: {e}")

        logger.error(f"❌ {api_model_name} calling failed")
        return None
    
    # ==================== memory.retrieve API ====================
    def file_retrieve_step(self, params):
        index_content = params['index_content']
        context = params['context']  # List of text and images
        hint = params['hint']
        actions_and_results = params['actions_and_results']  # List of text and images
        current_view = params['current_view']  # List of text and images
        history_actions_and_results = params.get('history_actions_and_results', [])  # List of text and images
        language = params.get('language', 'en')  # Language for thoughts and messages

        # Extract text and medias using utility function
        actions_text, actions_medias = self._extract_text_and_medias(actions_and_results)
        history_text, history_medias = self._extract_text_and_medias(history_actions_and_results)
        context_text, context_medias = self._extract_text_and_medias(context)
        current_view_text, current_view_medias = self._extract_text_and_medias(current_view)

        # Language instruction
        language_instruction = ""
        if language == 'zh':
            language_instruction = "IMPORTANT: You must respond in Chinese (中文)."
        elif language == 'en':
            language_instruction = "IMPORTANT: You must respond in English."

        # Ask LLM to extract relevant information and suggest next files
        prompt = f"""
You are navigating an agent's memory system to retrieve information or answer queries based on the current context.

{language_instruction}

The agent's memory is organized as markdown files with links to each other. The overall guidelines for memory retrieval can be found in the following doc.

```
{index_content}
```

# History from previous memory operations
{history_text if history_text else '(No previous history)'}

# Current context
{context_text}

HINT: {hint}

# Already performed actions and results
{actions_text if actions_text else '(No previous actions)'}

# Current view (content from multiple file operations)
```
{current_view_text if current_view_text else '(No current view)'}
```

# Tasks
1. Extract or summarize any information from the current view that is relevant to the context.
2. Identify file operations (reading files and lines) that should be explored next.
3. Decide whether to continue searching or stop if no more information is needed.

# Response format
Your response should be a brief paragraph (<50 words, prefixed with "Thought:") describing the plan, followed by Python code that directly executes the operations. The code should set two variables: `inferred_results` (extracted/summarized information) and `next_operations` (list of file operations to perform). You can use standard python APIs and memory-specific operation APIs as follows:

- memory.read(file_path, line_start, line_end): read the memory file from line range [line_start, line_end]. For example, [0, 10] means the first 11 lines and [-10, -1] means the last 10 lines.
- memory.search(file_or_dir_path, text, line_limit=100): search the memory file(s) for given text. It will return the matched files and text lines.

Note: You should read/search at most 100 lines at a time to avoid context explosion.
Note: The code should not block the execution (e.g. using time.sleep APIs).

An example of response is:
Thought: To answer the question about Beijing, the image sent by Alice may be helpful. I need to read more conversations with Alice about Beijing, and also read the chat history with other contacts.
```python
# Extracted or summarized information as a list of text and images
inferred_results = [
    "Alice had sent me a photo of Beijing in October last year.",
    ("_media/20251014/beijing.png", None)  # Image reference
]

# Next operations to perform
next_operations = [
    memory.read('social/conversations/with_alice.md', 100, 200),
    memory.read('social/conversations/with_tim.md', 0, 100),
    memory.search('social/conversations/', 'Beijing')
]
```
"""
        # Collect all medias
        medias = []
        medias.extend(context_medias)
        medias.extend(actions_medias)
        medias.extend(current_view_medias)

        # Build messages list with text and images
        # Start with text content that may reference images by path
        content_parts = [{"type": "text", "text": prompt}]

        # Add images with both path and base64 content to help model map images to text references
        media_content_parts = self._organize_medias_as_content_parts(medias)
        if media_content_parts is not None:
            content_parts.extend(media_content_parts)

        messages = [{
            "role": "user",
            "content": content_parts
        }]

        # Query the API
        response = self._call_api(messages, api_name='file_retrieve_step')

        if not response:
            logger.error("Failed to get response from API")
            return None, None

        # Parse the thought and code from the response
        thought = None
        code = None

        # Extract Thought: section
        thought_match = re.search(r'Thought:\s*(.*?)(?=\n\s*```|$)', response, re.IGNORECASE | re.DOTALL)
        if thought_match:
            thought = thought_match.group(1).strip()

        # Extract Python code block
        code_match = re.search(r'```python\s*(.*?)```', response, re.DOTALL)
        if not code_match:
            # Try without python tag
            code_match = re.search(r'```\s*(.*?)```', response, re.DOTALL)

        if code_match:
            code = code_match.group(1).strip()

        if not thought or not code:
            logger.warning(f"Failed to parse response. Thought: {thought is not None}, Code: {code is not None}")
            logger.debug(f"Response content: {response[:500]}")

        return thought, code

    def _extract_text_and_medias(self, items):
        """
        Extract text and media from a list of mixed text and image items.

        Args:
            items: List containing strings and image tuples (path, base64)

        Returns:
            tuple: (text_string, media_list)
                - text_string: Combined text with image citations
                - media_list: List of image tuples (path, base64)
        """
        text_parts = []
        medias = []

        if items:
            for item in items:
                if isinstance(item, str):
                    text_parts.append(item)
                elif isinstance(item, tuple) and len(item) == 2:
                    # Image tuple (path, base64)
                    media_path, media_base64 = item
                    medias.append(item)
                    # Add citation to text
                    if media_path:
                        text_parts.append(f"[Image: {media_path}]")
                    else:
                        text_parts.append(f"[Image {len(medias)}]")

        text_string = '\n'.join(text_parts)
        return text_string, medias

    def _organize_medias_as_content_parts(self, medias):
        # Each element in the medias list is a tuple (file_path, file_base64)
        content_parts = []
        for media_path, media_base64 in medias:
            try:
                if media_base64:
                    # Use base64 directly from the dict (no conversion needed)
                    # Add path information as text to help model map image to text references
                    if media_path:
                        content_parts.append({
                            "type": "text",
                            "text": f"[Image: {media_path}]"
                        })
                    content_parts.append({
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/png;base64,{media_base64}"
                        }
                    })
            except Exception as e:
                logger.warning(f"Failed to process image: {e}")
        return content_parts


    # ==================== memory.memorize API ====================
    def file_archive_step(self, params):
        index_content = params['index_content']
        content = params['content']  # List of text and images
        hint = params['hint']
        actions_and_results = params['actions_and_results']  # List of text and images
        current_view = params['current_view']  # List of text and images
        history_actions_and_results = params.get('history_actions_and_results', [])  # List of text and images
        language = params.get('language', 'en')  # Language for thoughts and messages

        # Extract text and medias using utility function
        actions_text, actions_medias = self._extract_text_and_medias(actions_and_results)
        history_text, _ = self._extract_text_and_medias(history_actions_and_results)
        content_text, content_medias = self._extract_text_and_medias(content)
        current_view_text, current_view_medias = self._extract_text_and_medias(current_view)

        # Language instruction
        language_instruction = ""
        if language == 'zh':
            language_instruction = "IMPORTANT: You must respond in Chinese (中文)."
        elif language == 'en':
            language_instruction = "IMPORTANT: You must respond in English."

        # Ask LLM to plan memory edits and suggest next files to read
        # The memorization process also performs retrieval to better guide where and what to store
        prompt = f"""
You are navigating an agent's memory system to store new information relevant to the current content.

{language_instruction}

The agent's memory is organized as markdown files with links to each other. The overall guidelines for memory storage can be found in the following doc.

```
{index_content}
```

# History from previous memory operations
{history_text if history_text else '(No previous history)'}

# Content to memorize
{content_text}

HINT: {hint}

# Already performed actions and results
{actions_text if actions_text else '(No previous actions)'}

# Current view (content from multiple file operations)
```
{current_view_text if current_view_text else '(No current view)'}
```

# Tasks
1. Extract or summarize any information from the current view that is relevant to the content to memorize (retrieval step).
2. Determine what information from the content should be stored in the files shown in the current view or related files, guided by the retrieved information.
3. Identify file operations (reading files, searching, and memory edit operations) that should be performed next.
4. Decide whether to continue exploring files or if you have enough information to finalize the memory edits.

# Response format
Your response should be a brief paragraph (<50 words, prefixed with "Thought:") describing the plan, followed by Python code that directly executes the operations. The code should set two variables: `inferred_results` (extracted/summarized information from retrieval) and `next_operations` (list of operations including both read/search and memory edit operations). You can use standard python APIs and memory-specific operation APIs as follows:

- memory.read(file_path, line_start, line_end): read the memory file from line range [line_start, line_end]. For example, [0, 10] means the first 11 lines and [-10, -1] means the last 10 lines.
- memory.search(file_or_dir_path, text, line_limit=100): search the memory file(s) for given text. It will return the matched files and text lines.
- memory.create(file_path, content): create a new memory file with the given content.
- memory.append(file_path, content): append content to the end of a memory file. If the file doesn't exist, it will be created.
- memory.insert(file_path, insert_line, content): insert content at a specific line number in a memory file. Line numbers are 0-indexed.
- memory.delete(file_path): delete an entire memory file.
- memory.remove_lines(file_path, line_start, line_end): remove lines from line_start to line_end (inclusive) from a memory file.

Note: Memory edit operations (create, append, insert, delete, remove_lines) should be included in next_operations as code, not as strings.
Note: You should read/search at most 100 lines at a time to avoid context explosion.
Note: The code should not block the execution (e.g. using time.sleep APIs).

An example of response is:
Thought: I need to retrieve relevant information about Alice and Beijing to guide where to store the new message. Then I'll append the message to Alice's conversation file and update the knowledge base about Beijing.
```python
# Extracted or summarized information from current file (retrieval step) as a list of text and images
inferred_results = [
    "Alice had sent me a photo of Beijing in October last year. The conversation file with Alice contains travel discussions.",
    ("_media/20251014/beijing.png", None)  # Image reference
]

# Next operations include both read/search operations and memory edit operations
next_operations = [
    memory.read('social/conversations/with_alice.md', -20, -1),
    memory.search('knowledge/travel/', 'Beijing'),
    memory.append('social/conversations/with_alice.md', '2024-10-14 10:30: Alice sent a message about Beijing with a photo [beijing_photo](_media/20251014/beijing.png)'),
    memory.append('knowledge/travel/beijing.md', 'Beijing is a city that Alice mentioned in our conversations.')
]
```
"""
        # Collect all medias
        medias = []
        medias.extend(content_medias)
        medias.extend(actions_medias)
        medias.extend(current_view_medias)

        # Build messages list with text and images
        # Start with text content that may reference images by path
        content_parts = [{"type": "text", "text": prompt}]

        # Add images with both path and base64 content to help model map images to text references
        media_content_parts = self._organize_medias_as_content_parts(medias)
        if media_content_parts is not None:
            content_parts.extend(media_content_parts)

        messages = [{
            "role": "user",
            "content": content_parts
        }]

        # Query the API
        response = self._call_api(messages, api_name='file_archive_step')

        if not response:
            logger.error("Failed to get response from API")
            return None, None

        # Parse the thought and code from the response
        thought = None
        code = None

        # Extract Thought: section
        thought_match = re.search(r'Thought:\s*(.*?)(?=\n\s*```|$)', response, re.IGNORECASE | re.DOTALL)
        if thought_match:
            thought = thought_match.group(1).strip()

        # Extract Python code block
        code_match = re.search(r'```python\s*(.*?)```', response, re.DOTALL)
        if not code_match:
            # Try without python tag
            code_match = re.search(r'```\s*(.*?)```', response, re.DOTALL)

        if code_match:
            code = code_match.group(1).strip()

        if not thought or not code:
            logger.warning(f"Failed to parse response. Thought: {thought is not None}, Code: {code is not None}")
            logger.debug(f"Response content: {response[:500]}")

        return thought, code

    # ==================== query_model_formatted API ====================
    def query_model_formatted(self, params):
        """
        query the LLM with given context and question
        the LLM should return an answer
        """
        context = params.get('context', None)
        model_name = params.get('model_name', None)
        query = params['query']
        returns = params.get('returns', None)  # the description of return format

        # Import returns parser
        from mobileclaw.fm.returns_parser import ReturnsParser
        returns_parser = ReturnsParser(self.agent)

        # Get required values from returns specification
        required_values = returns_parser.get_returns(returns)
        example = returns_parser.generate_example(required_values)

        # Build return description
        return_str = ""
        for i, req in enumerate(required_values):
            return_str += f'The {i + 1}th item should be {req[0]}, its type should be {returns_parser.type_list_to_prompt(required_values[i][1])}\n'

        # Build the prompt
        prompt = f"""You are answering a question based on the provided context.

# Context
{context}

# Question
{query}

# Task
Answer the question based on the context provided above.

# Response Format
Your response should be in JSON format as a list. The list should contain {len(required_values)} item(s):
{return_str}

# Example Response Format
{example}

Please provide your answer in the exact JSON format shown above."""

        # Build messages
        messages = [
            {"role": "user", "content": prompt}
        ]

        # Call the API
        response = self._call_api(messages, model_name=model_name, api_name='query_model_formatted')

        if not response:
            logger.error("Failed to get response from API for query")
            return None

        # Parse the response
        data = returns_parser.parse_string_to_json(response)
        if data is None:
            logger.error("Failed to parse response as JSON")
            return None

        # Validate the parsed data
        usable, score = returns_parser.parse_json(data, required_values)

        if len(data) == 1:
            data = data[0]

        if not usable:
            # Try to fix common issues
            if type(data) is dict:
                data = list(data.values())
                usable, score = returns_parser.parse_json(data, required_values)
            elif type(data) is list and len(data) == 1:
                if type(data[0]) is list:
                    usable, score = returns_parser.parse_json(data[0], required_values)
                    if usable:
                        data = data[0]
                elif type(data[0]) is dict:
                    data = list(data[0].values())
                    usable, score = returns_parser.parse_json(data, required_values)

        if usable:
            return data
        else:
            logger.warning(f"Query response validation failed with score {score}")
            return data

    # ==================== query_model API ====================
    def query_model(self, params):
        """
        Query a foundation model with a query containing text and images.

        Args:
            params: dict with 'query' (str or list of text and images),
                    optional 'context' (str), and 'model_name' (str)

        Returns:
            str: Model response
        """
        query = params['query']
        context = params.get('context', None)
        model_name = params.get('model_name', None)

        # If context is provided, prepend it to the query
        if context:
            if isinstance(query, str):
                query = f"# Context\n{context}\n\n# Query\n{query}"
            elif isinstance(query, list):
                # Insert context at the beginning of the list
                query = [f"# Context\n{context}\n\n# Query\n"] + query

        # Extract text and medias from query
        prompt_text, prompt_medias = self._extract_text_and_medias(query)

        # Build content parts
        content_parts = [{"type": "text", "text": prompt_text}]

        # Add images if present
        media_content_parts = self._organize_medias_as_content_parts(prompt_medias)
        if media_content_parts:
            content_parts.extend(media_content_parts)

        # Build messages
        messages = [
            {"role": "user", "content": content_parts}
        ]

        # Call the API
        response = self._call_api(messages, model_name=model_name, api_name='query_model')

        if not response:
            logger.error("Failed to get response from API for query_model")
            return None

        return response

    # ==================== device_use_step API ====================
    def _get_device_actions_documentation(self, device_type: str) -> str:
        """Get device-specific action documentation for Python code generation"""

        # Common note-taking and result recording actions for all device types
        note_actions = """
### Note-Taking Actions (for recording progress information useful for future steps):
- `device.take_note(text)`: Record a text note about task progress
- `device.take_note_screenshot(description, bbox=(x1,y1,x2,y2))`: Record a screenshot note with description. bbox is the screen bounding box to capture. bbox=None means full screen.

### Result Recording Actions (for recording any relevant information requested by the task):
- `device.record_result(content)`: Record a task result (text). Only the recorded content and files will be returned to the task caller.
- `device.record_result_screenshot(description, bbox=(x1,y1,x2,y2))`: Record a screenshot of task result with description. bbox is the screen bounding box to capture. bbox=None means full screen."""

        if device_type == 'computer':
            return """### Computer Device Actions:
- `device.click(x, y)`: Click at coordinates (x, y)
- `device.double_click(x, y)`: Double-click at coordinates (x, y)
- `device.right_click(x, y)`: Right-click at coordinates (x, y)
- `device.view_set_text(content)`: Type text content
- `device.enter()`: Press Enter key
- `device.hotkey(keys)`: Press hotkey combination (e.g., 'ctrl c', 'cmd v')
- `device.scroll(direction, start_xy=(x, y))`: Scroll in direction ('up', 'down', 'left', 'right')
- `device.drag((x1, y1), (x2, y2))`: Drag from (x1, y1) to (x2, y2)
- `device.start_app(app_name)`: Start an application
- `device.back()`: Go back
- `device.home()`: Go to home
""" + note_actions

        elif device_type == 'phone':
            return """### Phone Device Actions:
- `device.click(x, y)`: Tap at coordinates (x, y)
- `device.long_click(x, y)`: Long press at coordinates (x, y)
- `device.view_set_text(content)`: Type text content
- `device.enter()`: Press Enter key
- `device.scroll(direction, start_xy=(x, y))`: Scroll in direction ('up', 'down', 'left', 'right')
- `device.drag((x1, y1), (x2, y2))`: Drag from (x1, y1) to (x2, y2)
- `device.start_app(app_name)`: Start an app
- `device.back()`: Press back button
- `device.home()`: Press home button
""" + note_actions

        elif device_type == 'browser':
            return """### Browser Device Actions:
- `device.click(x, y)`: Click at coordinates (x, y)
- `device.long_touch(x, y)`: Long press at coordinates (x, y)
- `device.view_set_text(content)`: Type text content
- `device.enter()`: Press Enter key
- `device.scroll(direction, start_xy=(x, y))`: Scroll in direction ('up', 'down', 'left', 'right')
- `device.drag((x1, y1), (x2, y2))`: Drag from (x1, y1) to (x2, y2)
- `device.open_url(url)`: Open URL in browser
- `device.back()`: Go back
- `device.home()`: Go to home page
""" + note_actions

        else:
            return ""

    def device_use_step(self, params):
        """
        Generate device-use steps using GUI_VLM.
        Similar to task_step but focused on device control with visual input.

        Args:
            params: dict with the following keys:
                - task: str - Task description
                - actions_and_results: list - Previous actions and their results (includes text notes and screenshot tuples)
                - device_type: str - 'computer', 'phone', or 'browser'
                - current_screen: str - Base64 encoded screenshot of current screen
                - images: list - List of image tuples (path, base64) from previous screenshots and noted images
                - language: str - 'zh' or 'en'
                - knowledge: str - Useful knowledge for doing the task
                - agent_info: str - Agent context information (profile, memory, etc.)

        Returns:
            tuple: (thought, code) - Thought string and Python code to execute
        """
        task = params['task']
        actions_and_results = params['actions_and_results']
        device_type = params['device_type']
        current_screen = params['current_screen']
        images = params.get('images', [])  # contains the screenshots from previous steps and images captured by device.take_note_screenshot()
        knowledge = params.get('knowledge', '')  # Useful knowledge for doing the task
        agent_info = params.get('agent_info', '')  # Agent context information

        # Extract text and medias using utility function
        # actions_text contains action history and notes
        # actions_medias contains history screenshots
        actions_text, actions_medias = self._extract_text_and_medias(actions_and_results)

        # Get device-specific action documentation
        device_actions_doc = self._get_device_actions_documentation(device_type)

        # Build prompt
        prompt = f"""You are helping control a {device_type} device to complete a task step by step.

# How to Control the Device

The task execution process follows an iterative manner. You generate a step (represented as a small piece of Python program) based on the current screenshot and situation, execute the step, observe the results, and decide the next steps. Each step should be one action based on the current screenshot.

If the same action does not lead to expected results for more than 3 times, try other ways to do the job.

## Device Control APIs

The following device control methods are available through the `device` object:

{device_actions_doc}

# The Current Task

## Agent Information
{agent_info}

## Task to Complete
{task}

## Task-related Knowledge
{knowledge if knowledge else '(No specific knowledge provided)'}

## Action History and Notes
{actions_text if actions_text else '(No previous actions)'}

## Your Response

You should analyze the current screenshot and situation based on actions already performed, then decide the next action to take toward completing the task.

Your response should be a brief paragraph (<50 words, prefixed with "Thought:") describing what you plan to do next, followed by Python code that executes an action.

The code will have access to:
- `device`: The device controller object with control methods

Note:
- Do not include comments in the code.
- One action at a time in your response.
- If and only if no more action is needed, output a line `task_status = 'finished'/'failed'/'infeasible'` to indicate whether the task has been completed. If task_status is in the output, it should be the only line in the code.

"""

        # Build messages with screenshot
        content_parts = [{"type": "text", "text": prompt}]

        # Collect all medias: action screenshots (history screenshots)
        all_medias = actions_medias + images

        # Add all media content parts
        media_content_parts = self._organize_medias_as_content_parts(all_medias)
        if media_content_parts:
            content_parts.extend(media_content_parts)

        # Add current screen screenshot
        content_parts.append({
            "type": "text",
            "text": f"[Current Screen]"
        })
        content_parts.append({
            "type": "image_url",
            "image_url": {
                "url": f"data:image/png;base64,{current_screen}"
            }
        })

        messages = [{"role": "user", "content": content_parts}]

        # Call API with special_content for debugging
        response = self._call_api(messages, api_name='device_use_step')

        if not response:
            logger.error("Failed to get response from API for device_use_step")
            return None, None

        # Parse thought and code (same as task_step)
        thought = None
        code = None

        thought_match = re.search(r'Thought:\s*(.*?)(?=\n\s*```|$)', response, re.IGNORECASE | re.DOTALL)
        if thought_match:
            thought = thought_match.group(1).strip()

        code_match = re.search(r'```python\s*(.*?)```', response, re.DOTALL)
        if not code_match:
            code_match = re.search(r'```\s*(.*?)```', response, re.DOTALL)

        if code_match:
            code = code_match.group(1).strip()

        if not thought or not code:
            logger.warning(f"Failed to parse response. Thought: {thought is not None}, Code: {code is not None}")
            logger.debug(f"Response content: {response[:500]}")

        return thought, code


    # ==================== task execution API ====================
    def task_step(self, params):
        """
        Generate a step for task execution.
        Similar to file_retrieve_step but for general task execution.
        """
        task = params['task']  # Task description string
        agent_info = params['agent_info']
        actions_and_results = params['actions_and_results']
        available_devices = params['available_devices']
        available_models = params['available_models']
        available_files = params['available_files']
        additional_context = params.get('additional_context', [])  # Additional context from previous task executions
        recursion_depth = params.get('recursion_depth', 0)  # Current recursion depth
        vars_preview = params.get('vars_preview', {})  # Dict mapping var names to preview strings
        knowledge = params.get('knowledge', '')  # Useful knowledge for doing the task
        mode = params.get('mode', 'normal')  # Execution mode: 'normal' or 'fast'

        # Extract text and medias using utility function
        actions_text, actions_medias = self._extract_text_and_medias(actions_and_results)
        additional_context_text, additional_context_medias = self._extract_text_and_medias(additional_context)

        # Format vars preview for display
        if vars_preview:
            vars_text = '\n\n'.join([f"{var_name}: {preview}" for var_name, preview in vars_preview.items()])
        else:
            vars_text = '(No other variables defined yet)'

        # Format available devices
        if available_devices:
            devices_text = '\n'.join([f"- {name}: {description}" for name, description in available_devices])
        else:
            devices_text = '(No devices configured)'

        # Format available models
        if available_models:
            models_text = '\n'.join([f"- {name}: {description}" for name, description in available_models])
        else:
            models_text = '(No models configured)'

        # Format available files (working directory structure)
        if available_files:
            files_text = available_files
        else:
            files_text = '(No working directory structure available)'

        # Mode-specific instructions
        mode_instruction = ""
        if mode == 'handle_message':
            mode_instruction = f"""
## IMPORTANT: You are in "Handle Message" Mode. The purpose of this mode is to handle incoming messages by:
1. Reading relevant memory and knowledge files to understand context
2. Updating memory and profile files with new conversation information.
3. This mode is not supposed for lengthy tasks with do_with_device or execute_task. If there is anything remaining to do with device, add it to the daily memory with "[PENDING]" prefix.
4. Generating appropriate responses and sending them using agent.send_message()

"""
        elif mode == 'conclude_task':
            mode_instruction = f"""
## IMPORTANT: You are operating in "Conclude Task" mode. The purpose of this mode is to save useful information from the completed task by:
1. Review the task execution history and results.
2. Extract key information, learnings, and outcomes.
3. Update relevant knowledge files (e.g., procedures, facts, contacts) and today's daily memory file if worth and haven't done so.
4. Send task results to the manager if worth and haven't done so. DO NOT send same message repetitively.
"""

        # Build API documentation based on mode
        # Exclude device and task decomposition APIs in handle_message and conclude_task modes
        api_docs = """
- Messaging
  - `agent.send_message(message, receiver=None, channel=None)`: send a message to the `receiver` via `channel`. `message` can be a string, an image/file (represented as file path). `receiver` is the name/id. `receiver=None` means sending to the manager. `channel=None` means sending to the default channel. This API is used for sending messages through internal channels. **DO NOT** send same/similar messages repetitively.

- AI model calling
  - `agent.query_model(params, model_name=None)`: query the foundation model. `query_params` is a list of query parameters (text, image, etc.). `model_name` specifies the preferred model to use in this query. The avaliable models can be found in `Available Models` section. This function returns the model response as a list of text and images.

- File/memory operations for text (markdown) files. Use these APIs to fetch and maintain knowledge/memory before and after each task. When creating new files, make sure the new file is created under the agent's personal dir:
  - `agent.file.read(file_path, line_start, line_end)`: read the working directory file from line range [line_start, line_end]. For example, [0, 10] means the first 11 lines and [-10, -1] means the last 10 lines.
  - `agent.file.search(file_or_dir_path, text, line_limit=100)`: search the working directory file(s) for given text. It will return the matched files and text lines.
  - `agent.file.write(file_path, content)`: write content to a working directory file. If the file doesn't exist, it will be created.
  - `agent.file.append(file_path, content)`: append content to the end of a working directory file. If the file doesn't exist, it will be created.
  - `agent.file.replace(file_path, match_text, replace_text)`: replace all occurrences of match_text with replace_text in a working directory file.
  - `agent.file.delete(file_path)`: delete an entire working directory file.
- File operations for general (non-markdown) files:
  - `agent.file.parse_file(file_path)`: parse a file to model-readable format. Supports various formats (doc, pdf, xlsx, pptx, etc.). Returns the parsed file content as a list of text and images.
  - `agent.file.generate_file(file_path, requirement, materials)`: generate a new file for human use based on given materials. `requirement` is text description of the file to generate. `materials` is a list of text and images.

- Note-taking and result recording
  - `agent.take_note(text)`: Record a text note about task progress. Use this for useful information that helps with future steps.
  - `agent.record_result(content)`: Record a text paragraph to the task results. Use this for results relevant to the task goal. Only the recorded content and files will be returned to the task caller.
  - `agent.record_result_file(file_path)`: Record a file to the task results."""

        if mode in ['normal']:
            api_docs = """
- Device use
  - `agent.do_with_device(task, knowledge, device)`: Execute a task on a device (phone/browser/desktop/...). `task` is a natural language description of what to do. `knowledge` is an optional text paragraph that may be useful for executing this task. `device` is the name/id of an available device. The avaliable devices can be found in `Available Devices` section. This function returns the information collected during task execution, which is a list of text and images.

- Task decomposition
  - `agent.execute_task(task, knowledge)`: Execute a subtask (for breaking down complex tasks into smaller ones). `knowledge` is an optional text paragraph that may be useful for executing this task.
""" + api_docs

        # Build prompt
        prompt = f"""You are helping an agent execute a task step by step.

# Overall guideline

The task execution process follows an iterative manner. The agent generates a step (represented as a small piece of Python program) based on the current situation, execute the step, observe the results, and decide the next steps. Each step should be one or few minimal actions that you are certain about based on the current situation.

The actions in each step are represented as Python program based on a set of domain-specific APIs designed for device use, LLM calling, user interaction, file operations, etc. Each step should be one action only.

If the task does not clearly specify what to do. Try generating a specific task based on profile jobs or system jobs.

## System Jobs

- If there is any missing information (marked with "?") in profile, ask the manager to complete them.
- Analyze pending tasks in memory and complete them if it is an appropriate time. The manager-requested tasks have highest priority.
- Every day before other tasks, summarize yesterday's memory and save important information into long-term memory.
- Compress the long-term memory or the daily memory if it is too long (e.g. >1000 words).

## Domain-Specific APIs
{api_docs}

## Available Devices
{devices_text}

## Available Models
{models_text}

## Available Files
The agent has access to a working directory with the following structure:
```
{files_text}
```

# The Current Task

## Agent Information
{agent_info}

## Task to Execute
{task}

{mode_instruction}

## Task-related Knowledge
{knowledge if knowledge else '(No specific knowledge provided)'}

## Previous Actions and Results
{actions_text if actions_text else '(No previous actions)'}

## Current Variables
```
{vars_text}
```

## Your Response

You need to decide the next action to take toward completing the task. You need to understand what and how to do (avoid duplicated tasks) based on memory, knowledge and action history.
Your response should be a brief paragraph (<50 words, prefixed with "Thought:") describing what you plan to do next, followed by Python code that executes the action.

The code will have access to:
- `agent`: The agent object with domain-specific APIs
- `vars`: A dict containing previous created variables. You can use the vars as API params.

Note: 
- Do not include comments in the code.
- Output only one action in your response.
- If and only if no more action is needed, output a line `task_status = 'finished'/'failed'/'infeasible'` to indicate whether the task has been completed. If task_status is in the output, it should be the only line in the code.

"""
        # Collect medias
        medias = []
        medias.extend(actions_medias)
        medias.extend(additional_context_medias)

        # Build messages
        content_parts = [{"type": "text", "text": prompt}]
        media_content_parts = self._organize_medias_as_content_parts(medias)
        if media_content_parts:
            content_parts.extend(media_content_parts)

        messages = [{"role": "user", "content": content_parts}]

        # Call API
        response = self._call_api(messages, api_name='task_step')

        if not response:
            logger.error("Failed to get response from API")
            return None, None

        # Parse thought and code (same as memory functions)
        thought = None
        code = None

        thought_match = re.search(r'Thought:\s*(.*?)(?=\n\s*```|$)', response, re.IGNORECASE | re.DOTALL)
        if thought_match:
            thought = thought_match.group(1).strip()

        code_match = re.search(r'```python\s*(.*?)```', response, re.DOTALL)
        if not code_match:
            code_match = re.search(r'```\s*(.*?)```', response, re.DOTALL)

        if code_match:
            code = code_match.group(1).strip()

        if not thought or not code:
            logger.warning(f"Failed to parse response. Thought: {thought is not None}, Code: {code is not None}")
            logger.debug(f"Response content: {response[:500]}")

        return thought, code

