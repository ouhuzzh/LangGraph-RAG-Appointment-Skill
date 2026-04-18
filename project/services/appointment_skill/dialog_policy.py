from __future__ import annotations


def format_department_options(departments: list[dict]) -> str:
    if not departments:
        return "目前没有找到可用科室。你可以告诉我症状，我先帮你推荐挂哪个科。"
    lines = [f"{idx}. **{item['name']}**" for idx, item in enumerate(departments, start=1)]
    return "目前可以查询或预约的常见科室有：\n\n" + "\n".join(lines) + "\n\n你可以直接告诉我科室名，或者先描述症状让我帮你推荐。"


def format_doctor_options(department: str, doctor_options: list[dict], *, lead: str = "") -> str:
    if not doctor_options:
        prefix = f"{lead}\n\n" if lead else ""
        return prefix + f"暂时没有找到 **{department}** 的可预约医生。你可以换个日期或时段，我继续帮你找。"
    lines = [
        f"{idx}. **{item['doctor_name']}** - {item.get('schedule_date')} {item.get('time_slot')}（剩余号源 {item.get('quota_available', 0)}）"
        for idx, item in enumerate(doctor_options[:8], start=1)
    ]
    prefix = f"{lead}\n\n" if lead else ""
    return (
        prefix
        + f"目前 **{department}** 可预约的医生有：\n\n"
        + "\n".join(lines)
        + "\n\n你可以直接回复医生姓名，或回复 **任一可用医生**。"
    )


def format_appointment_list(appointments: list[dict], *, empty_hint: str = "当前没有可取消的预约。") -> str:
    if not appointments:
        return empty_hint
    lines = [
        f"{idx}. 预约号：**{item['appointment_no']}**，{item['department']}，{item['appointment_date'].isoformat()} {item['time_slot']}，医生：{item.get('doctor_name') or '未指定'}"
        for idx, item in enumerate(appointments[:8], start=1)
    ]
    return "我找到你当前的预约如下：\n\n" + "\n".join(lines) + "\n\n你可以回复预约号，或者说“第 1 个 / 第 2 个”。"


def format_upcoming_availability(department: str, upcoming_rows: list[dict]) -> str:
    if not upcoming_rows:
        return f"目前没有找到 **{department}** 近期可用号源。你可以换个科室，或者让我根据症状先帮你推荐。"
    lines = [
        f"- **{item['doctor_name']}**：{item['schedule_date']} {item['time_slot']}（剩余号源 {item.get('quota_available', 0)}）"
        for item in upcoming_rows[:6]
    ]
    return (
        f"目前 **{department}** 最近可预约的时段有：\n\n"
        + "\n".join(lines)
        + "\n\n你可以直接说日期、时段和医生姓名，也可以回复 **任一可用医生**。"
    )


def format_reschedule_preview(current_item: dict, alternatives: list[dict]) -> str:
    if not alternatives:
        return (
            f"当前预约是 **{current_item['department']}** {current_item['appointment_date'].isoformat()} {current_item['time_slot']}，"
            "但我暂时没找到更合适的替代时段。你可以再告诉我更宽松的日期范围。"
        )
    lines = [
        f"{idx}. **{item['doctor_name']}**：{item['schedule_date']} {item['time_slot']}（剩余号源 {item.get('quota_available', 0)}）"
        for idx, item in enumerate(alternatives[:5], start=1)
    ]
    return (
        f"你当前的预约是 **{current_item['department']}** {current_item['appointment_date'].isoformat()} {current_item['time_slot']}。\n\n"
        "我找到这些可替代时段：\n\n"
        + "\n".join(lines)
        + "\n\n告诉我你想改成哪一个，我先为你准备改约预览。"
    )
