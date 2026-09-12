"""Complete, validated starting configurations for the research workspace."""
from copy import deepcopy
import json
from pathlib import Path

from .engine import validate_request


def strategy_library():
    directory = Path(__file__).parent / 'presets'
    base = json.loads((directory / 'strangle-20-delta.json').read_text())
    ideas = json.loads((directory / 'library.json').read_text())
    for idea in ideas:
        config = {**deepcopy(base), **idea.pop('overrides')}
        # Reset the hidden custom editor too when switching back to a standard idea.
        config.setdefault('legs', [dict(type='P', side='sell', delta=.2, ratio=1),
                                   dict(type='C', side='sell', delta=.2, ratio=1)])
        idea['config'] = validate_request(config)
    return ideas
