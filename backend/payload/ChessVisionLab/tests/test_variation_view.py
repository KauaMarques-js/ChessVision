import unittest

from variation_view import next_cycle_rank, selected_line


class VariationViewTests(unittest.TestCase):
    def test_human_selection_requires_native_suggestion(self):
        lines=[{'rank':1,'uci':'e2e4'}]
        self.assertIsNone(selected_line(lines,'human'))
        suggestion={'rank':3,'uci':'g1f3','skill':7}
        self.assertEqual(selected_line(lines,'human',human_line=suggestion),suggestion)
    def setUp(self):
        self.lines = [
            {'rank': 1, 'uci': 'e2e4'},
            {'rank': 2, 'uci': 'd2d4'},
            {'rank': 3, 'uci': 'g1f3'},
            {'rank': 4, 'uci': 'c2c4'},
            {'rank': 5, 'uci': 'g2g3'},
        ]

    def test_manual_mode_selects_exact_ranking(self):
        for mode, uci in [('all', 'e2e4'), ('first', 'e2e4'),
                          ('second', 'd2d4'), ('third', 'g1f3'),
                          ('fourth', 'c2c4'), ('fifth', 'g2g3')]:
            with self.subTest(mode=mode):
                self.assertEqual(selected_line(self.lines, mode)['uci'], uci)

    def test_missing_third_never_falls_back_to_first(self):
        self.assertIsNone(selected_line(self.lines[:2], 'third'))
        self.assertIsNone(selected_line([], 'first'))

    def test_alternation_cycles_all_five(self):
        rank = 1
        observed = []
        for _ in range(6):
            observed.append(selected_line(self.lines, 'alternate', rank)['rank'])
            rank = next_cycle_rank(self.lines, rank)
        self.assertEqual(observed, [1, 2, 3, 4, 5, 1])

    def test_missing_fifth_never_substitutes_a_better_move(self):
        self.assertIsNone(selected_line(self.lines[:4], 'fifth'))

    def test_alternation_skips_unavailable_ranks(self):
        partial = [self.lines[0], self.lines[2]]
        self.assertEqual(next_cycle_rank(partial, 1), 3)
        self.assertEqual(next_cycle_rank(partial, 3), 1)
        self.assertEqual(selected_line(partial, 'alternate', 2)['rank'], 1)
        self.assertEqual(next_cycle_rank([], 2), 1)


if __name__ == '__main__':
    unittest.main()
