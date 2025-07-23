import asyncio
import random
import os

from comfy_library import config
from comfy_library.client import ComfyUIClient
from comfy_library.workflow import ComfyWorkflow

# Part 1: 服务器和轮询配置
COMFYUI_URLS = [
    "http://127.0.0.1:8188",
]

def get_next_url(url_list):
    """一个无限循环的URL生成器，实现轮询。"""
    index = 0
    while True:
        yield url_list[index]
        index = (index + 1) % len(url_list)

url_cycler = get_next_url(COMFYUI_URLS)

# Part 2: 核心工作流函数
async def run_workflow(
    prompt: str,
    input_image_path: str,
    output_dir: str = ""
):
    current_server_url = next(url_cycler)
    print(f"\n本次执行使用服务器: {current_server_url}")

    NODE_MAPPING = {
        "LOAD_IMAGE": '33', "POSITIVE_PROMPT": '6', "NEGATIVE_PROMPT": '7',
        "KSAMPLER": '3', "SAVE_IMAGE": '9',
    } # 这边是你工作流中节点对应的序号
    WORKFLOW_JSON_PATH = "ComfyUI_08412_ (1).json"# 这是你工作流json文件路径

    if not all(os.path.exists(p) for p in [input_image_path, WORKFLOW_JSON_PATH]):
        print(f"错误: 确保文件存在: {input_image_path}, {WORKFLOW_JSON_PATH}"); return

    async with ComfyUIClient(current_server_url, config.PROXY) as client:
        upload_info = await client.upload_file(input_image_path)
        server_filename = upload_info['name']
        workflow = ComfyWorkflow(WORKFLOW_JSON_PATH)

        workflow.add_replacement(NODE_MAPPING["LOAD_IMAGE"], "image", server_filename)# 这边第一个值是节点序号，第二个值是节点参数名，第三个值是参数值
        workflow.add_replacement(NODE_MAPPING["POSITIVE_PROMPT"], "text", prompt)
        workflow.add_replacement(NODE_MAPPING["NEGATIVE_PROMPT"], "text", "bad quality, blurry")
        workflow.add_replacement(NODE_MAPPING["KSAMPLER"], "seed", random.randint(0, 9999999999))
        workflow.add_replacement(NODE_MAPPING["KSAMPLER"], "denoise", 1.0)# 重绘幅度，1代表直接文生图
        workflow.add_output_node(NODE_MAPPING["SAVE_IMAGE"])# 这边是你工作流中需要下载的输出节点序号
        
        # 使用 async for 循环处理流式结果
        print("\n开始执行工作流并等待流式下载结果")
        async for result in client.execute_workflow(workflow, output_dir):
            node_id = result["node_id"]
            file_path = result["file_path"]
            print(f"✅ 下载完成! 节点 '{node_id}' 的结果已保存到: {file_path}")

# Part 3: 脚本直接运行时的入口
async def main():
    INPUT_IMAGE = "ComfyUI_temp_gpxyb_00805_.png"# 输入图片路径
    PROMPT = "A beautiful cat, cinematic, masterpiece"
    
    await run_workflow(
        prompt=PROMPT,
        input_image_path=INPUT_IMAGE
    )

if __name__ == "__main__":
    asyncio.run(main())