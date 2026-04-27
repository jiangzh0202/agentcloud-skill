#!/usr/bin/env python3
"""
AgentCloud CLI — 一键接入 AI Agent 云存储

用法:
  python3 agentcloud.py register [--name NAME]
  python3 agentcloud.py upload FILE [--key KEY]
  python3 agentcloud.py download FILE_ID -o OUTPUT [--key KEY]
  python3 agentcloud.py list [--key KEY]
  python3 agentcloud.py share FILE_ID [--expires SECONDS] [--key KEY]
  python3 agentcloud.py me [--key KEY]

不传 --key 时，会从环境变量 AGENTCLOUD_KEY 读取。
首次注册会保存配置到 ~/.agentcloud/config.json。
"""

import argparse
import json
import os
import sys
from pathlib import Path

try:
    import requests
except ImportError:
    print("❌ 请先安装 requests: pip install requests")
    sys.exit(1)

BASE_URL = "https://api.traceclaw.cn/api/v1"
CONFIG_DIR = Path.home() / ".agentcloud"
CONFIG_FILE = CONFIG_DIR / "config.json"


def _load_key(args_key):
    """从参数、环境变量或配置文件获取 API Key"""
    if args_key:
        return args_key
    env_key = os.environ.get("AGENTCLOUD_KEY")
    if env_key:
        return env_key
    if CONFIG_FILE.exists():
        config = json.loads(CONFIG_FILE.read_text())
        key = config.get("api_key")
        if key:
            return key
    return None


def _save_config(data):
    """保存注册信息到配置文件"""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    if CONFIG_FILE.exists():
        config = json.loads(CONFIG_FILE.read_text())
        config.update(data)
    else:
        config = data
    CONFIG_FILE.write_text(json.dumps(config, indent=2, ensure_ascii=False))
    print(f"📁 配置已保存: {CONFIG_FILE}")


def _headers(api_key):
    return {"X-Agent-Key": api_key}


def cmd_register(args):
    """注册新 Agent"""
    name = args.name or f"agent-{os.getpid()}"
    print(f"🔐 注册 Agent: {name}")
    try:
        r = requests.post(f"{BASE_URL}/agents", json={"name": name}, timeout=15)
        r.raise_for_status()
        data = r.json()
    except requests.exceptions.RequestException as e:
        print(f"❌ 注册失败: {e}")
        return

    _save_config({
        "agent_id": data["agent_id"],
        "api_key": data["api_key"],
        "name": data["name"],
    })

    print(f"\n✅ 注册成功!")
    print(f"   Agent ID: {data['agent_id']}")
    print(f"   API Key:  {data['api_key']}  ⚠️ 请妥善保存")
    print(f"   名称:     {data['name']}")
    print(f"\n💡 设置环境变量方便后续使用:")
    print(f"   export AGENTCLOUD_KEY={data['api_key']}")

    # 测试连通性
    print(f"\n📡 测试连接...")
    try:
        r2 = requests.get(f"{BASE_URL}/agents/me", headers=_headers(data["api_key"]), timeout=10)
        r2.raise_for_status()
        info = r2.json()
        print(f"   存储: {info.get('used_storage_mb', 0):.1f}MB / {info.get('total_storage_mb', 30)}MB")
        print(f"   会员: {'已开通' if info.get('subscription_end') else '免费用户'}")
    except Exception as e:
        print(f"   ⚠️ 连接测试失败: {e}")


def cmd_upload(args):
    """上传文件"""
    api_key = _load_key(args.key)
    if not api_key:
        print("❌ 未设置 API Key。请先运行 register 或设置 AGENTCLOUD_KEY")
        return

    filepath = args.file
    if not os.path.exists(filepath):
        print(f"❌ 文件不存在: {filepath}")
        return

    filename = os.path.basename(filepath)
    filesize = os.path.getsize(filepath)
    print(f"📤 上传: {filename} ({_fmt_size(filesize)})")

    try:
        with open(filepath, "rb") as f:
            r = requests.post(
                f"{BASE_URL}/files/upload",
                files={"file": (filename, f)},
                headers=_headers(api_key),
                timeout=120
            )
        r.raise_for_status()
        data = r.json()
        print(f"✅ 上传成功!")
        print(f"   File ID: {data['file_id']}")
        print(f"   大小:    {_fmt_size(data.get('file_size', filesize))}")
        # 自动生成分享命令提示
        print(f"\n💡 分享给其他 Agent:")
        print(f"   python3 agentcloud.py share {data['file_id']}")
    except requests.exceptions.RequestException as e:
        print(f"❌ 上传失败: {e}")
        if hasattr(e, 'response') and e.response is not None:
            try:
                print(f"   服务器返回: {e.response.json()}")
            except Exception:
                print(f"   服务器返回: {e.response.text[:200]}")


def cmd_download(args):
    """下载文件"""
    api_key = _load_key(args.key)
    if not api_key:
        print("❌ 未设置 API Key。请先运行 register 或设置 AGENTCLOUD_KEY")
        return

    file_id = args.file_id
    output = args.output or f"download_{file_id}"

    print(f"📥 下载: {file_id}")
    try:
        r = requests.get(
            f"{BASE_URL}/files/download/{file_id}",
            headers=_headers(api_key),
            timeout=120,
            stream=True
        )
        r.raise_for_status()

        # 尝试获取文件名
        content_disp = r.headers.get("Content-Disposition", "")
        if "filename=" in content_disp:
            output = content_disp.split("filename=")[-1].strip('"').strip("'")

        with open(output, "wb") as f:
            for chunk in r.iter_content(chunk_size=8192):
                f.write(chunk)

        size = os.path.getsize(output)
        print(f"✅ 下载成功!")
        print(f"   文件: {output}")
        print(f"   大小: {_fmt_size(size)}")
    except requests.exceptions.RequestException as e:
        print(f"❌ 下载失败: {e}")
        if hasattr(e, 'response') and e.response is not None:
            print(f"   HTTP {e.response.status_code}")


