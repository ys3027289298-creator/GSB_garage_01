"""回归测试：覆盖八个缺陷修复后的幂等性与边界/非法输入。"""

import io
import unittest
from contextlib import redirect_stdout

import core


class TestEntry(unittest.TestCase):
    def test_duplicate_entry_idempotent(self):
        state = core.new_game()
        self.assertTrue(core.enter(state, "A"))
        self.assertFalse(core.enter(state, "A"))
        self.assertEqual(state["spots"]["P1"], "A")
        self.assertIsNone(state["spots"]["P2"])
        self.assertEqual(len(state["vehicles"]), 1)

    def test_capacity_boundary_and_full(self):
        state = core.new_game()
        self.assertTrue(core.enter(state, "A"))
        self.assertTrue(core.enter(state, "B"))
        self.assertFalse(core.can_enter(state))
        self.assertFalse(core.enter(state, "C"))
        self.assertNotIn("C", state["vehicles"])

    def test_invalid_plate(self):
        state = core.new_game()
        self.assertFalse(core.enter(state, ""))
        self.assertTrue(core.can_enter(state))


class TestFee(unittest.TestCase):
    def test_same_day_is_zero(self):
        state = core.new_game()
        core.enter(state, "A")
        self.assertEqual(core.fee(state, "A", 1), 0)

    def test_cross_day(self):
        state = core.new_game()
        core.enter(state, "A")
        self.assertEqual(core.fee(state, "A", 4), 3)

    def test_invalid_exit_day(self):
        state = core.new_game()
        core.enter(state, "A")
        self.assertIsNone(core.fee(state, "A", 0))
        self.assertIsNone(core.fee(state, "A", "x"))
        self.assertIsNone(core.fee(state, "GHOST", 5))

    def test_fee_is_pure(self):
        state = core.new_game()
        core.enter(state, "A")
        core.fee(state, "A", 3)
        core.fee(state, "A", 3)
        self.assertEqual(state["bills"], {})


class TestReservation(unittest.TestCase):
    def test_reserve_occupies_and_blocks(self):
        state = core.new_game()
        self.assertTrue(core.reserve(state, "A", "P1", 2))
        self.assertEqual(state["spots"]["P1"], "A")
        self.assertFalse(core.reserve(state, "B", "P1", 1))

    def test_invalid_reserve(self):
        state = core.new_game()
        self.assertFalse(core.reserve(state, "A", "PX", 1))
        self.assertFalse(core.reserve(state, "A", "P1", 0))
        self.assertFalse(core.reserve(state, "", "P1", 1))
        self.assertIsNone(state["spots"]["P1"])

    def test_expire_releases_once(self):
        state = core.new_game()
        core.reserve(state, "A", "P1", 1)
        self.assertTrue(core.expire_reservations(state, 3))
        self.assertIsNone(state["spots"]["P1"])
        self.assertNotIn("A", state["reservations"])
        self.assertTrue(core.expire_reservations(state, 3))
        self.assertIsNone(state["spots"]["P1"])

    def test_not_expired_on_due_day(self):
        state = core.new_game()
        core.reserve(state, "A", "P1", 1)
        self.assertTrue(core.expire_reservations(state, 2))
        self.assertEqual(state["spots"]["P1"], "A")

    def test_cancel_refund_idempotent(self):
        state = core.new_game()
        core.reserve(state, "A", "P1", 2)
        self.assertEqual(core.cancel_reservation(state, "A"), 10)
        self.assertIsNone(state["spots"]["P1"])
        self.assertEqual(core.cancel_reservation(state, "A"), 0)

    def test_enter_consumes_reservation(self):
        state = core.new_game()
        core.reserve(state, "A", "P1", 2)
        self.assertTrue(core.enter(state, "A"))
        self.assertEqual(state["vehicles"]["A"]["spot"], "P1")
        self.assertNotIn("A", state["reservations"])
        self.assertFalse(core.enter(state, "A"))

    def test_expire_rejects_backward_day(self):
        state = core.new_game()
        core.reserve(state, "A", "P1", 5)
        core.expire_reservations(state, 4)
        self.assertFalse(core.expire_reservations(state, 2))
        self.assertIn("A", state["reservations"])


