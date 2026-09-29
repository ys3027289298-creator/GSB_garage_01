"""停车场核心逻辑：车位、进出、计费和预约。

规则约定：
- 按跨日天数计费：fee = 出场日 - 入场日（同日出场为 0）。
- 预约在 expires 当日仍有效，current_day > expires 才算过期。
- 预约成功立即占用车位；取消时退还押金；过期自动释放车位。
- 每个操作都是幂等的：重复触发不会重复占用、重复收费或重复退款。
"""

import json

DEPOSIT = 10        # 预约押金
MONTHLY_DISCOUNT = 10  # 月卡折扣
SPOT_IDS = ("P1", "P2")


def new_game():
    return {
        "spots": {spot: None for spot in SPOT_IDS},
        "vehicles": {},
        "reservations": {},
        "day": 1,
        "bills": {},
    }


def save_state(state):
    return json.dumps(state, ensure_ascii=False)


def load_state(text):
    """从 JSON 恢复状态。

    容忍空数据/缺键（补默认值），并按 vehicles、reservations 校正车位，
    保证读档后车位与流水一致。bills 原样保留。
    """
    if not isinstance(text, str) or not text.strip():
        raise ValueError("空数据：无法加载存档")
    try:
        raw = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError("非法存档：不是合法 JSON") from exc
    if not isinstance(raw, dict):
        raise ValueError("非法存档：顶层必须是对象")

    base = new_game()
    base.update(raw)
    if not isinstance(base["spots"], dict):
        raise ValueError("非法存档：spots 必须是对象")
    for key in ("vehicles", "reservations", "bills"):
        if not isinstance(base[key], dict):
            raise ValueError("非法存档：%s 必须是对象" % key)
    if not isinstance(base["day"], int) or isinstance(base["day"], bool):
        raise ValueError("非法存档：day 必须是整数")

    for spot in SPOT_IDS:
        base["spots"].setdefault(spot, None)

    # 以车辆流水为准，再叠加有效预约，重建车位占用，消除读档不一致。
    for spot in list(base["spots"].keys()):
        base["spots"][spot] = None
    for plate, info in base["vehicles"].items():
        spot = info.get("spot")
        if spot in base["spots"]:
            base["spots"][spot] = plate
        else:
            info["spot"] = None
    for plate, res in base["reservations"].items():
        spot = res.get("spot")
        if spot in base["spots"] and base["spots"][spot] is None:
            base["spots"][spot] = plate
    return base


def _release_spot(state, spot, plate):
    """只有车位当前确实属于 plate 时才释放，保证幂等。"""
    if spot in state["spots"] and state["spots"][spot] == plate:
        state["spots"][spot] = None


def enter(state, plate):
    if not isinstance(plate, str) or not plate:
        return False
    if plate in state["vehicles"]:
        return False

    reservation = state["reservations"].get(plate)
    spot = None
    if reservation is not None:
        reserved_spot = reservation.get("spot")
        if state["spots"].get(reserved_spot) == plate:
            spot = reserved_spot
        else:
            # 预约车位已不可用（脏数据/被占）：清掉失效预约后再找普通空位。
            state["reservations"].pop(plate, None)

    if spot is None:
        spot = next(
            (name for name, holder in state["spots"].items() if holder is None),
            None,
        )
    if spot is None:
        return False

    state["spots"][spot] = plate
    state["vehicles"][plate] = {
        "spot": spot,
        "entry_day": state["day"],
        "monthly": False,
    }
    # 入场后预约消费掉（车位仍被该车辆占用），押金不退。
    state["reservations"].pop(plate, None)
    return True


def can_enter(state):
    return any(holder is None for holder in state["spots"].values())


def fee(state, plate, exit_day):
    """返回跨日计费天数（纯查询，不修改账单）。非法输入返回 None。"""
    info = state["vehicles"].get(plate)
    if info is None:
        return None
    if not isinstance(exit_day, int) or isinstance(exit_day, bool):
        return None
    if exit_day < info["entry_day"]:
        return None
    return exit_day - info["entry_day"]


def reserve(state, plate, spot, days):
    """预约车位：立即占用，返回是否成功。重复/非法/已满均失败且幂等。"""
    if not isinstance(plate, str) or not plate:
        return False
    if spot not in state["spots"]:
        return False
    if not isinstance(days, int) or isinstance(days, bool) or days <= 0:
        return False
    if plate in state["vehicles"]:
        return False
    existing = state["reservations"].get(plate)
    if existing is not None:
        # 重复预约：仅完全相同的预约视为幂等成功，不重复收押金。
        return existing.get("spot") == spot and existing.get("expires") == state["day"] + days
    if state["spots"][spot] is not None:
        return False

    state["spots"][spot] = plate
    state["reservations"][plate] = {
        "spot": spot,
        "expires": state["day"] + days,
        "deposit": DEPOSIT,
    }
    return True


