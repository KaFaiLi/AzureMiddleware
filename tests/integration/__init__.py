"""Integration tests for Azure OpenAI Middleware.

These tests require a running middleware server with valid Azure credentials.

Run with:
    pytest tests/integration/ -v

Or with markers:
    pytest tests/integration/ -v -m "not thinking"  # Skip thinking model tests
    pytest tests/integration/ -v -m "not embedding"  # Skip embedding tests
"""