def cmd_list(args):
    """列出文件"""
    api_key = _load_key(args.key)
    if not api_key:
        print("❌ 未设置 API Key。请先运行 register 或设置 AGENTCLOUD_KEY")
        return

    print("📂 文件列表")
    try:
        r = requests.get(f"{BASE_URL}/files", headers=_headers(api_key), timeout=15)
        r.raise_for_status()
        files = r.json()
    except requests.exceptions.RequestException as e:
        print(f"❌ 查询失败: {e}")
        return

    if not files:
        print("   (空)")
        return

    print(f"   共 {len(files)} 个文件:")
    for f in files:
        created = f.get("created_at", "")[:19] if f.get("created_at") else "?"
        print(f"   [{f['file_id'][:8]}...] {f['filename']}  "
              f"{_fmt_size(f['file_size'])}  {created}")


def cmd_share(args):
    """创建分享链接"""
    api_key = _load_key(args.key)
    if not api_key:
        print("❌ 未设置 API Key。请先运行 register 或设置 AGENTCLOUD_KEY")
        return

    file_id = args.file_id
    expires = args.expires or 86400  # 默认24小时

    print(f"🔗 创建分享链接: {file_id} (有效期 {expires} 秒)")
    try:
        r = requests.post(
            f"{BASE_URL}/files/{file_id}/share",
            json={"expires_in": expires},
            headers=_headers(api_key),
            timeout=15
        )
        r.raise_for_status()
        data = r.json()
        share_url = f"{BASE_URL}/files/shared/{data['share_token']}"
        print(f"✅ 分享链接:")
        print(f"   {share_url}")
        print(f"\n💡 其他 Agent 可通过此链接直接下载，无需认证")
    except requests.exceptions.RequestException as e:
        print(f"❌ 分享失败: {e}")
        if hasattr(e, 'response') and e.response is not None:
            try:
                print(f"   服务器返回: {e.response.json()}")
            except Exception:
                print(f"   服务器返回: {e.response.text[:200]}")


def cmd_me(args):
    """查看 Agent 信息"""
    api_key = _load_key(args.key)
    if not api_key:
        print("❌ 未设置 API Key。请先运行 register 或设置 AGENTCLOUD_KEY")
        return

    try:
        r = requests.get(f"{BASE_URL}/agents/me", headers=_headers(api_key), timeout=15)
        r.raise_for_status()
        info = r.json()
    except requests.exceptions.RequestException as e:
        print(f"❌ 查询失败: {e}")
        return

    print(f"📊 Agent 信息")
    print(f"   ID:        {info.get('agent_id', '?')}")
    print(f"   名称:      {info.get('name', '?')}")
    print(f"   存储:      {info.get('used_storage_mb', 0):.1f}MB / {info.get('total_storage_mb', '?')}MB")
    sub_end = info.get("subscription_end")
    if sub_end:
        print(f"   会员到期:  {sub_end[:19] if isinstance(sub_end, str) else sub_end}")
    else:
        print(f"   会员:      免费用户 (30MB)")


def _fmt_size(size_bytes):
    """格式化文件大小"""
    if size_bytes < 1024:
        return f"{size_bytes}B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f}KB"
    else:
        return f"{size_bytes / 1024 / 1024:.1f}MB"


def main():
    parser = argparse.ArgumentParser(description="AgentCloud CLI - AI Agent 云存储")
    subparsers = parser.add_subparsers(dest="command", help="可用命令")

    # register
    p_register = subparsers.add_parser("register", help="注册新 Agent")
    p_register.add_argument("--name", default=None, help="Agent 名称")

    # upload
    p_upload = subparsers.add_parser("upload", help="上传文件")
    p_upload.add_argument("file", help="文件路径")
    p_upload.add_argument("--key", default=None, help="API Key")

    # download
    p_download = subparsers.add_parser("download", help="下载文件")
    p_download.add_argument("file_id", help="文件 ID")
    p_download.add_argument("-o", "--output", default=None, help="输出路径")
    p_download.add_argument("--key", default=None, help="API Key")

    # list
    p_list = subparsers.add_parser("list", help="列出文件")
    p_list.add_argument("--key", default=None, help="API Key")

    # share
    p_share = subparsers.add_parser("share", help="创建分享链接")
    p_share.add_argument("file_id", help="文件 ID")
    p_share.add_argument("--expires", type=int, default=86400, help="有效期（秒，默认86400）")
    p_share.add_argument("--key", default=None, help="API Key")

    # me
    p_me = subparsers.add_parser("me", help="查看 Agent 信息")
    p_me.add_argument("--key", default=None, help="API Key")

    args = parser.parse_args()

    if args.command == "register":
        cmd_register(args)
    elif args.command == "upload":
        cmd_upload(args)
    elif args.command == "download":
        cmd_download(args)
    elif args.command == "list":
        cmd_list(args)
    elif args.command == "share":
        cmd_share(args)
    elif args.command == "me":
        cmd_me(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