class TestExit(unittest.TestCase):
    def test_unpaid_exit_keeps_everything(self):
        state = core.new_game()
        core.enter(state, "A")
        state["bills"]["A"] = 20
        self.assertFalse(core.exit_vehicle(state, "A", False))
        self.assertEqual(state["bills"]["A"], 20)
        self.assertEqual(state["spots"]["P1"], "A")
        self.assertIn("A", state["vehicles"])

    def test_paid_exit_clears_and_releases(self):
        state = core.new_game()
        core.enter(state, "A")
        state["bills"]["A"] = 20
        self.assertTrue(core.exit_vehicle(state, "A", True))
        self.assertNotIn("A", state["bills"])
        self.assertNotIn("A", state["vehicles"])
        self.assertIsNone(state["spots"]["P1"])

    def test_double_exit_after_success(self):
        state = core.new_game()
        core.enter(state, "A")
        self.assertTrue(core.exit_vehicle(state, "A", True))
        self.assertFalse(core.exit_vehicle(state, "A", True))


class TestMonthly(unittest.TestCase):
    def test_discount_once(self):
        state = core.new_game()
        core.enter(state, "A")
        state["vehicles"]["A"]["monthly"] = True
        self.assertEqual(core.monthly_fee(state, "A", 100), 90)
        self.assertEqual(core.monthly_fee(state, "A", 100), 90)

    def test_no_discount_for_normal(self):
        state = core.new_game()
        core.enter(state, "A")
        self.assertEqual(core.monthly_fee(state, "A", 100), 100)

    def test_fee_never_negative(self):
        state = core.new_game()
        core.enter(state, "A")
        state["vehicles"]["A"]["monthly"] = True
        self.assertEqual(core.monthly_fee(state, "A", 5), 0)


class TestPersistence(unittest.TestCase):
    def test_roundtrip_full_state(self):
        state = core.new_game()
        core.enter(state, "A")
        core.reserve(state, "B", "P2", 1)
        state["bills"]["A"] = 7
        loaded = core.load_state(core.save_state(state))
        self.assertEqual(loaded["spots"], state["spots"])
        self.assertEqual(loaded["bills"]["A"], 7)
        self.assertIn("B", loaded["reservations"])

    def test_load_empty_raises(self):
        with self.assertRaises(ValueError):
            core.load_state("")
        with self.assertRaises(ValueError):
            core.load_state("   ")
        with self.assertRaises(ValueError):
            core.load_state("not-json")

    def test_load_fills_missing_keys(self):
        loaded = core.load_state('{"day": 3}')
        self.assertEqual(loaded["day"], 3)
        self.assertEqual(loaded["spots"], {"P1": None, "P2": None})
        self.assertEqual(loaded["bills"], {})

    def test_load_reconciles_stale_spot(self):
        state = core.new_game()
        state["spots"]["P1"] = "GHOST"
        text = core.save_state(state)
        loaded = core.load_state(text)
        self.assertIsNone(loaded["spots"]["P1"])

    def test_load_reconciles_from_vehicles(self):
        state = core.new_game()
        core.enter(state, "A")
        state["spots"]["P1"] = None
        loaded = core.load_state(core.save_state(state))
        self.assertEqual(loaded["spots"]["P1"], "A")


class TestCli(unittest.TestCase):
    def _run(self, lines):
        import core as c
        state = c.new_game()
        out = io.StringIO()
        with redirect_stdout(out):
            for line in lines:
                print(c._run_command(state, line.split()), file=out)
        return out.getvalue()

    def test_illegal_commands(self):
        out = self._run(["frobnicate x", "enter", "fee A x", "monthly A x"])
        self.assertIn("未知命令", out)
        self.assertIn("需要车牌", out)
        self.assertIn("必须是整数", out)
        self.assertIn("非负整数", out)

    def test_duplicate_input_flow(self):
        out = self._run([
            "enter A", "enter A",
            "canenter", "enter B", "canenter",
            "fee A 3", "fee A 3",
            "exit A 0", "exit A 0",
            "reserve B P1 1",
        ])
        self.assertIn("失败", out)
        self.assertIn("2", out)

    def test_reserve_expire_cancel_flow(self):
        out = self._run([
            "reserve A P1 1", "reserve A P1 1",
            "cancel A", "cancel A",
            "reserve A P1 1", "expire 3",
        ])
        self.assertIn("ok", out)
        self.assertIn("10", out)
        self.assertIn("0", out)


if __name__ == "__main__":
    unittest.main()
