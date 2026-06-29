"""Test rules generation with append mode."""

from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from codegenome.rules import write_rule


def test_write_rule_new_file():
    """Test writing rules to a new file."""
    with TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "test.md"
        content = "# CodeGenome Rules\nTest content"
        
        write_rule(path, content)
        
        result = path.read_text()
        assert "<!-- BEGIN CODEGENOME MCP INTEGRATION -->" in result
        assert "<!-- END CODEGENOME MCP INTEGRATION -->" in result
        assert content in result


def test_write_rule_existing_file_no_section():
    """Test appending rules to existing file without CodeGenome section."""
    with TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "test.md"
        
        # Create file with existing user content
        existing_content = "# My Custom Rules\n\nUser-defined content here.\n"
        path.write_text(existing_content)
        
        # Add CodeGenome rules
        codegenome_content = "# CodeGenome Rules\nTest content"
        write_rule(path, codegenome_content)
        
        result = path.read_text()
        
        # Both existing and new content should be present
        assert "My Custom Rules" in result
        assert "User-defined content here." in result
        assert "CodeGenome Rules" in result
        assert "<!-- BEGIN CODEGENOME MCP INTEGRATION -->" in result
        assert "<!-- END CODEGENOME MCP INTEGRATION -->" in result


def test_write_rule_existing_section_replacement():
    """Test replacing existing CodeGenome section."""
    with TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "test.md"
        
        # Create file with existing CodeGenome section
        initial_content = """# My Rules

User content before.

<!-- BEGIN CODEGENOME MCP INTEGRATION -->
# Old CodeGenome Rules
Old content that should be replaced.
<!-- END CODEGENOME MCP INTEGRATION -->

User content after.
"""
        path.write_text(initial_content)
        
        # Update CodeGenome rules
        new_codegenome_content = "# New CodeGenome Rules\nUpdated content"
        write_rule(path, new_codegenome_content)
        
        result = path.read_text()
        
        # User content should be preserved
        assert "User content before." in result
        assert "User content after." in result
        
        # Old CodeGenome content should be replaced
        assert "Old content that should be replaced." not in result
        
        # New CodeGenome content should be present
        assert "New CodeGenome Rules" in result
        assert "Updated content" in result


def test_write_rule_preserves_whitespace():
    """Test that existing file whitespace is preserved."""
    with TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / ".windsurfrules"
        
        # Create file with specific formatting
        existing_content = "# Windsurf Custom Rules\n\n\nSome rules here.\n\n"
        path.write_text(existing_content)
        
        # Add CodeGenome rules
        write_rule(path, "CodeGenome content")
        
        result = path.read_text()
        
        # Original content structure should be intact
        assert result.startswith("# Windsurf Custom Rules\n\n\nSome rules here.\n\n")


def test_write_rule_multiple_updates():
    """Test multiple updates to the same file."""
    with TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "AGENTS.md"
        
        # First write
        write_rule(path, "Version 1")
        result1 = path.read_text()
        assert "Version 1" in result1
        
        # Second write (update)
        write_rule(path, "Version 2")
        result2 = path.read_text()
        assert "Version 2" in result2
        assert "Version 1" not in result2
        
        # Third write (update)
        write_rule(path, "Version 3")
        result3 = path.read_text()
        assert "Version 3" in result3
        assert "Version 2" not in result3
        assert "Version 1" not in result3
