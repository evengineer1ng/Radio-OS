"""
Narrative Engine for From the Backmarker

*** DEPRECATED - MERGED INTO from_the_backmarker.py ***

This file has been fully integrated into from_the_backmarker.py to create
a unified meta plugin. All classes (EventRouter, BeatBuilder, ArcMemory,
NarratorBeat, NewsBeat) now live in from_the_backmarker.py.

This file is kept for backwards compatibility only.
Import from from_the_backmarker directly instead:

    from plugins.meta.from_the_backmarker import (
        EventRouter, BeatBuilder, ArcMemory, NarratorBeat, NewsBeat
    )
"""

# Re-export classes for backwards compatibility
try:
    from plugins.meta.from_the_backmarker import (
        EventRouter, BeatBuilder, ArcMemory, NarratorBeat, NewsBeat,
        EventTier
    )
except ImportError:
    pass
