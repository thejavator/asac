import unittest

from todo import add, done


class TodoTests(unittest.TestCase):
    def test_add_strips(self) -> None:
        self.assertEqual(add([], "  buy milk "), ["buy milk"])

    def test_done_removes(self) -> None:
        self.assertEqual(done(["a", "b"], "a"), ["b"])


if __name__ == "__main__":
    unittest.main()
