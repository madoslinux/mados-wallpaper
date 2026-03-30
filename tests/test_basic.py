#!/usr/bin/env python3
"""Basic tests for mados-wallpaper - verify modules compile."""

import py_compile
import os

test_dir = os.path.dirname(os.path.abspath(__file__))
repo_dir = os.path.dirname(test_dir)

def test_http_client_compile():
    """Test http_client.py compiles without syntax errors."""
    py_compile.compile(f"{repo_dir}/http_client.py", doraise=True)


def test_workspace_card_compile():
    """Test workspace_card.py compiles without syntax errors."""
    py_compile.compile(f"{repo_dir}/workspace_card.py", doraise=True)


def test_config_compile():
    """Test config.py compiles without syntax errors."""
    py_compile.compile(f"{repo_dir}/config.py", doraise=True)


def test_database_compile():
    """Test database.py compiles without syntax errors."""
    py_compile.compile(f"{repo_dir}/database.py", doraise=True)


if __name__ == "__main__":
    test_http_client_compile()
    test_workspace_card_compile()
    test_config_compile()
    test_database_compile()
    print("All tests passed!")
