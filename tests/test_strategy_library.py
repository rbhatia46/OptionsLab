import unittest

from app.options_lab.engine import DEFAULTS, validate_request
from app.options_lab.ideas import strategy_library


class StrategyLibraryTests(unittest.TestCase):
    def test_every_idea_is_complete_and_valid(self):
        ideas = strategy_library()
        self.assertEqual(len(ideas), 9)
        self.assertEqual(len({idea['id'] for idea in ideas}), len(ideas))
        for idea in ideas:
            with self.subTest(idea=idea['id']):
                self.assertEqual(set(idea['config']), set(DEFAULTS) | {'legs'})
                self.assertEqual(validate_request(idea['config']), idea['config'])

    def test_switching_ideas_resets_filters_experiments_and_custom_legs(self):
        ideas = {i['id']: i['config'] for i in strategy_library()}
        current = dict(ideas['delta-stop-grid'])
        for id in ('put-spread', 'delta-wings', 'strangle-20'):
            current.update(ideas[id])
            self.assertEqual(current, ideas[id])
        self.assertEqual(current['mode'], 'single')
        self.assertEqual(current['min_move_pct'], -100)
        self.assertEqual(len(current['legs']), 2)
        ideas['delta-wings']['legs'][0]['delta'] = .9
        fresh = {i['id']: i['config'] for i in strategy_library()}
        self.assertEqual(fresh['delta-wings']['legs'][0]['delta'], .25)
