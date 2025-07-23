import httpx, json, asyncio, uuid, os, aiofiles, websockets, mimetypes
from typing import Dict, Any, Optional, List, AsyncGenerator
from .config import (
    HTTP_TIMEOUT, WS_OPEN_TIMEOUT, WS_PING_INTERVAL,
    WS_PING_TIMEOUT, WORKFLOW_EXECUTION_TIMEOUT
)
from .workflow import ComfyWorkflow

class ComfyUIClient:
    def __init__(self, base_url: str, proxy: Optional[str] = None):
        self.base_url = base_url.rstrip('/')
        self.client_id = str(uuid.uuid4())
        ws_protocol = "ws" if self.base_url.startswith("http:") else "wss"
        host = self.base_url.split("://")[1]
        self.ws_address = f"{ws_protocol}://{host}/ws?clientId={self.client_id}"
        proxies = {"http://": proxy, "https://": proxy} if proxy else None
        self._client = httpx.AsyncClient(proxies=proxies, timeout=HTTP_TIMEOUT, follow_redirects=True)

    async def __aenter__(self): return self
    async def __aexit__(self, exc_type, exc_val, exc_tb): await self.close()
    async def close(self): await self._client.aclose()
    def _get_http_url(self, endpoint: str) -> str: return f"{self.base_url}{endpoint}"

    async def execute_workflow(self, workflow: ComfyWorkflow, output_dir: str = "outputs") -> AsyncGenerator[Dict[str, str], None]:
        wf_to_run = await self.load_and_prepare_workflow(workflow.workflow_json_path, workflow._replacements)
        prompt_id = await self.queue_prompt(wf_to_run)
        if not prompt_id: return
        completed = await self.wait_for_prompt_completion(prompt_id)
        if not completed: print("❌ 任务未能成功完成，流程终止。"); return
        print(f"\n任务完成，准备流式下载 {len(workflow._output_nodes)} 个节点的输出")
        history = await self.get_history(prompt_id)
        total_files_downloaded = 0
        for node_id in workflow._output_nodes:
            async for file_path in self.download_output_files(history, node_id, output_dir):
                total_files_downloaded += 1
                yield {"node_id": node_id, "file_path": file_path}
        if total_files_downloaded > 0: print(f"\n🎉🎉🎉 工作流成功完成! 共 {total_files_downloaded} 个文件已下载。")
        else: print("\n⚠️ 工作流已结束，但没有文件被下载。")

    async def upload_file(self, file_path: str, server_subfolder: str = "", overwrite: bool = True) -> Dict[str, Any]:
        if not os.path.exists(file_path): raise FileNotFoundError(f"文件未找到: {file_path}")
        print(f"准备上传文件: {os.path.basename(file_path)}...")
        filename = os.path.basename(file_path)
        mime_type, _ = mimetypes.guess_type(filename)
        if mime_type is None: mime_type = 'application/octet-stream'
        payload = {'overwrite': str(overwrite).lower(), 'subfolder': server_subfolder}
        url = self._get_http_url("/upload/image")
        try:
            with open(file_path, 'rb') as f:
                files = {'image': (filename, f.read(), mime_type)}
                response = await self._client.post(url, files=files, data=payload)
                response.raise_for_status()
            result = response.json()
            print(f"✅ 文件上传成功. 服务器文件名: {result['name']}")
            return result
        except (httpx.RequestError, httpx.HTTPStatusError) as e:
            print(f"❌ 上传文件时发生网络或HTTP错误: {e}")
            if isinstance(e, httpx.HTTPStatusError): print(f"   - 服务器响应: {e.response.text}")
            raise
    
    @classmethod
    async def load_and_prepare_workflow(cls, workflow_path: str, replacements: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
        print(f"正在加载工作流: {os.path.basename(workflow_path)}")
        if not os.path.exists(workflow_path): raise FileNotFoundError(f"工作流文件未找到: {workflow_path}")
        async with aiofiles.open(workflow_path, 'r', encoding='utf-8') as f: workflow = json.loads(await f.read())
        print("正在动态替换节点内容...")
        for node_id, inputs_to_replace in replacements.items():
            if node_id in workflow:
                for input_name, new_value in inputs_to_replace.items():
                    workflow[node_id]['inputs'][input_name] = new_value
                    print(f"   - 节点 '{node_id}' 的输入 '{input_name}' 已更新。")
        return workflow

    async def queue_prompt(self, prepared_workflow: Dict[str, Any]) -> str:
        print("正在将工作流提交到队列...")
        url = self._get_http_url("/prompt")
        payload = {"prompt": prepared_workflow, "client_id": self.client_id}
        try:
            response = await self._client.post(url, json=payload)
            response.raise_for_status()
            prompt_id = response.json().get("prompt_id")
            print(f"✅ 工作流提交成功. Prompt ID: {prompt_id}")
            return prompt_id
        except (httpx.RequestError, httpx.HTTPStatusError) as e:
            print(f"❌ 提交工作流时发生网络或HTTP错误: {e}")
            raise

    async def wait_for_prompt_completion(self, prompt_id: str, timeout: Optional[int] = None) -> bool:
        effective_timeout = timeout if timeout is not None else WORKFLOW_EXECUTION_TIMEOUT
        print(f"开始通过 WebSocket 监听任务 {prompt_id} 的执行状态 (总超时: {effective_timeout}s)...")
        try:
            async with websockets.connect(self.ws_address, ping_interval=WS_PING_INTERVAL, ping_timeout=WS_PING_TIMEOUT, open_timeout=WS_OPEN_TIMEOUT) as ws:
                print("WebSocket 连接成功建立。")
                while True:
                    try:
                        message_data = await asyncio.wait_for(ws.recv(), timeout=effective_timeout)
                        if isinstance(message_data, str):
                            message = json.loads(message_data)
                            if message.get('type') == 'progress':
                                data = message.get('data', {})
                                print(f"  - 进度更新: 节点 {data.get('node', 'N/A')} - 步数 {data.get('value', 0)}/{data.get('max', 1)}")
                            elif message.get('type') == 'executing' and message.get('data', {}).get('prompt_id') == prompt_id and message['data'].get('node') is None:
                                print("✅ 任务执行流程结束。")
                                return True
                    except asyncio.TimeoutError:
                        print(f"\n❌ 监听消息超时 ({effective_timeout}秒)，未收到新消息。")
                        return False
        except Exception as e:
            print(f"\n❌ 监听 WebSocket 时发生错误: {e}")
        return False

    async def get_history(self, prompt_id: str) -> Dict[str, Any]:
        url = self._get_http_url(f"/history/{prompt_id}")
        try:
            response = await self._client.get(url)
            response.raise_for_status()
            return response.json().get(prompt_id, {})
        except Exception as e:
            print(f"❌ 获取历史记录时发生错误: {e}")
            return {}
            
    async def download_output_files(self, history: Dict[str, Any], target_node_id: str, output_dir: str) -> AsyncGenerator[str, None]:
        node_output = history.get('outputs', {}).get(target_node_id)
        if not node_output or 'images' not in node_output: return
        for image_data in node_output.get('images', []):
            file_path = await self._download_file(image_data, output_dir)
            if file_path: yield file_path

    async def _download_file(self, file_data: Dict[str, str], target_dir: str) -> Optional[str]:
        filename, subfolder, file_type = file_data.get('filename'), file_data.get('subfolder', ''), file_data.get('type')
        if not filename or not file_type: return None
        output_sub_dir = os.path.join(target_dir, file_type); os.makedirs(output_sub_dir, exist_ok=True)
        url = self._get_http_url("/view")
        params = {"filename": filename, "subfolder": subfolder, "type": file_type}
        try:
            async with self._client.stream("GET", url, params=params) as response:
                response.raise_for_status()
                output_path = os.path.join(output_sub_dir, filename)
                async with aiofiles.open(output_path, 'wb') as f:
                    async for chunk in response.aiter_bytes(): await f.write(chunk)
                return output_path
        except Exception as e:
            print(f"   -> ❌ 下载或保存 {filename} 时发生错误: {e}")
            return None
            
    async def view_tasks(self) -> Dict[str, List[Dict]]:
        try:
            queue_res = await self._client.get(self._get_http_url("/queue"))
            queue_res.raise_for_status()
            queue_data = queue_res.json()
            running_tasks = [{"prompt_id": item[1]} for item in queue_data.get('queue_running', []) if isinstance(item, list) and len(item) > 1]
            queued_tasks = [{"prompt_id": item[1]} for item in queue_data.get('queue_pending', []) if isinstance(item, list) and len(item) > 1]
            history_res = await self._client.get(self._get_http_url("/history"))
            history_res.raise_for_status()
            history_data = history_res.json()
            sortable_history = []
            for prompt_id, result in history_data.items():
                completion_timestamp = 0
                messages = result.get("status", {}).get("messages", [])
                for msg in messages:
                    if isinstance(msg, list) and len(msg) > 1 and msg[0] == 'execution_success':
                        if isinstance(msg[1], dict) and 'timestamp' in msg[1]:
                            completion_timestamp = msg[1]['timestamp']
                            break
                sortable_history.append({"prompt_id": prompt_id, "result": result, "timestamp": completion_timestamp})
            sortable_history.sort(key=lambda x: x.get('timestamp', 0), reverse=True)
            completed_tasks = []
            running_and_queued_ids = {t['prompt_id'] for t in running_tasks} | {t['prompt_id'] for t in queued_tasks}
            for item in sortable_history:
                prompt_id = item['prompt_id']
                if prompt_id in running_and_queued_ids: continue
                outputs_preview = "无输出"
                if 'outputs' in item['result']:
                    for node_output in item['result']['outputs'].values():
                        if 'images' in node_output and node_output['images']:
                           outputs_preview = node_output['images'][0]['filename']
                           break
                completed_tasks.append({"prompt_id": prompt_id, "outputs_preview": outputs_preview})
            return {"running": running_tasks, "queued": queued_tasks, "completed": completed_tasks}
        except Exception as e:
            print(f"❌ 获取任务列表时出错: {e}")
            return {"running": [], "queued": [], "completed": []}

    async def interrupt_running_task(self) -> bool:
        print("正尝试中断当前任务...")
        try:
            response = await self._client.post(self._get_http_url("/interrupt"))
            response.raise_for_status()
            return True
        except Exception as e:
            print(f"❌ 发送中断请求失败: {e}")
            return False

    async def delete_queued_tasks(self, prompt_ids: List[str]) -> bool:
        print(f"正尝试从队列中删除任务: {prompt_ids}...")
        try:
            response = await self._client.post(self._get_http_url("/queue"), json={"delete": prompt_ids})
            response.raise_for_status()
            return True
        except Exception as e:
            print(f"❌ 发送删除请求失败: {e}")
            return False