def expire_reservations(state, current_day):
    """释放所有已过期预约占用的车位。重复调用无副作用。"""
    if not isinstance(current_day, int) or isinstance(current_day, bool):
        return False
    if current_day < state["day"]:
        return False
    state["day"] = current_day
    for plate, reservation in list(state["reservations"].items()):
        if current_day > reservation["expires"]:
            _release_spot(state, reservation["spot"], plate)
            state["reservations"].pop(plate, None)
    return True


def cancel_reservation(state, plate):
    """取消预约并退还押金；重复取消返回 0。"""
    reservation = state["reservations"].pop(plate, None)
    if reservation is None:
        return 0
    _release_spot(state, reservation["spot"], plate)
    return reservation.get("deposit", DEPOSIT)


def exit_vehicle(state, plate, paid):
    """出场：仅 paid 为真且车辆在场时放行、清账单。

    出场失败（未付费、车辆不存在）时账单与车位保持原样，可安全重试。
    """
    info = state["vehicles"].get(plate)
    if info is None or not paid:
        return False
    _release_spot(state, info["spot"], plate)
    del state["vehicles"][plate]
    state["bills"].pop(plate, None)
    return True


def monthly_fee(state, plate, base):
    """月卡折扣只减一次，结果不为负。非法基础金额返回 None。"""
    if not isinstance(base, (int, float)) or isinstance(base, bool) or base < 0:
        return None
    info = state["vehicles"].get(plate)
    if info is not None and info.get("monthly"):
        return max(0, base - MONTHLY_DISCOUNT)
    return base


def _parse_int(text):
    try:
        return int(text)
    except (TypeError, ValueError):
        return None


def _parse_paid(text):
    return text in ("1", "true", "yes", "y", "t")


def _run_command(state, parts):
    """执行一条命令，返回要打印给用户的字符串。命令名与 JSON 键名保持不变。"""
    cmd = parts[0]
    args = parts[1:]
    if cmd == "enter":
        if len(args) != 1:
            return "错误: enter 需要车牌参数"
        return "ok" if enter(state, args[0]) else "失败: 车辆已在场或车位已满"
    if cmd == "canenter":
        if args:
            return "错误: canenter 不带参数"
        return "ok" if can_enter(state) else "失败: 车位已满"
    if cmd == "fee":
        if len(args) != 2:
            return "错误: fee 需要车牌和出场日参数"
        exit_day = _parse_int(args[1])
        if exit_day is None:
            return "错误: 出场日必须是整数"
        amount = fee(state, args[0], exit_day)
        return "失败: 车辆不在场" if amount is None else str(amount)
    if cmd == "reserve":
        if len(args) != 3:
            return "错误: reserve 需要车牌、车位和天数参数"
        days = _parse_int(args[2])
        if days is None or days <= 0:
            return "错误: 预约天数必须是正整数"
        ok = reserve(state, args[0], args[1], days)
        return "ok" if ok else "失败: 车位不可用、重复或非法预约"
    if cmd == "expire":
        if len(args) != 1:
            return "错误: expire 需要当前日参数"
        current_day = _parse_int(args[0])
        if current_day is None:
            return "错误: 当前日必须是整数"
        return "ok" if expire_reservations(state, current_day) else "失败: 日期非法"
    if cmd == "cancel":
        if len(args) != 1:
            return "错误: cancel 需要车牌参数"
        return str(cancel_reservation(state, args[0]))
    if cmd == "exit":
        if len(args) != 2:
            return "错误: exit 需要车牌和是否已付费参数"
        ok = exit_vehicle(state, args[0], _parse_paid(args[1].lower()))
        return "ok" if ok else "失败: 车辆不在场或未付费"
    if cmd == "monthly":
        if len(args) != 2:
            return "错误: monthly 需要车牌和基础费用参数"
        base = _parse_int(args[1])
        if base is None or base < 0:
            return "错误: 基础费用必须是非负整数"
        amount = monthly_fee(state, args[0], base)
        return "失败: 基础费用非法" if amount is None else str(amount)
    return "错误: 未知命令"


def main():
    print("停车场 - 命令: enter/canenter/fee/reserve/expire/cancel/exit/monthly/quit")
    state = new_game()
    while True:
        try:
            raw = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not raw:
            continue
        if raw == "quit":
            break
        print(_run_command(state, raw.split()))


if __name__ == "__main__":
    main()
