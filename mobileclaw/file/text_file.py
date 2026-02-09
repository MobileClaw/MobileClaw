import os
import re


class TextFile:
    def __init__(self, file_path: str):
        """
        :param file_path: markdown
        """
        self.file_path = file_path

    def line_count(self):
        """Return the number of lines in this file"""
        if not os.path.exists(self.file_path):
            return 0
        with open(self.file_path, 'r', encoding='utf-8') as f:
            return sum(1 for _ in f)

    def description(self):
        """Return the description (the first line) of this file"""
        if not os.path.exists(self.file_path):
            return ""
        with open(self.file_path, 'r', encoding='utf-8') as f:
            first_line = f.readline().strip()
            return first_line

    def read(self, line_low=0, line_high=-1):
        """
        Read lines from this file.
        [line_low, line_high] is the line index range (0-indexed).
        e.g. [0, 9] means reading the first 10 lines, [-10, -1] means reading the last 10 lines.
        Returns a list of tuples [(line_idx, line_content), ...]
        """
        if not os.path.exists(self.file_path):
            return []

        with open(self.file_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()

        total_lines = len(lines)
        if total_lines == 0:
            return []

        # Handle negative indices
        if line_low < 0:
            line_low = max(0, total_lines + line_low)
        if line_high < 0:
            line_high = total_lines + line_high

        # Clamp to valid range
        line_low = max(0, min(line_low, total_lines - 1))
        line_high = max(0, min(line_high, total_lines - 1))

        # Return list of (index, content) tuples
        result = []
        for i in range(line_low, line_high + 1):
            if i < total_lines:
                result.append((i, lines[i].rstrip('\n')))

        return result

    def delete(self, line_low=0, line_high=-1):
        """
        Delete lines from this file.
        [line_low, line_high] is the line index range (0-indexed).
        e.g. [0, 9] means deleting the first 10 lines, [-10, -1] means deleting the last 10 lines.
        """
        if not os.path.exists(self.file_path):
            return

        with open(self.file_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()

        total_lines = len(lines)
        if total_lines == 0:
            return

        # Handle negative indices
        if line_low < 0:
            line_low = max(0, total_lines + line_low)
        if line_high < 0:
            line_high = total_lines + line_high

        # Clamp to valid range
        line_low = max(0, min(line_low, total_lines - 1))
        line_high = max(0, min(line_high, total_lines - 1))

        # Remove lines in the range
        new_lines = lines[:line_low] + lines[line_high + 1:]

        # Write back to file
        with open(self.file_path, 'w', encoding='utf-8') as f:
            f.writelines(new_lines)

    def write(self, content):
        """
        Write content to this file.
        """
        # Ensure directory exists
        os.makedirs(os.path.dirname(self.file_path) or '.', exist_ok=True)
        lines = [content]

        # Write back to file
        with open(self.file_path, 'w', encoding='utf-8') as f:
            f.writelines(lines)
    
    def append(self, content):
        """
        Append content to this file.
        """
        # Ensure directory exists
        os.makedirs(os.path.dirname(self.file_path) or '.', exist_ok=True)
        lines = [content]

        # Write to file
        with open(self.file_path, 'a', encoding='utf-8') as f:
            f.writelines(lines)

    def insert(self, content, line_idx=0):
        """
        Insert content to this file.
        line_idx is the line number to insert the content.
        By default, the content will be written to the start of the file (line_idx=0).
        """
        # Ensure directory exists
        os.makedirs(os.path.dirname(self.file_path) or '.', exist_ok=True)

        # Read existing lines if file exists
        if os.path.exists(self.file_path):
            with open(self.file_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
        else:
            lines = []

        # Ensure content ends with newline
        if content and not content.endswith('\n'):
            content += '\n'

        # Handle negative index
        if line_idx < 0:
            line_idx = max(0, len(lines) + line_idx + 1)

        # Insert content at specified line
        lines.insert(line_idx, content)

        # Write back to file
        with open(self.file_path, 'w', encoding='utf-8') as f:
            f.writelines(lines)

    def find(self, target):
        """
        Find lines that match the target (could be a substr or a regex).
        Returns a list of tuples [(line_idx, line_content), ...]
        """
        if not os.path.exists(self.file_path):
            return []

        result = []
        with open(self.file_path, 'r', encoding='utf-8') as f:
            for idx, line in enumerate(f):
                line_content = line.rstrip('\n')
                # Try regex match first, fall back to substring match
                try:
                    if re.search(target, line_content):
                        result.append((idx, line_content))
                except re.error:
                    # If regex is invalid, use substring match
                    if target in line_content:
                        result.append((idx, line_content))

        return result

