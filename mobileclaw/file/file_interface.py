"""
The interfaces to manage agent working directory stored as markdown files.
Implements permission system based on member roles.
"""
import os
import threading
import importlib.resources as pkg_resources
from mobileclaw import resources
from mobileclaw.utils.interface import UniInterface
from mobileclaw.file.text_file import TextFile
import structlog


class FileException(Exception):
    """Base exception for file operations."""
    pass


class FilePermissionError(FileException):
    """Exception raised when file operation is denied due to permissions."""
    pass


class File_Interface(UniInterface):
    def __init__(self, agent):
        super().__init__(agent)
        from mobileclaw.agent import AutoAgent
        assert isinstance(agent, AutoAgent)
        # Compute working directory as {root_dir}/{org_name}
        self.org_file_name = self._get_parsed_name(agent.org_name)
        self.agent_file_name = self._get_parsed_name(agent.name)
        self.agent_permission = agent.permission
        self.org_dir = os.path.join(agent.config.root_dir, self.org_file_name)
        self.agent_dir = os.path.join(self.org_dir, self.agent_file_name)
        self.agent_temp_dir = os.path.join(self.agent_dir, '_temp')
        self.agent_log_dir = os.path.join(self.agent_dir, '_logs')
        self.agent_memory_dir = os.path.join(self.agent_dir, 'daily_memory')
        self.agent_profile_path = os.path.join(self.agent_dir, 'profile.md')
        self._tag = 'file'
        # Cache for embeddings: {file_path: (mtime, embedding)}
        self._embedding_cache = {}
        self._embedding_cache_path = os.path.join(self.org_dir, '.embedding_cache.json')
        self._load_embedding_cache()

        # File locks for concurrent write protection
        self._file_locks = {}  # {file_path: Lock}
        self._locks_lock = threading.Lock()  # Lock for the locks dictionary itself

    def _get_file_lock(self, file_path: str) -> threading.Lock:
        """
        Get or create a lock for a specific file path.

        Args:
            file_path: Absolute path to the file

        Returns:
            threading.Lock: Lock object for the file
        """
        with self._locks_lock:
            if file_path not in self._file_locks:
                self._file_locks[file_path] = threading.Lock()
            return self._file_locks[file_path]

    def get_log_path_today(self):
        """
        Return a date-named log file path under the _logs dir.
        If it is a new file, write a header into the file.

        Returns:
            str: Absolute path to today's log file
        """
        from datetime import datetime

        # Ensure the _logs directory exists
        os.makedirs(self.agent_log_dir, exist_ok=True)

        # Get today's date in YYYY-MM-DD format
        today = datetime.now().strftime("%Y-%m-%d")
        log_filename = f"log_{today}.md"
        log_path = os.path.join(self.agent_log_dir, log_filename)

        # If the file doesn't exist, create it with a header
        if not os.path.exists(log_path):
            lock = self._get_file_lock(log_path)
            with lock:
                # Double-check after acquiring lock
                if not os.path.exists(log_path):
                    header = f"# Log for {today}\n\n"
                    with open(log_path, 'w', encoding='utf-8') as f:
                        f.write(header)

        # Return absolute path
        return log_path
    
    def get_memory_path_today(self):
        """
        Return a date-named memory file path under the _memory dir.
        If it is a new file, write a header into the file.

        Returns:
            str: Absolute path to today's memory file
        """
        from datetime import datetime

        # Ensure the _memory directory exists
        os.makedirs(self.agent_memory_dir, exist_ok=True)

        # Get today's date in YYYY-MM-DD format
        today = datetime.now().strftime("%Y-%m-%d")
        memory_filename = f"memory_{today}.md"
        memory_path = os.path.join(self.agent_memory_dir, memory_filename)

        # If the file doesn't exist, create it with a header
        if not os.path.exists(memory_path):
            lock = self._get_file_lock(memory_path)
            with lock:
                # Double-check after acquiring lock
                if not os.path.exists(memory_path):
                    header = f"# Memory for {today}\n\n"
                    with open(memory_path, 'w', encoding='utf-8') as f:
                        f.write(header)

        # Return absolute path
        return memory_path

    def _get_parsed_name(self, name):
        # Convert a name to a valid file name
        return name.replace(' ', '_').replace('-', '_')

    def __str__(self) -> str:
        return "file"

    def _open(self):
        if self.org_dir:
            # Ensure working directory exists
            os.makedirs(self.org_dir, exist_ok=True)
            self._initialize_working_dir()

    def _close(self):
        pass

    def _query_fm(self, *args, returns=None):
        """
        A wrapper of fm. This file system uses fm calls to navigate the file structure.
        """
        vlm = self.agent.fm.vlm
        return vlm(*args, returns=returns)

    def _initialize_working_dir(self):
        """
        Initialize the working directory structure based on the structure in `resources/working_dir_template`.
        If the structure already exists, don't overwrite.
        """
        from pathlib import Path

        # Get the template directory path using pkg_resources
        template_dir = pkg_resources.files(resources).joinpath('working_dir_template')

        if not template_dir.is_dir():
            print(f"Warning: Working dir template directory not found at {template_dir}")
            return

        # Copy template structure to working directory
        working_path = Path(self.org_dir)

        # Walk through template directory and copy files that don't exist
        def copy_template_files(src_dir, dst_dir):
            """Recursively copy template files to destination"""
            for item in src_dir.iterdir():
                if item.is_file():
                    # Calculate relative path and target file
                    target_file = dst_dir / item.name
                    # Only copy if target doesn't exist
                    if not target_file.exists():
                        target_file.parent.mkdir(parents=True, exist_ok=True)
                        with item.open('rb') as src_f:
                            with open(target_file, 'wb') as dst_f:
                                dst_f.write(src_f.read())
                elif item.is_dir():
                    # Recursively copy subdirectories
                    copy_template_files(item, dst_dir / item.name)

        copy_template_files(template_dir, working_path)

        # Ensure the agent's directory exists with the same structure as sample_member
        agent_dir = working_path / self.agent_file_name
        sample_member_dir = template_dir / 'sample_member'

        if sample_member_dir.is_dir() and not agent_dir.exists():
            # Copy sample_member structure to agent's directory
            copy_template_files(sample_member_dir, agent_dir)

    def _check_permission(self, file_path: str, operation: str) -> bool:
        """
        Check if the current member has permission to perform the operation on the file.

        Permission rules:
        - All members can read the whole directory
        - Members with "manager" permission can write org_shared/files and org_shared/knowledge
        - Normal members can only write their own directory
        - No one should write log files (maintained automatically)

        :param file_path: Relative or absolute file path
        :param operation: 'read' or 'write'
        :return: True if permission granted, False otherwise
        """
        # Normalize file path
        if not os.path.isabs(file_path):
            file_path = os.path.join(self.org_dir, file_path)

        rel_path = os.path.relpath(file_path, self.org_dir)

        # All members can read
        if operation == 'read':
            return True

        if rel_path.endswith('log.md') or '/_logs/' in rel_path:
            return False

        # Check write permissions
        if operation == 'write':
            # Managers can write to org_shared/files and org_shared/knowledge
            if self.agent_permission == 'manager':
                if rel_path.startswith('org_shared/files') or rel_path.startswith('org_shared/knowledge'):
                    return True

            # All members can write to their own directory
            if rel_path.startswith(f'{self.agent_file_name}/'):
                return True

            # Otherwise, no permission
            return False

        return False

    def _load_embedding_cache(self):
        """Load embedding cache from file."""
        import json
        if os.path.exists(self._embedding_cache_path):
            try:
                with open(self._embedding_cache_path, 'r', encoding='utf-8') as f:
                    cache_data = json.load(f)
                    # Convert to proper format: {file_path: (mtime, embedding)}
                    self._embedding_cache = {
                        k: (v['mtime'], v['embedding'])
                        for k, v in cache_data.items()
                    }
                logger = structlog.get_logger(__name__)
                logger.debug(f"Loaded {len(self._embedding_cache)} embeddings from cache")
            except Exception as e:
                logger = structlog.get_logger(__name__)
                logger.warning(f"Failed to load embedding cache: {e}")
                self._embedding_cache = {}

    def _save_embedding_cache(self):
        """Save embedding cache to file."""
        import json
        try:
            # Convert to JSON-serializable format
            cache_data = {
                k: {'mtime': v[0], 'embedding': v[1]}
                for k, v in self._embedding_cache.items()
            }
            with open(self._embedding_cache_path, 'w', encoding='utf-8') as f:
                json.dump(cache_data, f)
        except Exception as e:
            logger = structlog.get_logger(__name__)
            logger.warning(f"Failed to save embedding cache: {e}")

    def get_working_dir_tree(self, show_others=False, show_non_markdown=False, exclude=['_temp', '_logs']) -> str:
        """
        Get a text description of the working directory tree.
        By default, only shows markdown files.

        :param show_others: If True, also show other member's files
        :param show_non_markdown: If True, also show non-markdown files
        :param exclude: List of directory/file names to exclude from the tree
        :return: Text description of the directory tree
        """
        from pathlib import Path

        working_path = Path(self.org_dir)
        if not working_path.exists():
            return "(Working directory not initialized)"

        lines = []
        # Display just the directory name instead of absolute path
        lines.append(f"Working Directory: {working_path.name}")

        def build_tree(path, prefix="", is_last=True, is_root=False):
            """Recursively build tree structure"""
            items = sorted(path.iterdir(), key=lambda x: (not x.is_dir(), x.name))

            # Filter out excluded directories/files
            if exclude:
                items = [item for item in items if item.name not in exclude]

            # Filter out non-markdown files if needed
            if not show_non_markdown:
                items = [item for item in items if item.is_dir() or item.suffix == '.md']

            # Filter out other members' directories if show_others=False and we're at root level
            if is_root and not show_others:
                filtered_items = []
                for item in items:
                    # Always include org_shared directory
                    if item.name == 'org_shared':
                        filtered_items.append(item)
                    # Always include current member's directory
                    elif item.name == self.agent_file_name:
                        filtered_items.append(item)
                    # Include non-directory items (files at root level)
                    elif not item.is_dir():
                        filtered_items.append(item)
                    # Skip other member directories
                items = filtered_items

            for idx, item in enumerate(items):
                is_last_item = (idx == len(items) - 1)
                connector = "└── " if is_last_item else "├── "

                # For files, add introduction (first line, truncated to <50 chars)
                if item.is_file():
                    intro = ""
                    try:
                        with open(item, 'r', encoding='utf-8') as f:
                            first_line = f.readline().strip()
                            if first_line:
                                # Truncate to <50 chars
                                if len(first_line) > 49:
                                    intro = f" \t- {first_line[:49]}..."
                                else:
                                    intro = f" \t- {first_line}"
                    except Exception:
                        # If we can't read the file, just skip the intro
                        pass
                    lines.append(f"{prefix}{connector}{item.name}{intro}")
                else:
                    lines.append(f"{prefix}{connector}{item.name}")

                if item.is_dir():
                    extension = "    " if is_last_item else "│   "
                    build_tree(item, prefix + extension, is_last_item, is_root=False)

        build_tree(working_path, is_root=True)
        return "\n".join(lines)

    # ==================== File Operation APIs ====================
    # These APIs are used in the code generated by file operation steps

    def read(self, file_path: str, line_start: int, line_end: int):
        """
        Read the file from line range [line_start, line_end].
        For example, [0, 10] means the first 11 lines and [-10, -1] means the last 10 lines.
        The function tolerates line_start and line_end that exceed the actual line count.
        Returns text showing the file content with each line prefixed by its actual line number.
        """
        # Check permission
        if not self._check_permission(file_path, 'read'):
            return f"Permission denied: read({file_path})"

        # Normalize file path
        if not os.path.isabs(file_path):
            file_path = os.path.join(self.org_dir, file_path)

        mem_file = TextFile(file_path)
        lines = mem_file.read(line_start, line_end)

        # Format as text with line numbers
        if not lines:
            return ""

        result_lines = []
        for line_idx, line_content in lines:
            # result_lines.append(f"{line_idx}: {line_content}")
            result_lines.append(f"{line_content}")

        return "\n".join(result_lines)

    def search(self, file_or_dir_path: str, text: str, line_limit: int = 100, exclude_dirs: list = None):
        """
        Search the file(s) for given text.
        :param file_or_dir_path: File or directory path to search in
        :param text: Text to search for
        :param line_limit: Maximum number of lines to retrieve per file (default: 100)
        :param exclude_dirs: List of directory names to exclude from search (default: ['_temp', '_logs'])
        Returns a list of text elements, each element contains the matched file name,
        followed by the matched content with line numbers.
        """
        if exclude_dirs is None:
            exclude_dirs = ['_temp', '_logs']
        # Check permission
        if not self._check_permission(file_or_dir_path, 'read'):
            return [f"Permission denied: search({file_or_dir_path})"]

        result_list = []
        file_contents = {}  # file_path -> list of (line_idx, line_content)

        # Normalize path
        if not os.path.isabs(file_or_dir_path):
            search_path = os.path.join(self.org_dir, file_or_dir_path)
        else:
            search_path = file_or_dir_path

        if os.path.isfile(search_path):
            # Search in single file
            mem_file = TextFile(search_path)
            file_matches = mem_file.find(text)
            rel_path = os.path.relpath(search_path, self.org_dir)

            # Limit the number of lines
            file_matches = file_matches[:line_limit]

            if file_matches:
                file_contents[rel_path] = file_matches

        elif os.path.isdir(search_path):
            # Search in directory
            for root, dirs, files in os.walk(search_path):
                # Filter out excluded directories (modify dirs in-place to prevent traversal)
                dirs[:] = [d for d in dirs if d not in exclude_dirs]

                for file in files:
                    if file.endswith('.md'):
                        file_path = os.path.join(root, file)
                        mem_file = TextFile(file_path)
                        file_matches = mem_file.find(text)
                        rel_path = os.path.relpath(file_path, self.org_dir)

                        # Limit the number of lines per file
                        file_matches = file_matches[:line_limit]

                        if file_matches:
                            file_contents[rel_path] = file_matches

        # Format results as list of text elements
        for file_path, lines in file_contents.items():
            if lines:
                text_lines = [file_path]
                for line_idx, line_content in lines:
                    text_lines.append(f"{line_idx}: {line_content}")
                result_list.append("\n".join(text_lines))

        return result_list

    def search_semantic(self, file_or_dir_path: str, query_text: str, top_k: int = 5, line_limit: int = 100, exclude_dirs: list = None):
        """
        Semantic search using embeddings to find files with similar content.

        :param file_or_dir_path: File or directory path to search in
        :param query_text: Query text to search for semantically
        :param top_k: Number of top results to return (default: 5)
        :param line_limit: Maximum number of lines to retrieve per file (default: 100)
        :param exclude_dirs: List of directory names to exclude from search (default: ['_temp', '_logs'])
        Returns a list of text elements, each element contains the matched file name,
        followed by the file content with line numbers, sorted by semantic similarity.
        """
        if exclude_dirs is None:
            exclude_dirs = ['_temp', '_logs']
        # Check permission
        if not self._check_permission(file_or_dir_path, 'read'):
            return [f"Permission denied: search_semantic({file_or_dir_path})"]

        # Normalize path
        if not os.path.isabs(file_or_dir_path):
            search_path = os.path.join(self.org_dir, file_or_dir_path)
        else:
            search_path = file_or_dir_path

        # Collect all markdown files
        file_paths = []
        if os.path.isfile(search_path):
            file_paths.append(search_path)
        elif os.path.isdir(search_path):
            for root, dirs, files in os.walk(search_path):
                # Filter out excluded directories (modify dirs in-place to prevent traversal)
                dirs[:] = [d for d in dirs if d not in exclude_dirs]

                for file in files:
                    if file.endswith('.md'):
                        file_paths.append(os.path.join(root, file))

        if not file_paths:
            return []

        # Get query embedding
        try:
            query_embedding = self.agent.fm.embedding(query_text)
            if query_embedding is None:
                logger = structlog.get_logger(__name__)
                logger.error("Failed to generate query embedding")
                return []
        except Exception as e:
            logger = structlog.get_logger(__name__)
            logger.error(f"Error generating query embedding: {e}")
            return []

        # Compute similarities for all files
        file_similarities = []
        cache_updated = False

        for file_path in file_paths:
            try:
                # Get file content
                mem_file = TextFile(file_path)
                lines = mem_file.read(0, -1)
                if not lines:
                    continue

                content = '\n'.join([line_content for _, line_content in lines])

                # Get or compute file embedding
                mtime = os.path.getmtime(file_path)
                cache_key = file_path

                if cache_key in self._embedding_cache:
                    cached_mtime, cached_embedding = self._embedding_cache[cache_key]
                    if cached_mtime == mtime:
                        file_embedding = cached_embedding
                    else:
                        # File modified, recompute embedding
                        file_embedding = self.agent.fm.embedding(content)
                        if file_embedding is not None:
                            self._embedding_cache[cache_key] = (mtime, file_embedding)
                            cache_updated = True
                else:
                    # Compute new embedding
                    file_embedding = self.agent.fm.embedding(content)
                    if file_embedding is not None:
                        self._embedding_cache[cache_key] = (mtime, file_embedding)
                        cache_updated = True

                if file_embedding is None:
                    continue

                # Compute cosine similarity
                import numpy as np
                query_vec = np.array(query_embedding)
                file_vec = np.array(file_embedding)
                similarity = np.dot(query_vec, file_vec) / (np.linalg.norm(query_vec) * np.linalg.norm(file_vec))

                file_similarities.append((file_path, similarity, lines))

            except Exception as e:
                logger = structlog.get_logger(__name__)
                logger.warning(f"Error processing file {file_path}: {e}")
                continue

        # Save cache if updated
        if cache_updated:
            self._save_embedding_cache()

        # Sort by similarity (descending) and take top_k
        file_similarities.sort(key=lambda x: x[1], reverse=True)
        top_results = file_similarities[:top_k]

        # Format results
        result_list = []
        for file_path, similarity, lines in top_results:
            rel_path = os.path.relpath(file_path, self.org_dir)

            # Limit the number of lines
            lines = lines[:line_limit]

            if lines:
                text_lines = [f"{rel_path} (similarity: {similarity:.4f})"]
                for line_idx, line_content in lines:
                    text_lines.append(f"{line_idx}: {line_content}")
                result_list.append("\n".join(text_lines))

        return result_list

    def write(self, file_path: str, content: str):
        """
        Write content to a file. If the file doesn't exist, it will be created.

        Args:
            file_path: Path to the file to write
            content: Content to write to the file

        Raises:
            FilePermissionError: If permission is denied
            FileException: If write operation fails
        """
        # Check permission
        if not self._check_permission(file_path, 'write'):
            raise FilePermissionError(f"Permission denied: write({file_path})")

        # Normalize file path
        if not os.path.isabs(file_path):
            file_path = os.path.join(self.org_dir, file_path)

        lock = self._get_file_lock(file_path)
        with lock:
            try:
                mem_file = TextFile(file_path)
                # Write at line 0 (start of file)
                mem_file.write(content)
            except Exception as e:
                logger = structlog.get_logger(__name__)
                logger.error(f"Error writing file {file_path}: {e}")
                raise FileException(f"Failed to write file {file_path}: {e}")

    def append(self, file_path: str, content: str):
        """
        Append content to the end of a file. If the file doesn't exist, it will be created.

        Args:
            file_path: Path to the file
            content: Content to append

        Raises:
            FilePermissionError: If permission is denied
            FileException: If append operation fails
        """
        # Check permission
        if not self._check_permission(file_path, 'write'):
            logger = structlog.get_logger(__name__)
            logger.error(f"Permission denied when appending to {file_path}")
            raise FilePermissionError(f"Permission denied: append({file_path})")

        # Normalize file path
        if not os.path.isabs(file_path):
            file_path = os.path.join(self.org_dir, file_path)

        lock = self._get_file_lock(file_path)
        with lock:
            try:
                mem_file = TextFile(file_path)
                mem_file.append(content)
            except Exception as e:
                logger = structlog.get_logger(__name__)
                logger.error(f"Error appending to file {file_path}: {e}")
                raise FileException(f"Failed to append to file {file_path}: {e}")

    def insert(self, file_path: str, insert_line: int, content: str):
        """
        Insert content at a specific line number in a file. Line numbers are 0-indexed.

        Args:
            file_path: Path to the file
            insert_line: Line number to insert at (0-indexed)
            content: Content to insert

        Raises:
            FilePermissionError: If permission is denied
            FileException: If insert operation fails
        """
        # Check permission
        if not self._check_permission(file_path, 'write'):
            raise FilePermissionError(f"Permission denied: insert({file_path})")

        # Normalize file path
        if not os.path.isabs(file_path):
            file_path = os.path.join(self.org_dir, file_path)

        lock = self._get_file_lock(file_path)
        with lock:
            try:
                mem_file = TextFile(file_path)
                mem_file.insert(content=content, line_idx=insert_line)
            except Exception as e:
                logger = structlog.get_logger(__name__)
                logger.error(f"Error inserting into file {file_path}: {e}")
                raise FileException(f"Failed to insert into file {file_path}: {e}")

    def replace(self, file_path: str, match_text: str, replace_text: str):
        """
        Replace all occurrences of match_text with replace_text in a file.

        Args:
            file_path: Path to the file
            match_text: Text to search for
            replace_text: Text to replace with

        Raises:
            FilePermissionError: If permission is denied
            FileException: If replace operation fails
        """
        # Check permission
        if not self._check_permission(file_path, 'write'):
            raise FilePermissionError(f"Permission denied: replace({file_path})")

        # Normalize file path
        if not os.path.isabs(file_path):
            file_path = os.path.join(self.org_dir, file_path)

        lock = self._get_file_lock(file_path)
        with lock:
            try:
                # Read the file content
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()

                # Replace the text
                new_content = content.replace(match_text, replace_text)

                # Write back the content
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(new_content)
            except Exception as e:
                logger = structlog.get_logger(__name__)
                logger.error(f"Error replacing text in file {file_path}: {e}")
                raise FileException(f"Failed to replace text in file {file_path}: {e}")

    def delete(self, file_path: str):
        """
        Delete an entire file.

        Args:
            file_path: Path to the file to delete

        Raises:
            FilePermissionError: If permission is denied
            FileException: If delete operation fails or file doesn't exist
        """
        # Check permission
        if not self._check_permission(file_path, 'write'):
            raise FilePermissionError(f"Permission denied: delete({file_path})")

        # Normalize file path
        if not os.path.isabs(file_path):
            file_path = os.path.join(self.org_dir, file_path)

        lock = self._get_file_lock(file_path)
        with lock:
            try:
                if os.path.exists(file_path):
                    os.remove(file_path)
                else:
                    raise FileException(f"File does not exist: {file_path}")
            except FileException:
                raise
            except Exception as e:
                logger = structlog.get_logger(__name__)
                logger.error(f"Error deleting file {file_path}: {e}")
                raise FileException(f"Failed to delete file {file_path}: {e}")

    def remove_lines(self, file_path: str, line_start: int, line_end: int):
        """
        Remove lines from line_start to line_end (inclusive) from a file.

        Args:
            file_path: Path to the file
            line_start: Starting line number (inclusive)
            line_end: Ending line number (inclusive)

        Raises:
            FilePermissionError: If permission is denied
            FileException: If remove operation fails
        """
        # Check permission
        if not self._check_permission(file_path, 'write'):
            raise FilePermissionError(f"Permission denied: remove_lines({file_path})")

        # Normalize file path
        if not os.path.isabs(file_path):
            file_path = os.path.join(self.org_dir, file_path)

        lock = self._get_file_lock(file_path)
        with lock:
            try:
                mem_file = TextFile(file_path)
                mem_file.delete(line_start, line_end)
            except Exception as e:
                logger = structlog.get_logger(__name__)
                logger.error(f"Error removing lines from file {file_path}: {e}")
                raise FileException(f"Failed to remove lines from file {file_path}: {e}")
    
    def read_document(self, file_name: str):
        """
        Read a document and return the content as a list of text and images.

        :param file_name: Path to the document file
        :return: List containing text and images extracted from the document
        """
        from markitdown import MarkItDown
        md = MarkItDown(enable_plugins=False)
        result = md.convert(file_name)
        return [result.text_content]

    def parse_file(self, file_path: str):
        """
        Parse a file to model-readable format.
        Supports various file formats: doc, pdf, xlsx, pptx, etc.

        :param file_path: Path to the file to parse
        :return: Parsed file content as a list of text and images
        """
        try:
            # Use data interface to read document
            result = self.read_document(file_path)
            # Convert result to list format
            if isinstance(result, str):
                return [result]
            elif isinstance(result, list):
                return result
            else:
                return [str(result)]
        except Exception as e:
            logger = structlog.get_logger(__name__)
            logger.error(f"Error parsing file {file_path}: {e}")
            return [f"Error parsing file: {str(e)}"]

    def generate_file(self, file_path: str, requirement: str, materials):
        """
        Generate a new file based on given materials.
        Uses AI model to generate content for human use.

        :param file_path: Path where the file should be generated
        :param requirement: Text description of the file to generate
        :param materials: List of text and images to use as materials
        """
        try:
            # Convert materials to a prompt for the model
            text_materials = [m for m in materials if isinstance(m, str)]
            image_materials = [m for m in materials if not isinstance(m, str)]
            materials_text = '\n'.join(text_materials)

            prompt = f"""Generate a file based on the following requirement and materials.

Requirement: {requirement}

Materials:
{materials_text}

Please generate the content for the file."""

            # Query the model to generate content using VLM (can handle images if present)
            image = image_materials[0] if image_materials else None
            # TODO implement this by calling self.agent.fm.call_func
            raise NotImplementedError()

            # Write the generated content to the file
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(content)

            logger = structlog.get_logger(__name__)
            logger.info(f"Generated file: {file_path}")
        except Exception as e:
            logger = structlog.get_logger(__name__)
            logger.error(f"Error generating file {file_path}: {e}")
            raise

