"""PostToolUse -> tool timing + sub-agent budget brake."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _trace

if __name__ == "__main__":
    _trace._EVENT = "PostToolUse"
    _trace.forward("post")
