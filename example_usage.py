import asyncio
import random
import os
import json

from comfy_library import config
from comfy_library.client import ComfyUIClient
from comfy_library.workflow import ComfyWorkflow

# Part 1: 服务器配置
COMFYUI_URLS = ["http://127.0.0.1:8188"]

# 使用asyncio.Queue来实现更健壮的轮询
url_queue = asyncio.Queue()
for url in COMFYUI_URLS:
    url_queue.put_nowait(url)

# Part 2: 核心工作流函数
async def run_workflow(prompt: str, input_image_path: str, output_dir: str = "outputs"):
    current_server_url = await url_queue.get()
    print(f"\n本次执行使用服务器: {current_server_url}")
    # 将URL放回队列以便下次使用
    await url_queue.put(current_server_url)

    # 请确保这些ID与你的工作流JSON文件匹配，其实这个不搞也可以，只是为了方便下面表示
    NODE_MAPPING = {
        "LOAD_IMAGE": '33', "POSITIVE_PROMPT": '6', "NEGATIVE_PROMPT": '7',
        "KSAMPLER": '3', "SAVE_IMAGE": '9', "TEXT_OUTPUT": "69"
    }
    WORKFLOW_JSON_PATH = "example_src/neta_lumina_i2i.json"

    if not all(os.path.exists(p) for p in [input_image_path, WORKFLOW_JSON_PATH]):
        print(f"错误: 确保文件存在: {input_image_path}, {WORKFLOW_JSON_PATH}"); return

    async with ComfyUIClient(current_server_url, proxy=config.PROXY) as client:
        upload_info = await client.upload_file(input_image_path)
        server_filename = upload_info['name']

        workflow = ComfyWorkflow(WORKFLOW_JSON_PATH)
        workflow.add_replacement(NODE_MAPPING["LOAD_IMAGE"], "image", server_filename)
        workflow.add_replacement(NODE_MAPPING["POSITIVE_PROMPT"], "text", prompt)
        workflow.add_replacement(NODE_MAPPING["KSAMPLER"], "seed", random.randint(0, 9999999999))

        # 定义所有你想要的输出
        # 1. 默认下载: 自动查找并下载所有可用的文件
        workflow.add_output_node(NODE_MAPPING["SAVE_IMAGE"])
        
        # 2. 精确提取: 从同一个节点获取文件名
        workflow.add_output_node(NODE_MAPPING["SAVE_IMAGE"], "images[0].filename")
        
        # 3. 提取文本，并测试一个无效的路径以展示容错性
        workflow.add_output_node(NODE_MAPPING["TEXT_OUTPUT"], ["text[0]", "text[99]"]) # text[99] 应该会提示路径不存在

        print("\n开始执行工作流，完成后将一次性返回所有结果...")
        all_results = await client.execute_workflow(workflow, output_dir)

        print("\n工作流全部输出结果")
        # 使用json.dumps美化输出，方便查看
        print(json.dumps(all_results, indent=2, ensure_ascii=False))
        print("输出完毕")


# Part 3: 主函数入口
async def main():
    INPUT_IMAGE = "example_src/upload_img.png"
    PROMPT = "A beautiful cat, cinematic, masterpiece"
    await run_workflow(prompt=PROMPT, input_image_path=INPUT_IMAGE)

if __name__ == "__main__":
    asyncio.run(main())