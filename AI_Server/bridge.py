"""bridge.py —— OneBot v11 桥接：收私聊消息，回一句话

现在只是「回声」。接 dsh 是下一步。
被 start.py 拉起，也可以单独跑：

    python3 bridge.py --token xxx
"""

import argparse
import asyncio
import json

import websockets


def extract_text(message):
    """OneBot 的 message 可能是字符串，也可能是消息段数组。"""
    if isinstance(message, str):
        return message
    parts = []
    for seg in message or []:
        t = seg.get("type")
        if t == "text":
            parts.append(seg.get("data", {}).get("text", ""))
        elif t == "image":
            parts.append("[图片]")
        elif t == "face":
            parts.append("[表情]")
    return "".join(parts)


async def run(url, token):
    headers = {"Authorization": "Bearer " + token} if token else {}
    async with websockets.connect(url, additional_headers=headers) as ws:
        print("已连接:", url, flush=True)
        async for raw in ws:
            try:
                event = json.loads(raw)
            except json.JSONDecodeError:
                continue

            if event.get("post_type") != "message":
                if event.get("post_type") == "meta_event":
                    print("[meta]", event.get("meta_event_type"), flush=True)
                continue
            if event.get("message_type") != "private":
                continue

            uid = event.get("user_id")
            text = extract_text(event.get("message"))
            print("收到 %s: %s" % (uid, text), flush=True)

            await ws.send(json.dumps({
                "action": "send_private_msg",
                "params": {"user_id": uid, "message": "收到：" + text},
                "echo": "reply",
            }, ensure_ascii=False))


def main():
    p = argparse.ArgumentParser(description="OneBot 私聊桥接")
    p.add_argument("--url", default="ws://127.0.0.1:3001")
    p.add_argument("--token", default="")
    a = p.parse_args()
    try:
        asyncio.run(run(a.url, a.token))
    except KeyboardInterrupt:
        print("\nbye")


if __name__ == "__main__":
    main()
