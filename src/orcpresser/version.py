"""Project version metadata.

VERSION is numeric-only because the updater parses and compares it.
DISPLAY_VERSION may include the development channel shown in the UI/docs.
"""
VERSION = '2.5.0'
CHANNEL = 'dev'
DISPLAY_VERSION = f'{VERSION}-{CHANNEL}' if CHANNEL else VERSION
