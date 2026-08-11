import urllib.request
import base64
import re

# 1. 填入你提供的那 3 个巨大的开源项目订阅源
SOURCES = [
    "https://githubusercontent.com",
    "https://bulinkbulink.com",
    "https://githubusercontent.com"
]

# 2. 包含过滤正则：只保留优质看视频协议 + 目标地区（含美国、加拿大、俄罗斯等）
INCLUDE_REGEX = r"(?i)hy2|hysteria|reality|vless|us|ca|ru|hk|sg|jp|tw|美国|加拿大|俄罗斯|俄国|香港|新加坡|日本|台湾"

# 3. 排除过滤正则：剔除导致 Karing 报错的 blake3 加密、广告节点和无效文本
EXCLUDE_REGEX = r"(?i)blake3|aes-256-gcm|官网|网站|到期|剩余|群|通知|公告|广告|freefq"

def decode_content(content):
    """尝试多种方式解码节点数据"""
    # 移除可能存在的首尾空格或干扰字符
    content_str = content.decode('utf-8', errors='ignore').strip()
    
    # 尝试 Base64 解码
    try:
        # 补齐 Base64 填充符 '='
        missing_padding = len(content_str) % 4
        if missing_padding:
            content_str += '=' * (4 - missing_padding)
        decoded = base64.b64decode(content_str).decode('utf-8', errors='ignore')
        return decoded.splitlines()
    except Exception:
        # 如果不是 Base64，直接按明文换行切分
        return content_str.splitlines()

def main():
    all_nodes = []
    
    print("开始在后台下载并清洗巨量节点...")
    
    for url in SOURCES:
        try:
            req = urllib.request.Request(
                url, 
                headers={'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'}
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

    # 核心过滤逻辑：将数万个节点精简到几百个，减轻 Karing 压力
    for node in all_nodes:
        node = node.strip()
        if not node or not (node.startswith("vmess://") or node.startswith("vless://") or 
                            node.startswith("ss://") or node.startswith("ssr://") or 
                            node.startswith("trojan://") or node.startswith("hy2://") or 
                            node.startswith("hysteria2://")):
            continue
            
        # 1. 检查是否包含我们想要的协议或地区
        if re.search(INCLUDE_REGEX, node):
            # 2. 检查并剔除会报错或广告的节点
            if not re.search(EXCLUDE_REGEX, node):
                filtered_nodes.append(node)

    # 重新打包成标准的 Base64 订阅格式
    output_str = "\n".join(filtered_nodes)
    encoded_output = base64.b64encode(output_str.encode('utf-8')).decode('utf-8')

    # 将清洗干净的最终订阅写入文件
    with open("sub_filtered.txt", "w") as f:
        f.write(encoded_output)
        
    print(f"\n✨ 后台清洗大功告成！")
    print(f"📊 原始总节点数: {len(all_nodes)} -> 过滤后精简节点数: {len(filtered_nodes)}")
    print("Karing 客户端现在可以在 1 秒内瞬间完成更新了！")

if __name__ == "__main__":
    main()
