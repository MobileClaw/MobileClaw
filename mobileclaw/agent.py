import time
import os
import copy
import queue
import threading
import random

import structlog
from typing import cast, Callable, Iterable, Any
from concurrent.futures import ThreadPoolExecutor, as_completed

from mobileclaw.config import AgentConfig

logger = structlog.get_logger(__name__)


class AutoAgent:
    def __init__(self, config: AgentConfig):
        self.config = config
        from . import device, fm, chat, file
        self.name = config.name
        self.org_name = config.org_name
        self.permission = getattr(self.config, 'permission', 'normal')

        self.device_manager = device.DeviceManager(self)
        self.fm = fm.FM_Interface(self)
        self.chat = chat.Chat_Interface(self)
        self.file = file.File_Interface(self)

        self.print_model_configuration()
        self._enabled = True
        self._idle_task_count = 0

        # Track current task execution stack (for nested tasks)
        self._current_task_stack = []  # List of (task, actions_and_results) tuples
        self.actions_and_results_max_len = 100  # TODO change this to a config

        # Message handling queue and synchronization
        self._message_queue = queue.Queue()
        self._message_handling_lock = threading.Lock()
        self._handling_message = False
        self._message_pause_event = threading.Event()
        self._message_pause_event.set()  # Initially not paused

        self.start()

    def start(self):
        self.fm._open()
        self.chat._open()
        self.file._open()

    def stop(self):
        self._enabled = False
        self.fm._close()
        self.chat._close()
        self.file._close()

    def _adaptive_sleep(self):
        """Adaptive sleep based on idle task count.
        Sleep time increases exponentially with consecutive idle tasks,
        up to a maximum of 10 minutes (600 seconds).
        """
        sleep_time = min(2 ** self._idle_task_count, 600)
        self._sleep(sleep_time)

    def serve(self):
        """
        Start agent serving.
        """
        while self._enabled:
            self.execute_task('Continue doing my job.')
            self._adaptive_sleep()

    def _log_and_report(self, content, actions_and_results, task_tag="📋"):
        """
        Helper method to append content to actions_and_results, log to log.md, and send to self.

        Args:
            content: Content to log and report
            actions_and_results: The actions_and_results list to append to
            task_tag: Emoji tag to prefix the content with
        """
        # Prefix content with task tag
        prefixed_content = f"{task_tag} {content}"

        # Append to actions_and_results
        actions_and_results.append(prefixed_content)

        # Append to log.md using file module
        try:
            from datetime import datetime
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            log_content = f"\n## {timestamp}\n{prefixed_content}\n"

            # Check if log.md exists, create with header if not
            full_log_path = self.file.get_log_path_today()

            if not os.path.exists(full_log_path):
                with open(full_log_path, 'w') as f:
                    # Create log.md with header
                    f.write("# Agent Log\n\n")

            # Append the content
            with open(full_log_path, 'a') as f:
                f.write(log_content)
        except Exception as e:
            logger.error(f"Failed to write to log.md: {e}")
            import traceback
            traceback.print_exc()

        # Send to self
        try:
            logger.info(prefixed_content)
            self.chat.send_to_log(prefixed_content)
        except Exception as e:
            logger.error(f"Error in send_to_log: {e}")

    def _conclude_task(self, task, actions_and_results, _recursion_depth=0):
        """
        Conclude a task by saving useful information to knowledge and memory files.
        This function is called at the end of execute_task and do_with_device.

        Args:
            task: The task description that was executed
            actions_and_results: List of actions taken and their results during execution

        Returns:
            None
        """
        try:
            # Create a summary of the task execution for the conclude_task mode
            task_summary = f"Review and save useful information from the following completed task:\n{task}"
            task_actions_results = copy.copy(actions_and_results)

            # Execute in conclude_task mode with limited steps
            logger.info(f"Concluding task: {task[:50]}...")
            self.execute_task(task=task_summary, actions_and_results=task_actions_results, mode='conclude_task', max_steps=10, _recursion_depth=_recursion_depth+1)

        except Exception as e:
            logger.warning(f"Error concluding task: {e}")
            # Don't fail the main task if conclusion fails

    def get_agent_info(self):
        """
        Gather agent context information including profile, memory, and basic info.

        Returns:
            str: Formatted string with agent profile and memory content
        """
        import os
        from datetime import datetime

        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # Read task guidelines from working directory
        profile_path = self.file.agent_profile_path
        profile_content = ""
        if os.path.exists(profile_path):
            with open(profile_path, 'r', encoding='utf-8') as f:
                profile_content = f.read()

        # Read today's memory
        memory_path_today = self.file.get_memory_path_today()
        memory_today_content = ""
        if os.path.exists(memory_path_today):
            with open(memory_path_today, 'r', encoding='utf-8') as f:
                memory_today_content = f.read()

        # Read long-term memory
        longterm_memory_path = os.path.join(self.file.agent_dir, 'long_term_memory.md')
        longterm_memory_content = ""
        if os.path.exists(longterm_memory_path):
            with open(longterm_memory_path, 'r', encoding='utf-8') as f:
                longterm_memory_content = f.read()

        # Get relative paths for display
        profile_path_rel = os.path.relpath(profile_path, self.file.org_dir)
        memory_path_today_rel = os.path.relpath(memory_path_today, self.file.org_dir)
        longterm_memory_path_rel = os.path.relpath(longterm_memory_path, self.file.org_dir)

        agent_info = f"""
- Current Time: {current_time}
- Organization: {self.org_name}
- Agent Name: {self.name}
- Agent Permission: {self.permission}
- Agent Profile ({profile_path_rel}):
```
{profile_content}
```
- Today's Memory ({memory_path_today_rel}):
```
{memory_today_content}
```
- Long-term Memory ({longterm_memory_path_rel}):
```
{longterm_memory_content}
```"""

        return agent_info

    def get_current_task_info(self):
        """
        Get information about the current ongoing task.

        Returns:
            tuple: (task, actions_and_results) or (None, []) if no task is running
        """
        if not self._current_task_stack:
            return (None, [])
        return self._current_task_stack[-1]  # Return the top of the stack

    def execute_task(self, task, knowledge='', actions_and_results=[], max_steps=30, _recursion_depth=0, mode='normal'):
        """
        Let the agent execute a task
        The execution process is a loop. At each step, let the model decide what actions to take next.

        Args:
            task: Task description
            knowledge: Useful knowledge for doing the task
            max_steps: Maximum number of steps to execute
            _recursion_depth: Internal parameter to track recursion depth (max 3 levels)
            mode: Execution mode. Supported modes:
                  - 'normal': Full functionality with all APIs available
                  - 'handle_message': Handle incoming messages with memory updates
                  - 'conclude_task': Save task information to knowledge and memory files
        """
        # Prevent infinite recursion
        if _recursion_depth >= 3:
            logger.warning(f"Maximum recursion depth reached for task: {task}")
            return [f"Error: Maximum recursion depth (3) reached. Cannot execute subtask: {task}"]

        # Generate a random emoji as task tag
        task_emojis = ['🔴', '🟠', '🟡', '🟢', '🔵', '🟣', '🟤', '⚫', '⚪',
                       '🟥', '🟧', '🟨', '🟩', '🟦', '🟪', '🟫', '⬛', '⬜',
                       '❤️', '🧡', '💛', '💚', '💙', '💜', '🤎', '🖤', '🤍']
        task_tag = random.choice(task_emojis)

        # Get agent context information
        agent_info = self.get_agent_info()

        # Get available devices and models
        available_devices = self.device_manager.get_available_devices()
        available_models = self.fm.get_available_models()

        # Get working directory structure
        available_files = self._get_working_dir_tree()

        # Initialize execution state
        actions_and_results = actions_and_results
        indent = "  " * _recursion_depth  # Indent for subtasks
        self._log_and_report(f'{indent}Start task: {task}', actions_and_results, task_tag)

        # Push task to stack for tracking
        self._current_task_stack.append((task, actions_and_results))

        try:
            # Initialize vars dict that persists across steps
            current_vars = {'actions_and_results': actions_and_results}
            agent_api = self._create_agent_api_for_execution(_recursion_depth, mode)

            # Track if task is idle (finished in step 0 with only task_status set)
            finished_step = -1

            for step in range(max_steps):
                # Pause normal tasks if a message is being handled
                if mode == 'normal':
                    self._message_pause_event.wait()

                # Create vars preview for display in prompt
                vars_preview = self._create_vars_preview(current_vars)

                if len(actions_and_results) > self.actions_and_results_max_len:
                    actions_and_results = actions_and_results[-self.actions_and_results_max_len:]
                # Prepare params for task_step
                params = {
                    'task': task,
                    'agent_info': agent_info,
                    'actions_and_results': actions_and_results,
                    'available_devices': available_devices,
                    'available_models': available_models,
                    'available_files': available_files,
                    'recursion_depth': _recursion_depth,
                    'vars_preview': vars_preview,
                    'knowledge': knowledge,
                    'mode': mode
                }

                # Call model to generate step code
                thought, code = self.fm.call_func('task_step', params)

                # Add thought to results
                if thought:
                    self._log_and_report(f'{indent}Step {step} Thought: {thought}', actions_and_results, task_tag)

                # Stop if no code generated
                if not code:
                    self._log_and_report(f'{indent}Step {step} Warning: No code parsed from the response. Perhaps forgot to wrap code in code block?', actions_and_results, task_tag)
                    continue

                self._log_and_report(f'{indent}Step {step} Action:\n```\n{code}\n```', actions_and_results, task_tag)
                logger.info(f"{indent}Step {step} Action:\n{code}")

                # Execute the code
                try:
                    # Update vars dict with current actions_and_results
                    current_vars['actions_and_results'] = actions_and_results

                    # Pass vars dict to the code
                    exec_globals = {
                        'agent': agent_api,
                        'vars': current_vars,
                        'task_status': 'ongoing'
                    }
                    exec(code, exec_globals)

                    # Update current_vars with any new variables created in the code
                    for key, value in exec_globals.items():
                        if key not in ['agent', 'task_status', '__builtins__', 'vars']:
                            current_vars[key] = value

                    task_status = exec_globals.get('task_status', 'ongoing')
                    if task_status != 'ongoing':
                        if task_status == 'finished':
                            finished_step = step
                        break

                except Exception as e:
                    err_msg = f"{indent}Error: step {step} was failed: {e}"
                    logger.error(err_msg)
                    self._log_and_report(err_msg, actions_and_results, task_tag)
                    continue # NOTE: decide between break or continue
            
            if step + 1 >= max_steps:
                self.agent._log_and_report(f'Task stopped due to step limit: {max_steps}. . You may need to start a new task to complete the remaining work.', actions_and_results, task_tag=task_tag)

            # Get results before concluding
            results = agent_api._results

            # Determine whether it is an idle task (finished within 1 step, no action executed)
            idle_flag = False
            if finished_step == 0:
                idle_flag = True
            # Update idle task count based on whether this task was idle
            if _recursion_depth == 0:
                if idle_flag:
                    self._idle_task_count += 1
                else:
                    self._idle_task_count = 0  # Reset counter on non-idle task

            # Conclude task by saving useful information (only for normal mode)
            if mode == 'normal' and not idle_flag: # and _recursion_depth == 0:
                self._conclude_task(task, actions_and_results, _recursion_depth=_recursion_depth)

            return results
        finally:
            # Pop task from stack
            if self._current_task_stack and self._current_task_stack[-1][0] == task:
                self._current_task_stack.pop()

    def handle_message(self, message, history, sender, channel):
        """
        Handle a new chat message with handle_message mode.
        This function is called when a new message arrives.
        Messages are processed sequentially - if a message is already being handled,
        this call will wait until the previous message is finished.

        Args:
            message: The incoming message. Can be a string, image/file path, or a list of them
            history: Recent previous messages in the conversation, represented as text
            sender: Who (name/id) sent this message
            channel: Through which the message was received
        """
        # Acquire lock to ensure only one message is handled at a time
        # If another message is being handled, this will wait
        with self._message_handling_lock:
            try:
                # Pause normal tasks while handling message
                self._message_pause_event.clear()
                self._handling_message = True

                message_content = str(message)
                history_content = str(history)

                # Get current task info
                current_task, current_task_actions = self.get_current_task_info()
                current_task_actions = copy.copy(current_task_actions)

                # Build task context section
                task_context = ""
                if current_task:
                    task_context = f"""
## Current Ongoing Task Context
The agent is currently working on the following task:
Task: {current_task}

"""

                # Format history content
                history_formatted = f"```\n{history_content}\n```" if history_content else '(No previous messages)'

                # Create task description that includes the message and history
                task_description = f"""Handle the following message from `{sender}`:
- Message: `{message_content}`
- Channel: `{channel}`
- Recent conversation:
{history_formatted}
{task_context}"""

                # Execute task directly in handle_message mode (for memory maintenance and response generation)
                logger.info(f"Handling message from {sender} via {channel}")
                results = self.execute_task(task_description, mode='handle_message', actions_and_results=current_task_actions)
                return results

            except Exception as e:
                logger.error(f"Error handling message: {e}")
                import traceback
                traceback.print_exc()
                return [f"Error: {str(e)}"]

            finally:
                # Resume normal tasks after handling message
                self._handling_message = False
                self._message_pause_event.set()
        
    def send_message(self, message, receiver, channel=None):
        """
        Send a message to receiver through channel.
        This API is used for messaging through the agent.chat module.
        For sending messages through other apps (wechat, etc.), use do_with_device function.

        Args:
            message: Can be a string, an image/file (represented as a path) or a list of them
            receiver: Name/id of the message receiver (can be a user or a group)
            channel: Channel through which to send the message (e.g., 'zulip')

        Returns:
            str: Confirmation message
        """
        logger.info(f"Sending message to {receiver} via {channel}")
        return self.chat.send_message(message, receiver, channel)

    def sleep(self, seconds: float):
        self._sleep(seconds)

    def _sleep(self, seconds: float):
        """Let the agent sleep for several seconds."""
        time.sleep(seconds)

    def _initialize_working_dir(self):
        """Initialize the working directory structure based on the template."""
        if hasattr(self, 'file') and self.file:
            self.file._initialize_working_dir()

    def _get_working_dir_tree(self, show_non_markdown=False) -> str:
        """Get a text description of the working directory tree.
        By default, only shows markdown files.

        Args:
            show_non_markdown: If True, also show non-markdown files
        Returns:
            str: Text description of the directory tree
        """
        if hasattr(self, 'file') and self.file:
            return self.file.get_working_dir_tree(show_non_markdown)
        return "(File interface not initialized)"

    def _create_vars_preview(self, vars_dict: dict, str_preview_len: int = 500, collection_preview_len: int = 100, preview_threshold: int = 10000) -> dict:
        """Create preview strings for variables to be displayed in prompts.

        Args:
            vars_dict: Dictionary of variable names to values
            str_preview_len: Maximum number of characters to show for string previews
            collection_preview_len: Maximum number of elements to show for collections
            preview_threshold: If len(str(value)) < preview_threshold, show the whole content
        Returns:
            dict: Dictionary mapping variable names to preview strings
        """
        def preview_value(value, depth=0, max_depth=2, indent_level=0, show_all=False):
            """Recursively create preview for a value."""
            # Prevent infinite recursion
            if depth > max_depth:
                return f"{type(value).__name__} object"

            # Determine effective limits based on show_all flag
            effective_str_len = preview_threshold if show_all else str_preview_len
            effective_collection_len = preview_threshold if show_all else collection_preview_len

            if isinstance(value, str):
                # Check if string has multiple lines
                lines = value.split('\n')
                if len(lines) > 1:
                    # Format multi-line strings like lists
                    num_lines_to_show = min(len(lines), int(effective_collection_len))
                    has_more = len(lines) > effective_collection_len

                    # Use multi-line format if more than 2 lines
                    if num_lines_to_show > 2 or has_more:
                        indent = "  " * (indent_level + 1)
                        preview_lines = ["\"\"\""]
                        for i, line in enumerate(lines[:int(effective_collection_len)]):
                            # Truncate each line if too long
                            if len(line) > effective_str_len:
                                remaining_chars = len(line) - int(effective_str_len)
                                line = line[:int(effective_str_len)] + f"... ({remaining_chars} more chars)"
                            preview_lines.append(f"{indent}{line}")
                        if has_more:
                            preview_lines.append(f"{indent}... ({len(lines) - int(effective_collection_len)} more lines)")
                        preview_lines.append("  " * indent_level + "\"\"\"")
                        return "\n".join(preview_lines)
                    else:
                        # Single-line format for 1-2 lines
                        preview_items = []
                        for line in lines[:int(effective_collection_len)]:
                            if len(line) > effective_str_len:
                                remaining_chars = len(line) - int(effective_str_len)
                                line = line[:int(effective_str_len)] + f"... ({remaining_chars} more chars)"
                            preview_items.append(line)
                        return f"'{chr(92)}n'.join([{', '.join([repr(l) for l in preview_items])}])"
                else:
                    # Single-line string
                    if len(value) > effective_str_len:
                        remaining_chars = len(value) - int(effective_str_len)
                        return f"'{value[:int(effective_str_len)]}... ({remaining_chars} more chars)'"
                    return f"'{value}'"

            elif isinstance(value, (int, float, bool)):
                return str(value)

            elif isinstance(value, list):
                if len(value) == 0:
                    return "[]"

                # Determine number of items to show
                num_items_to_show = min(len(value), int(effective_collection_len))
                has_more = len(value) > effective_collection_len

                # Use multi-line format if more than 2 items
                if num_items_to_show > 2 or has_more:
                    indent = "  " * (indent_level + 1)
                    preview_lines = ["["]
                    for i, item in enumerate(value[:int(effective_collection_len)]):
                        item_preview = preview_value(item, depth + 1, max_depth, indent_level + 1, show_all)
                        preview_lines.append(f"{indent}{item_preview},")
                    if has_more:
                        preview_lines.append(f"{indent}... ({len(value) - int(effective_collection_len)} more)")
                    preview_lines.append("  " * indent_level + "]")
                    return "\n".join(preview_lines)
                else:
                    # Single-line format for 1-2 items
                    preview_items = []
                    for item in value[:int(effective_collection_len)]:
                        preview_items.append(preview_value(item, depth + 1, max_depth, indent_level, show_all))
                    return f"[{', '.join(preview_items)}]"

            elif isinstance(value, tuple):
                if len(value) == 0:
                    return "()"

                # Determine number of items to show
                num_items_to_show = min(len(value), int(effective_collection_len))
                has_more = len(value) > effective_collection_len

                # Use multi-line format if more than 2 items
                if num_items_to_show > 2 or has_more:
                    indent = "  " * (indent_level + 1)
                    preview_lines = ["("]
                    for i, item in enumerate(value[:int(effective_collection_len)]):
                        item_preview = preview_value(item, depth + 1, max_depth, indent_level + 1, show_all)
                        preview_lines.append(f"{indent}{item_preview},")
                    if has_more:
                        preview_lines.append(f"{indent}... ({len(value) - int(effective_collection_len)} more)")
                    preview_lines.append("  " * indent_level + ")")
                    return "\n".join(preview_lines)
                else:
                    # Single-line format for 1-2 items
                    preview_items = []
                    for item in value[:int(effective_collection_len)]:
                        preview_items.append(preview_value(item, depth + 1, max_depth, indent_level, show_all))
                    return f"({', '.join(preview_items)})"

            elif isinstance(value, dict):
                if len(value) == 0:
                    return "{}"

                # Determine number of items to show
                num_items_to_show = min(len(value), int(effective_collection_len))
                has_more = len(value) > effective_collection_len

                # Use multi-line format if more than 2 items
                if num_items_to_show > 2 or has_more:
                    indent = "  " * (indent_level + 1)
                    preview_lines = ["{"]
                    for i, (k, v) in enumerate(list(value.items())[:int(effective_collection_len)]):
                        key_str = preview_value(k, depth + 1, max_depth, indent_level + 1, show_all)
                        val_str = preview_value(v, depth + 1, max_depth, indent_level + 1, show_all)
                        preview_lines.append(f"{indent}{key_str}: {val_str},")
                    if has_more:
                        preview_lines.append(f"{indent}... ({len(value) - int(effective_collection_len)} more)")
                    preview_lines.append("  " * indent_level + "}")
                    return "\n".join(preview_lines)
                else:
                    # Single-line format for 1-2 items
                    preview_items = []
                    for k, v in list(value.items())[:int(effective_collection_len)]:
                        key_str = preview_value(k, depth + 1, max_depth, indent_level, show_all)
                        val_str = preview_value(v, depth + 1, max_depth, indent_level, show_all)
                        preview_items.append(f"{key_str}: {val_str}")
                    return f"{{{', '.join(preview_items)}}}"

            else:
                return f"{type(value).__name__} object"

        vars_preview = {}
        for var_name, var_value in vars_dict.items():
            if var_name == 'actions_and_results':
                continue  # Skip actions_and_results as it's shown separately
            # Check if value is small enough to show completely
            show_all = len(str(var_value)) < preview_threshold
            vars_preview[var_name] = preview_value(var_value, show_all=show_all)

        return vars_preview

    def execute_on_device(self, func: Callable[[Any], Any], device: Any) -> Any:
        """Execute a given function on a single device.

        Args:
            func: A callable function that accepts a `device` parameter
            device: Device instance
        Returns:
            Any: Return value of `func(device)`
        """
        if not callable(func):
            raise TypeError("func must be callable")
        device_name = getattr(device, 'device_name', str(device))
        logger.debug(f"Executing function on device: {device_name}")
        return func(device)

    def execute_on_devices(self, func: Callable[[Any], Any], devices: Iterable[Any], parallel: bool = False) -> dict[str, Any]:
        """Execute a given function on multiple devices, either serially or in parallel.

        Args:
            func: A callable function that accepts a `device` parameter
            devices: Iterable of device instances
            parallel: If True, execute in parallel; otherwise execute serially
        Returns:
            dict[str, Any]: { device_name: return_value }
        """
        if not callable(func):
            raise TypeError("func must be callable")

        device_list = list(devices)
        results: dict[str, Any] = {}

        if not device_list:
            return results

        if not parallel:
            logger.debug("Executing function serially on multiple devices")
            for device in device_list:
                device_name = device.device_name
                results[device_name] = func(device)
            return results

        logger.debug("Executing function in parallel on multiple devices")
        with ThreadPoolExecutor(max_workers=len(device_list)) as executor:
            future_to_name = {}
            for device in device_list:
                device_name = device.device_name
                future = executor.submit(func, device)
                future_to_name[future] = device_name

            for future in as_completed(future_to_name):
                device_name = future_to_name[future]
                results[device_name] = future.result()

        return results

    def print_model_configuration(self):
        """Print model configuration information used in the execution script."""
        if getattr(self.config, 'use_ruyix_service', False):
            logger.info("✅ Using RuyiX service")
        if getattr(self.config, 'use_custom_fm', False):
            logger.info("✅ Using custom FM model")
        if getattr(self.config, 'use_custom_gui_vlm', False):
            logger.info("✅ Using custom GUI-VLM model")

    def get_current_task_line(self):
        """Get the current line number being executed in the task."""
        return None

    def get_task_execution_summary(self):
        """Get the execution summary of the current task."""
        return None

    # ==================== Domain-Specific APIs for Task Execution ====================
    # These APIs are used in generated Python code for task execution

    def do_with_device(self, task, knowledge='', device=None):
        """
        Execute a task on a device.
        # TODO pass exception to caller

        Args:
            task: Natural language description of what to do
            knowledge: Useful knowledge for doing the task
            device: The name/id of an available device

        Returns:
            list: Information collected during task execution (list of text notes and images)
        """
        device_obj = self.device_manager.get_device(device)
        if not device_obj:
            logger.error(f"Device not found: {device}")
            return [f"Error: Device '{device}' not found"]

        try:
            # Use device.execute_task to execute the instruction with knowledge
            results = device_obj.execute_task(task, knowledge=knowledge)
            return results
        except Exception as e:
            logger.error(f"Error executing instruction on device: {e}")
            return [f"Error: {str(e)}"]

    def query_model(self, params, model_name=None):
        """
        Query the foundation model.

        Args:
            params: List of query parameters (text, image, etc.)
            model_name: Specifies the preferred model to use in this query

        Returns:
            list: Model response as a list of text and images
        """
        # Convert params to appropriate format for fm interface
        if isinstance(params, str):
            params = [params]

        try:
            # Use the query_model function from function_hub_local
            response = self.fm.call_func('query_model', {
                'query': params,
                'model_name': model_name or 'default'
            })

            if response is None:
                return ["Error: No response from model"]

            return [response] if isinstance(response, str) else response
        except Exception as e:
            logger.error(f"Error querying model: {e}")
            return [f"Error: {str(e)}"]

    def _create_agent_api_for_execution(self, recursion_depth=0, mode='normal'):
        """
        Create an agent API object for task execution.
        Similar to MemoryAPI in memory system.

        Args:
            recursion_depth: Current recursion depth for nested tasks
            mode: Execution mode ('normal', 'handle_message', 'conclude_task')
        """
        class FileAPI:
            """File operations API for task execution."""
            def __init__(self, file_interface):
                self._file = file_interface

            def read(self, file_path, line_start, line_end):
                return self._file.read(file_path, line_start, line_end)

            def search(self, file_or_dir_path, text, line_limit=100):
                return self._file.search(file_or_dir_path, text, line_limit)

            def write(self, file_path, content):
                return self._file.write(file_path, content)

            def append(self, file_path, content):
                return self._file.append(file_path, content)

            def insert(self, file_path, insert_line, content):
                return self._file.insert(file_path, insert_line, content)

            def replace(self, file_path, match_text, replace_text):
                return self._file.replace(file_path, match_text, replace_text)

            def delete(self, file_path):
                return self._file.delete(file_path)

            def remove_lines(self, file_path, line_start, line_end):
                return self._file.remove_lines(file_path, line_start, line_end)

            def parse_file(self, file_path):
                return self._file.parse_file(file_path)

            def generate_file(self, file_path, requirement, materials):
                return self._file.generate_file(file_path, requirement, materials)

        class AgentAPI:
            def __init__(self, agent, recursion_depth, mode):
                self._agent = agent
                self._recursion_depth = recursion_depth
                self._mode = mode
                self._notes = []  # Store notes for task progress
                self._results = []  # Store task results
                # Expose file operations through agent.file
                self.file = FileAPI(agent.file)

            def do_with_device(self, task, knowledge='', device=None):
                # Check if mode allows device operations
                if self._mode in ['handle_message', 'conclude_task']:
                    raise Exception(f"do_with_device is not allowed in {self._mode} mode.")

                result = self._agent.do_with_device(task, knowledge, device)
                return result

            def query_model(self, params, model_name=None):
                result = self._agent.query_model(params, model_name)
                return result

            def execute_task(self, task, knowledge='', max_steps=20):
                """
                Execute a subtask. This allows breaking down complex tasks into smaller ones.

                Args:
                    task: Task description
                    knowledge: Useful knowledge for doing the task
                    max_steps: Maximum number of steps for the subtask

                Returns:
                    list: Results from subtask execution
                """
                # Check if mode allows task execution
                if self._mode in ['handle_message', 'conclude_task']:
                    raise Exception(f"execute_task is not allowed in {self._mode} mode.")

                result = self._agent.execute_task(task, knowledge, max_steps, _recursion_depth=self._recursion_depth + 1)
                return result

            def take_note(self, text):
                """
                Record a text note about task progress.
                Use this for information that helps with future steps.

                Args:
                    text: Note text to record

                Returns:
                    str: Confirmation message
                """
                self._notes.append(text)
                return f"Note recorded: {text}"

            def record_result(self, content):
                """
                Record a task result.
                Use this for final results relevant to the task goal.

                Args:
                    content: Result content to record

                Returns:
                    str: Confirmation message
                """
                self._results.append(content)
                return f"Result recorded: {content}"

            def send_message(self, message, receiver=None, channel=None):
                """
                Send a message to receiver through channel.

                Args:
                    message: Message content (string, image/file path, or list)
                    receiver: Name/id of the message receiver
                    channel: Channel to send through (e.g., 'wechat', 'API')

                Returns:
                    str: Confirmation message
                """
                result = self._agent.send_message(message, receiver, channel)
                return result

            def handle_message(self, message, history, sender, channel):
                """
                Handle a received message.

                Args:
                    message: Incoming message content
                    history: Recent conversation history
                    sender: Who sent the message
                    channel: Channel the message came from

                Returns:
                    list: Results from message handling
                """
                result = self._agent.handle_message(message, history, sender, channel)
                return result

        return AgentAPI(self, recursion_depth, mode)

