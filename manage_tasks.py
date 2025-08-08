import asyncio
import argparse

from comfy_library import config
from comfy_library.client import ComfyUIClient

async def main():
    parser = argparse.ArgumentParser(
        description="一个用于管理 ComfyUI 任务队列的命令行工具。",
        formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument(
        "--server", type=str, required=True,
        help="要管理的 ComfyUI 服务器的完整URL地址。\n示例: http://127.0.0.1:8188"
    )
    subparsers = parser.add_subparsers(dest="command", required=True, help="可用的命令")
    subparsers.add_parser("view", help="查看所有任务的状态 (运行中, 排队中, 已完成)。")
    subparsers.add_parser("interrupt", help="中断当前正在运行的任务。")
    parser_delete = subparsers.add_parser("delete", help="从队列中删除一个或多个指定的、还未开始的任务。")
    parser_delete.add_argument("prompt_ids", nargs='+', help="一个或多个要从队列中删除的任务ID。")
    args = parser.parse_args()

    async with ComfyUIClient(base_url=args.server, proxy=config.PROXY) as client:
        print(f"正在连接到服务器: {args.server}")
        if args.command == "view":
            tasks = await client.view_tasks()
            print("\n[🏃‍➡️ Running]")
            if tasks['running']: [print(f" - ID: {task['prompt_id']}") for task in tasks['running']]
            else: print(" (无)")
            print("\n[⏳ Queued]")
            if tasks['queued']: [print(f" - ID: {task['prompt_id']}") for task in tasks['queued']]
            else: print(" (无)")
            print("\n[✅ Completed] (按最新完成的顺序显示, 最多10条)")
            if tasks['completed']:
                for task in tasks['completed'][:10]: print(f" - ID: {task['prompt_id']} (输出: {task['outputs_preview']})")
                if len(tasks['completed']) > 10: print("  ...")
            else: print(" (无)")
        elif args.command == "interrupt":
            if await client.interrupt_running_task(): print("✅ 中断请求已成功发送。")
            else: print("❌ 中断请求失败。")
        elif args.command == "delete":
            if await client.delete_queued_tasks(args.prompt_ids): print("✅ 删除请求已成功发送。")
            else: print("❌ 删除请求失败。")

if __name__ == "__main__":
    asyncio.run(main())