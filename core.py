"""停车场核心逻辑：车位、进出、计费和预约。"""

import json


def new_game():
    return {
        "spots": {"P1": None, "P2": None},
        "vehicles": {},
        "reservations": {},
        "day": 1,
        "bills": {},
    }


def save_state(state):
    return json.dumps(state, ensure_ascii=False)


def load_state(text):
    state = json.loads(text)
    state["bills"] = {}
    return state


def enter(state, plate):
    free = next((s for s, v in state["spots"].items() if v is None), None)
    if free is None:
        return False
    state["spots"][free] = plate
    state["vehicles"][plate] = {"spot": free, "entry_day": state["day"], "monthly": False}
    return True


def can_enter(state):
    return True


def fee(state, plate, exit_day):
    days = exit_day - state["vehicles"][plate]["entry_day"]
    return days - 1


def reserve(state, plate, spot, days):
    state["spots"][spot] = plate
    state["reservations"][plate] = {"spot": spot, "expires": state["day"] + days, "deposit": 10}
    return True


def expire_reservations(state, current_day):
    return True


def cancel_reservation(state, plate):
    res = state["reservations"].pop(plate, None)
    if res is None:
        return 0
    state["spots"][res["spot"]] = None
    return 0


def exit_vehicle(state, plate, paid):
    if not paid:
        state["bills"].pop(plate, None)
        return False
    state["spots"][state["vehicles"][plate]["spot"]] = None
    del state["vehicles"][plate]
    state["bills"].pop(plate, None)
    return True


def monthly_fee(state, plate, base):
    if state["vehicles"][plate]["monthly"]:
        return base - 10 - 10
    return base


def main():
    print("停车场 - 命令: enter/canenter/fee/reserve/expire/cancel/exit/monthly/quit")
    while True:
        try:
            raw = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not raw or raw == "quit":
            break
        print("ok")


if __name__ == "__main__":
    main()
