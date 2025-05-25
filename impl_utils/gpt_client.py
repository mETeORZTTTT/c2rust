import time
import json
import logging
import requests
import os
import re
from datetime import datetime
from openai import OpenAI

class GPT:
    def __init__(self, api_key, model_name="gpt-4o", base_url="https://api.zetatechs.com/v1"):
        self.client = OpenAI(api_key=api_key, base_url=base_url)
        self.model_name = model_name
        self.total_tokens_in = 0
        self.total_tokens_out = 0
        self.call_count = 0
        
        # 用于记录对话历史
        self.conversation_history = []
        
        # 创建日志目录
        self.log_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs", "conversations")
        os.makedirs(self.log_dir, exist_ok=True)
        
        # 创建详细对话目录 - 包含每个会话的具体内容
        self.detailed_log_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs", "detailed")
        os.makedirs(self.detailed_log_dir, exist_ok=True)
        
        # 创建本次对话的唯一标识
        self.session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # 对话轮次计数
        self.turn_count = 0
        
        # 创建详细日志记录器
        self._setup_detailed_logger()
    
    def _setup_detailed_logger(self):
        """设置详细日志记录器"""
        # 创建详细日志记录器
        self.detailed_logger = logging.getLogger(f"detailed_{self.session_id}")
        self.detailed_logger.setLevel(logging.DEBUG)
        self.detailed_logger.propagate = False  # 避免向上传播到root logger
        
        # 创建详细日志文件处理器
        log_filename = f"detailed_{self.session_id}.log"
        log_path = os.path.join(self.detailed_log_dir, log_filename)
        file_handler = logging.FileHandler(log_path, encoding="utf-8", mode='w')
        file_handler.setLevel(logging.DEBUG)
        
        # 设置格式化器
        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        file_handler.setFormatter(formatter)
        
        # 添加处理器
        self.detailed_logger.addHandler(file_handler)
        
        # 记录会话开始信息
        self.detailed_logger.info(f"================================")
        self.detailed_logger.info(f"会话 {self.session_id} 开始 (模型: {self.model_name})")
        self.detailed_logger.info(f"================================")
    
    def ask(self, messages, temperature=0.2, max_retries=3, timeout=60):
        """发送请求给API，支持重试机制"""
        retry_count = 0
        self.turn_count += 1
        
        # 记录详细日志 - 本轮对话的输入
        self.detailed_logger.info(f"\n{'='*50}")
        self.detailed_logger.info(f"轮次 {self.turn_count} - 输入消息")
        self.detailed_logger.info(f"{'='*50}")
        
        # 记录每条消息
        for i, msg in enumerate(messages):
            self.detailed_logger.info(f"消息 {i+1} (角色: {msg['role']}):")
            self.detailed_logger.info(f"{'-'*40}")
            self.detailed_logger.info(msg['content'])
            self.detailed_logger.info("")
        
        # 记录会话历史
        if len(self.conversation_history) == 0:
            # 首次调用，记录所有消息
            self.conversation_history.extend(messages)
        else:
            # 后续调用，只记录新消息（避免重复）
            last_user_msg = next((i for i in reversed(range(len(self.conversation_history))) 
                                if self.conversation_history[i]["role"] == "user"), None)
            
            if last_user_msg is not None and last_user_msg < len(self.conversation_history) - 1:
                # 有新消息需要添加
                self.conversation_history.extend(messages[-(len(messages) - last_user_msg - 1):])
            else:
                # 添加所有新消息
                self.conversation_history.extend(messages)
        
        # 保存当前对话历史到日志文件
        self._save_conversation()
        
        while retry_count < max_retries:
            try:
                logging.info(f"开始API调用 (尝试 {retry_count+1}/{max_retries})")
                self.detailed_logger.info(f"开始API调用 (尝试 {retry_count+1}/{max_retries})")
                
                # 添加超时设置
                response = self.client.chat.completions.create(
                    model=self.model_name,
                    messages=messages,
                    temperature=temperature,
                    timeout=timeout
                )
                
                # 记录Token使用情况
                self.total_tokens_in += response.usage.prompt_tokens
                self.total_tokens_out += response.usage.completion_tokens
                self.call_count += 1
                
                content = response.choices[0].message.content.strip()
                logging.info(f"API调用成功，返回内容长度: {len(content)}")
                
                # 记录详细日志 - 本轮对话的输出
                self.detailed_logger.info(f"\n{'='*50}")
                self.detailed_logger.info(f"轮次 {self.turn_count} - 输出内容 (长度: {len(content)})")
                self.detailed_logger.info(f"{'='*50}")
                self.detailed_logger.info(content)
                
                # 检查是否有工具调用
                tool_calls = []
                get_dep_rust_calls = re.findall(r'<tool>GET_DEPENDENCY_RUST_CODE\((.*?)\)</tool>', content)
                get_dep_c_calls = re.findall(r'<tool>GET_DEPENDENCY_C_CODE\((.*?)\)</tool>', content)
                
                if get_dep_rust_calls or get_dep_c_calls:
                    self.detailed_logger.info(f"\n{'='*50}")
                    self.detailed_logger.info(f"检测到工具调用")
                    self.detailed_logger.info(f"{'='*50}")
                    
                    for call in get_dep_rust_calls:
                        tool_calls.append(f"GET_DEPENDENCY_RUST_CODE({call})")
                        self.detailed_logger.info(f"调用: GET_DEPENDENCY_RUST_CODE({call})")
                    
                    for call in get_dep_c_calls:
                        tool_calls.append(f"GET_DEPENDENCY_C_CODE({call})")
                        self.detailed_logger.info(f"调用: GET_DEPENDENCY_C_CODE({call})")
                
                # 添加模型回复到对话历史
                self.conversation_history.append({
                    "role": "assistant", 
                    "content": content,
                    "metadata": {
                        "tokens_in": response.usage.prompt_tokens,
                        "tokens_out": response.usage.completion_tokens,
                        "tool_calls": tool_calls,
                        "timestamp": datetime.now().isoformat()
                    }
                })
                
                # 保存更新后的对话历史
                self._save_conversation()
                
                return content
            
            except (requests.exceptions.RequestException, requests.exceptions.Timeout) as e:
                retry_count += 1
                wait_time = 2 ** retry_count  # 指数退避
                logging.warning(f"API网络错误 (尝试 {retry_count}/{max_retries}): {e}")
                self.detailed_logger.warning(f"API网络错误 (尝试 {retry_count}/{max_retries}): {e}")
                
                if retry_count < max_retries:
                    logging.info(f"等待 {wait_time} 秒后重试...")
                    self.detailed_logger.info(f"等待 {wait_time} 秒后重试...")
                    time.sleep(wait_time)
                else:
                    logging.error(f"网络请求失败，达到最大重试次数: {e}")
                    self.detailed_logger.error(f"网络请求失败，达到最大重试次数: {e}")
                    raise RuntimeError(f"API网络请求失败: {e}")
            
            except Exception as e:
                retry_count += 1
                wait_time = 2 ** retry_count  # 指数退避
                logging.warning(f"API调用失败 (尝试 {retry_count}/{max_retries}): {type(e).__name__}: {e}")
                self.detailed_logger.warning(f"API调用失败 (尝试 {retry_count}/{max_retries}): {type(e).__name__}: {e}")
                
                if retry_count < max_retries:
                    logging.info(f"等待 {wait_time} 秒后重试...")
                    self.detailed_logger.info(f"等待 {wait_time} 秒后重试...")
                    time.sleep(wait_time)
                else:
                    logging.error(f"达到最大重试次数。错误类型: {type(e).__name__}, 错误信息: {e}")
                    self.detailed_logger.error(f"达到最大重试次数。错误类型: {type(e).__name__}, 错误信息: {e}")
                    # 处理常见的API错误
                    if "rate limit" in str(e).lower():
                        raise RuntimeError(f"API速率限制错误，请稍后再试")
                    elif "authentication" in str(e).lower() or "api key" in str(e).lower():
                        raise RuntimeError(f"API密钥认证错误: {e}")
                    else:
                        raise RuntimeError(f"API调用失败: {type(e).__name__}: {e}")
    
    def _save_conversation(self):
        """保存当前对话历史到日志文件"""
        try:
            # 创建对话记录文件
            log_filename = f"conversation_{self.session_id}.json"
            log_path = os.path.join(self.log_dir, log_filename)
            
            # 保存为JSON格式
            with open(log_path, 'w', encoding='utf-8') as f:
                json.dump({
                    "session_id": self.session_id,
                    "model": self.model_name,
                    "timestamp": datetime.now().isoformat(),
                    "stats": self.get_stats(),
                    "turn_count": self.turn_count,
                    "conversation": self.conversation_history
                }, f, ensure_ascii=False, indent=2)
                
            logging.debug(f"对话历史已保存到: {log_path}")
        except Exception as e:
            logging.error(f"保存对话历史失败: {e}")
            self.detailed_logger.error(f"保存对话历史失败: {e}")
    
    def log_tool_response(self, tool_name, args, response):
        """记录工具调用的响应"""
        self.detailed_logger.info(f"\n{'='*50}")
        self.detailed_logger.info(f"工具响应: {tool_name}")
        self.detailed_logger.info(f"{'='*50}")
        self.detailed_logger.info(f"参数: {args}")
        self.detailed_logger.info(f"{'='*30}")
        self.detailed_logger.info(f"响应:\n{response}")
    
    def get_stats(self):
        """返回API使用统计"""
        return {
            "calls": self.call_count,
            "tokens_in": self.total_tokens_in,
            "tokens_out": self.total_tokens_out,
            "total_tokens": self.total_tokens_in + self.total_tokens_out
        } 