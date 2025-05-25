import time
import logging
import requests
from openai import OpenAI

class GPT:
    def __init__(self, api_key, model_name="gpt-4o", base_url="https://api.zetatechs.com/v1"):
        self.client = OpenAI(api_key=api_key, base_url=base_url)
        self.model_name = model_name
        self.total_tokens_in = 0
        self.total_tokens_out = 0
        self.call_count = 0
    
    def ask(self, messages, temperature=0.2, max_retries=3, timeout=60):
        """发送请求给API，支持重试机制"""
        retry_count = 0
        while retry_count < max_retries:
            try:
                logging.info(f"开始API调用 (尝试 {retry_count+1}/{max_retries})")
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
                return content
            
            except (requests.exceptions.RequestException, requests.exceptions.Timeout) as e:
                retry_count += 1
                wait_time = 2 ** retry_count  # 指数退避
                logging.warning(f"API网络错误 (尝试 {retry_count}/{max_retries}): {e}")
                
                if retry_count < max_retries:
                    logging.info(f"等待 {wait_time} 秒后重试...")
                    time.sleep(wait_time)
                else:
                    logging.error(f"网络请求失败，达到最大重试次数: {e}")
                    raise RuntimeError(f"API网络请求失败: {e}")
            
            except Exception as e:
                retry_count += 1
                wait_time = 2 ** retry_count  # 指数退避
                logging.warning(f"API调用失败 (尝试 {retry_count}/{max_retries}): {type(e).__name__}: {e}")
                
                if retry_count < max_retries:
                    logging.info(f"等待 {wait_time} 秒后重试...")
                    time.sleep(wait_time)
                else:
                    logging.error(f"达到最大重试次数。错误类型: {type(e).__name__}, 错误信息: {e}")
                    # 处理常见的API错误
                    if "rate limit" in str(e).lower():
                        raise RuntimeError(f"API速率限制错误，请稍后再试")
                    elif "authentication" in str(e).lower() or "api key" in str(e).lower():
                        raise RuntimeError(f"API密钥认证错误: {e}")
                    else:
                        raise RuntimeError(f"API调用失败: {type(e).__name__}: {e}")
    
    def get_stats(self):
        """返回API使用统计"""
        return {
            "calls": self.call_count,
            "tokens_in": self.total_tokens_in,
            "tokens_out": self.total_tokens_out,
            "total_tokens": self.total_tokens_in + self.total_tokens_out
        } 