import unittest
from push_box_game import PushBoxGame


class PushBoxGameTestInitGame(unittest.TestCase):
    def setUp(self) -> None:
        self.game_map = [
            "#####",
            "#O  #",
            "# X #",
            "#  G#",
            "#####"
        ]
        self.game = PushBoxGame(self.game_map)

    def test_init_game_1(self):
        self.assertEqual(self.game.map, self.game_map)

    def test_init_game_2(self):
        self.assertEqual(self.game.is_game_over, False)

    def test_init_game_3(self):
        self.assertEqual(self.game.player_col, 1)

    def test_init_game_4(self):
        self.assertEqual(self.game.player_row, 1)

    def test_init_game_5(self):
        self.assertEqual(self.game.targets, [(3, 3)])

    def test_init_game_6(self):
        self.assertEqual(self.game.boxes, [(2, 2)])

    def test_init_game_7(self):
        self.assertEqual(self.game.target_count, 1)

class PushBoxGameTestCheckWin(unittest.TestCase):
    def setUp(self) -> None:
        self.game_map = [
            "#####",
            "#O  #",
            "# X #",
            "#  G#",
            "#####"
        ]
        self.game = PushBoxGame(self.game_map)

    def test_check_win_1(self):
        self.assertFalse(self.game.check_win())

    def test_check_win_2(self):
        moves = ['d', 's', 'a', 's', 'd']
        for move in moves:
            self.game.move(move)
        self.assertTrue(self.game.check_win())
