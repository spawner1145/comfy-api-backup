import asyncio
import random
import os
import json

from comfy_library import config
from comfy_library.client import ComfyUIClient
from comfy_library.workflow import ComfyWorkflow

"""网页运行一次工作流后，在/history底部可以发现如下输出
    "outputs": {
      "118": {
        "images": [
          {
            "filename": "ComfyUI_00049_.png",
            "subfolder": "",
            "type": "output"
          }
        ]
      },
      "102": {
        "text": [
          "896"
        ]
      },
      "69": {
        "text": [
          "101x608x896"
        ]
      },
      "127": {
        "images": [
          {
            "filename": "ComfyUI_00001_.mp4",
            "subfolder": "video",
            "type": "output"
          }
        ],
        "animated": [true]
      },
      "125": {
        "images": [
          {
            "filename": "ComfyUI_temp_ygoyd_00007_.png",
            "subfolder": "",
            "type": "temp"
          }
        ]
      },
      "60": {
        "gifs": [
          {
            "filename": "WanVideo2_2_I2V_00025.mp4",
            "subfolder": "",
            "type": "output",
            "format": "video/h264-mp4",
            "frame_rate": 16,
            "workflow": "WanVideo2_2_I2V_00025.png",
            "fullpath": "/root/autodl-tmp/ComfyUI/output/WanVideo2_2_I2V_00025.mp4"
          }
        ]
      },
      "101": {
        "text": [
          "608"
        ]
      }
    },
"""

"""最终会类似如下输出：
🎉🎉🎉 工作流成功完成! 共处理 9 个输出项。

工作流全部输出结果
{
  "60": {
    "gifs": "D:/Downloads/comfy-api-backup/outputs/output/WanVideo2_2_I2V_00031.mp4"
  },
  "69": {
    "text[0]": "101x608x896"
  },
  "101": {
    "text[0]": "608"
  },
  "102": {
    "text[0]": "896"
  },
  "118": {
    "DEFAULT_DOWNLOAD": "D:/Downloads/comfy-api-backup/outputs/output/ComfyUI_00054_.png"
  },
  "125": {
    "images": "D:/Downloads/comfy-api-backup/outputs/temp/ComfyUI_temp_ygoyd_00012_.png"
  },
  "127": {
    "images": "D:/Downloads/comfy-api-backup/outputs/output/ComfyUI_00007_.mp4",
    "animated[0]": "True",
    "animated[99]": "指定的JSON路径不存在"
  }
}
输出完毕
"""

# Part 1: 服务器配置
COMFYUI_URLS = ["http://127.0.0.1:8188"]

# 使用asyncio.Queue来实现更健壮的轮询
url_queue = asyncio.Queue()
for url in COMFYUI_URLS:
    url_queue.put_nowait(url)

# Part 2: 核心工作流函数
async def run_workflow(output_dir: str = "outputs"):
    """
    执行工作流并获取所有预定义的输出
    """
    current_server_url = await url_queue.get()
    print(f"\n本次执行使用服务器: {current_server_url}")
    # 将URL放回队列以便下次使用
    await url_queue.put(current_server_url)

    # 您的工作流JSON文件的路径
    WORKFLOW_JSON_PATH = "example_src/wan22_i2v_test.json" 

    if not os.path.exists(WORKFLOW_JSON_PATH):
        print(f"错误: 找不到工作流文件: {WORKFLOW_JSON_PATH}"); return

    # 由于这个复杂工作流的输入（如提示词）是硬编码在文件里的
    # 我们这里就不再需要动态替换（add_replacement）了
    # 如果想让它动态化，可以像example_usage.py的例子一样添加add_replacement来替换提示词
    
    async with ComfyUIClient(current_server_url, proxy=config.PROXY) as client:
        
        workflow = ComfyWorkflow(WORKFLOW_JSON_PATH)

        # 种子一定要和上一次执行不同，否则不会返回内容
        workflow.add_replacement("116", "seed", random.randint(0, 9999999999))
        workflow.add_replacement("98", "seed", random.randint(0, 9999999999))
        
        # 1. 从节点 "60" (VHS_VideoCombine) 获取 "gifs" 列表中的所有文件
        #    这将触发默认下载行为，因为我们没有指定更深层的选择器
        workflow.add_output_node("60", "gifs")

        # 2. 从节点 "69" (GetImageSizeAndCount) 获取拼接后的尺寸文本
        workflow.add_output_node("69", "text[0]")

        # 3. 从节点 "101" 和 "102" (easy showAnything) 获取文本
        workflow.add_output_node("101", "text[0]")
        workflow.add_output_node("102", "text[0]")

        # 4. 从节点 "118" (SaveImage) 触发默认下载
        workflow.add_output_node("118")

        # 5. 从节点 "125" (PreviewImage) 下载临时文件
        workflow.add_output_node("125", "images")
        
        # 6. 从节点 "127" (SaveVideo) 下载最终视频，并测试一个无效路径
        workflow.add_output_node("127", [
            "images",                # 有效：下载视频文件
            "animated[0]",           # 有效：获取布尔值
            "animated[99]"           # 无效：测试索引越界
        ])


        # 一次性执行并获取所有结果
        print("\n开始执行工作流，完成后将一次性返回所有结果...")
        all_results = await client.execute_workflow(workflow, output_dir)

        print("\n工作流全部输出结果")
        # 使用json.dumps美化输出，方便查看
        print(json.dumps(all_results, indent=2, ensure_ascii=False))
        print("输出完毕")


# Part 3: 主函数入口
async def main():
    # 因为这个工作流是自包含的（不需要外部输入图片或prompt），
    # 所以我们直接调用 run_workflow 即可。你也可以模仿example_usage.py替换一些东西
    await run_workflow()

if __name__ == "__main__":
    asyncio.run(main())