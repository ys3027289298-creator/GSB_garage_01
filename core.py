"""停车场核心逻辑：车位、进出、计费和预约。"""

import json

DEPOSIT = 10
MONTHLY_DISCOUNT = 10


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
    base = new_game()
    for key in base:
        state.setdefault(key, base[key])
    return state


def enter(state, plate):
    if not plate:
        return False
    if plate in state["vehicles"] or plate in state["reservations"]:
        return False
    free = next((s for s, v in state["spots"].items() if v is None), None)
    if free is None:
        return False
    state["spots"][free] = plate
    state["vehicles"][plate] = {"spot": free, "entry_day": state["day"], "monthly": False}
    return True


def can_enter(state):
    return any(v is None for v in state["spots"].values())


def fee(state, plate, exit_day):
    vehicle = state["vehicles"].get(plate)
    if vehicle is None:
        return 0
    return max(0, exit_day - vehicle["entry_day"])


def reserve(state, plate, spot, days):
    if not plate or spot not in state["spots"]:
        return False
    if state["spots"][spot] is not None:
        return False
    if plate in state["vehicles"] or plate in state["reservations"]:
        return False
    if days <= 0:
        return False
    state["spots"][spot] = plate
    state["reservations"][plate] = {"spot": spot, "expires": state["day"] + days, "deposit": DEPOSIT}
    return True


def expire_reservations(state, current_day):
    expired = [p for p, r in state["reservations"].items() if current_day >= r["expires"]]
    for plate in expired:
        res = state["reservations"].pop(plate)
        if state["spots"].get(res["spot"]) == plate:
            state["spots"][res["spot"]] = None
    return len(expired)


def cancel_reservation(state, plate):
    res = state["reservations"].pop(plate, None)
    if res is None:
        return 0
    if state["spots"].get(res["spot"]) == plate:
        state["spots"][res["spot"]] = None
    return res["deposit"]


def exit_vehicle(state, plate, paid):
    vehicle = state["vehicles"].get(plate)
    if vehicle is None:
        return False
    if not paid:
        return False
    if state["spots"].get(vehicle["spot"]) == plate:
        state["spots"][vehicle["spot"]] = None
    del state["vehicles"][plate]
    state["bills"].pop(plate, None)
    return True


def monthly_fee(state, plate, base):
    vehicle = state["vehicles"].get(plate)
    if vehicle is not None and vehicle["monthly"]:
        return max(0, base - MONTHLY_DISCOUNT)
    return base


def _parse_int(text):
    try:
        return int(text)
    except (TypeError, ValueError):
        return None


def main():
    state = new_game()
    print("停车场 - 命令: enter/canenter/fee/reserve/expire/cancel/exit/monthly/quit")
    while True:
        try:
            raw = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not raw:
            continue
        parts = raw.split()
        cmd, args = parts[0], parts[1:]
        if cmd == "quit":
            break
        elif cmd == "enter" and len(args) == 1:
            print("ok" if enter(state, args[0]) else "fail")
        elif cmd == "canenter" and not args:
            print("yes" if can_enter(state) else "no")
        elif cmd == "fee" and len(args) == 2:
            day = _parse_int(args[1])
            print("bad" if day is None else fee(state, args[0], day))
        elif cmd == "reserve" and len(args) == 3:
            days = _parse_int(args[2])
            ok = days is not None and reserve(state, args[0], args[1], days)
            print("ok" if ok else "fail")
        elif cmd == "expire" and len(args) == 1:
            day = _parse_int(args[0])
            print("bad" if day is None else expire_reservations(state, day))
        elif cmd == "cancel" and len(args) == 1:
            print(cancel_reservation(state, args[0]))
        elif cmd == "exit" and len(args) == 2:
            paid = args[1] in ("1", "true", "yes", "paid")
            print("ok" if exit_vehicle(state, args[0], paid) else "fail")
        elif cmd == "monthly" and len(args) == 2:
            base = _parse_int(args[1])
            print("bad" if base is None else monthly_fee(state, args[0], base))
        else:
            print("bad")


if __name__ == "__main__":
    main()
