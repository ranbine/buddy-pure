"""Stop -> turn end summary record."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _trace

if __name__ == "__main__":
    _trace._EVENT = "Stop"
    _trace.forward("stop")
