import asyncio
import base64
import json
import re
import socket
import time
import urllib.request
from urllib.parse import urlparse

# 1. 填入你提供的那 3 个巨大的开源项目订阅源
SOURCES = [
    "https://raw.githubusercontent.com/barry-far/V2ray-config/main/Sub1.txt",
    "https://raw.githubusercontent.com/ebrasha/free-v2ray-public-list/refs/heads/main/V2Ray-Config-By-EbraSha-All-Type.txt",
]

# 2. 包含过滤正则：只保留优质看视频协议 + 目标地区（含美国、加拿大、俄罗斯等）
INCLUDE_REGEX = r"(?i)hy2|hysteria|reality|vless|us|ca|ru|hk|sg|jp|tw|美国|加拿大|俄罗斯|俄国|香港|新加坡|日本|台湾"

# 3. 排除过滤正则：剔除导致 Karing 报错的 blake3 加密、广告节点和无效文本
EXCLUDE_REGEX = r"(?i)blake3|aes-256-gcm|官网|网站|到期|剩余|群|通知|公告|广告|freefq"

# ================= 测速与延迟过滤参数 =================
MAX_DELAY_MS = 500  # 🎯 目标延迟门槛：只保留 500 毫秒以内的节点
TIMEOUT = 0.2  # 超时时间同步缩短为 0.2 秒（即 200ms），超过此时间直接断开
CONCURRENCY_LIMIT = 400  # 并发测速上限


def decode_content(content):
    """尝试多种方式解码节点数据"""
    content_str = content.decode("utf-8", errors="ignore").strip()
    try:
        missing_padding = len(content_str) % 4
        if missing_padding:
            content_str += "=" * (4 - missing_padding)
        decoded = base64.b64decode(content_str).decode("utf-8", errors="ignore")
        return decoded.splitlines()
    except Exception:
        return content_str.splitlines()


def parse_node(node_str):
    """解析主流代理协议的域名/IP与端口"""
    try:
        if node_str.startswith("vmess://"):
            b64_data = node_str.split("://")[-1].strip()
            b64_data += "=" * (-len(b64_data) % 4)
            config = json.loads(base64.b64decode(b64_data).decode("utf-8"))
            return config.get("add"), int(config.get("port", 0))

        elif node_str.startswith(
            (
                "vless://",
                "ss://",
                "ssr://",
                "trojan://",
                "hy2://",
                "hysteria2://",
                "hysteria://",
            )
        ):
            parsed = urlparse(node_str)
            host = parsed.hostname
            port = parsed.port

            if not host and "@" in parsed.netloc:
                host_port = parsed.netloc.split("@")[-1].split(":")
                if len(host_port) == 2:
                    return host_port[0], int(host_port[1])
            if host and port:
                return host, int(port)
    except Exception:
        pass
    return None, None


# ================= 🛠️ 核心改动：带延迟计算的异步 TCP 测试 =================
async def test_tcp_delay(host, port, semaphore):
    """测试节点连接延迟，超过 MAX_DELAY_MS 则返回失败"""
    if not host or not port:
        return False

    async with semaphore:
        try:
            # 1. 异步域名解析
            loop = asyncio.get_event_loop()
            ip = await loop.run_in_executor(
                None, lambda: socket.gethostbyname(host)
            )

            # 2. 记录开始时间（高精度时间戳）
            start_time = time.perf_counter()

            # 3. 尝试建立 TCP 握手
            _, writer = await asyncio.wait_for(
                asyncio.open_connection(ip, port), timeout=TIMEOUT
            )

            # 4. 计算消耗时间并转换为毫秒
            delay_ms = (time.perf_counter() - start_time) * 1000

            writer.close()
            await writer.wait_closed()

            # 5. 严格过滤：只有延迟小于设定值才算通过
            if delay_ms <= MAX_DELAY_MS:
                return True
        except Exception:
            pass
        return False


async def filter_low_latency_nodes(nodes):
    """批量筛选低延迟节点"""
    semaphore = asyncio.Semaphore(CONCURRENCY_LIMIT)
    tasks = []

    print(
        f"⚡ 开始对 {len(nodes)} 个初筛节点进行网络连通测试（目标延迟：小于 {MAX_DELAY_MS}ms）..."
    )

    for node in nodes:
        host, port = parse_node(node)
        tasks.append(test_tcp_delay(host, port, semaphore))

    results = await asyncio.gather(*tasks)

    # 仅保留低延迟的活节点
    fast_nodes = [node for node, is_fast in zip(nodes, results) if is_fast]
    return fast_nodes


# ================= ⚡ 主程序 =================
def main():
    all_nodes = []

    print("开始在后台下载并清洗巨量节点...")

    for url in SOURCES:
        try:
            req = urllib.request.Request(
                url,
                headers={
                    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
                },
            )
            with urllib.request.urlopen(req, timeout=45) as response:
                nodes = decode_content(response.read())
                all_nodes.extend(nodes)
                print(f"成功读取源: {url[:40]}... 提取到 {len(nodes)} 个原始节点")
        except Exception as e:
            print(f"提取源失败 {url[:40]}... 错误信息: {e}")

    # 去除完全重复的节点
    all_nodes = list(set(all_nodes))
    filtered_nodes = []

    # 核心过滤逻辑：将数万个节点精简，减轻 Karing 压力
    for node in all_nodes:
        node = node.strip()
        if not node or not (
            node.startswith("vmess://")
            or node.startswith("vless://")
            or node.startswith("ss://")
            or node.startswith("ssr://")
            or node.startswith("trojan://")
            or node.startswith("hy2://")
            or node.startswith("hysteria2://")
        ):
            continue

        if re.search(INCLUDE_REGEX, node):
            if not re.search(EXCLUDE_REGEX, node):
                filtered_nodes.append(node)

    # --- 🛠️ 驱动低延迟过滤 ---
    fast_nodes = asyncio.run(filter_low_latency_nodes(filtered_nodes))

    # 重新打包成标准的 Base64 订阅格式
    output_str = "\n".join(fast_nodes)
    encoded_output = base64.b64encode(output_str.encode("utf-8")).decode(
        "utf-8"
    )

    # 将清洗干净的最终订阅写入文件
    with open("sub_filtered.txt", "w") as f:
        f.write(encoded_output)

    print(f"\n✨ 后台清洗与低延迟测速大功告成！")
    print(f"📊 原始总数: {len(all_nodes)}")
    print(f"📉 文本初筛后: {len(filtered_nodes)}")
    print(f"🏆 延迟小于 {MAX_DELAY_MS}ms 的极速节点数: {len(fast_nodes)}")
    print(
        f"💡 节点库已成功瘦身！Karing 加载速度和网络响应都将达到巅峰状态。"
    )


if __name__ == "__main__":
    main()
