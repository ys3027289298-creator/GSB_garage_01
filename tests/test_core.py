import unittest

import core


class TestCore(unittest.TestCase):
    def test_01_no_duplicate_entry(self):
        state = core.new_game()
        self.assertTrue(core.enter(state, "A"))
        self.assertFalse(core.enter(state, "A"))

    def test_02_no_entry_when_full(self):
        state = core.new_game()
        core.enter(state, "A")
        core.enter(state, "B")
        self.assertFalse(core.can_enter(state))

    def test_03_cross_day_fee_exact(self):
        state = core.new_game()
        core.enter(state, "A")
        self.assertEqual(core.fee(state, "A", 3), 2)

    def test_04_expired_reservation_releases_spot(self):
        state = core.new_game()
        core.reserve(state, "A", "P1", 1)
        core.expire_reservations(state, 5)
        self.assertIsNone(state["spots"]["P1"])

    def test_05_exit_failure_keeps_bill(self):
        state = core.new_game()
        core.enter(state, "A")
        state["bills"]["A"] = 20
        result = core.exit_vehicle(state, "A", False)
        self.assertFalse(result)
        self.assertIn("A", state["bills"])

    def test_06_monthly_discount_once(self):
        state = core.new_game()
        core.enter(state, "A")
        state["vehicles"]["A"]["monthly"] = True
        self.assertEqual(core.monthly_fee(state, "A", 100), 90)

    def test_07_cancel_reservation_refunds_deposit(self):
        state = core.new_game()
        core.reserve(state, "A", "P1", 1)
        self.assertEqual(core.cancel_reservation(state, "A"), 10)

    def test_08_load_keeps_bills_consistent(self):
        state = core.new_game()
        state["bills"]["A"] = 20
        loaded = core.load_state(core.save_state(state))
        self.assertEqual(loaded["bills"].get("A"), 20)


if __name__ == "__main__":
    unittest.main()
