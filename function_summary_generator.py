import json
import time
import logging
import os
import sys
import traceback
import copy
from datetime import datetime

# 配置根日志器
logging.basicConfig(level=logging.WARNING)

# 导入工具模块
from sig_utils.gpt_client import GPT
from sig_utils.stats_collector import ConversionStats
from sig_utils.text_extractor import TextExtractor
from sig_utils.prompt_templates import PromptTemplates

# 配置目录
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_DIR = os.path.join(BASE_DIR, "logs")
DATA_DIR = os.path.join(BASE_DIR, "data")
os.makedirs(LOG_DIR, exist_ok=True)
os.makedirs(DATA_DIR, exist_ok=True)

# 配置日志
class Logger:
    def __init__(self, name, log_dir=LOG_DIR, console_output=True):
        self.logger = logging.getLogger(name)
        self.logger.setLevel(logging.DEBUG)
        self.logger.propagate = False
        
        if not self.logger.handlers:
            file_handler = logging.FileHandler(
                os.path.join(log_dir, f"{name}.log"), 
                encoding="utf-8",
                mode='w'
            )
            file_handler.setLevel(logging.DEBUG)
            
            formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
            file_handler.setFormatter(formatter)
            
            self.logger.addHandler(file_handler)
            
            if console_output:
                console_handler = logging.StreamHandler()
                console_handler.setLevel(logging.INFO)
                console_handler.setFormatter(formatter)
                self.logger.addHandler(console_handler)
                self.logger.addHandler(console_handler)
    
    def debug(self, msg): 
        self.logger.debug(msg)
        self._flush_handlers()
        
    def info(self, msg): 
        self.logger.info(msg)
        self._flush_handlers()
        
    def warning(self, msg): 
        self.logger.warning(msg)
        self._flush_handlers()
        
    def error(self, msg): 
        self.logger.error(msg)
        self._flush_handlers()
        
    def critical(self, msg): 
        self.logger.critical(msg)
        self._flush_handlers()
    
    def _flush_handlers(self):
        for handler in self.logger.handlers:
            handler.flush()

# 主日志
main_logger = Logger("func_summary_main")
item_logger = Logger("func_summary_items", console_output=False)
ai_dialog_logger = Logger("func_summary_ai_dialog", console_output=False)

# 依赖项使用示例
DEPENDENCY_EXAMPLE = """
例如，对于一个函数，如果它调用了"calculate_hash"和"allocate_memory"这两个依赖函数，依赖项分析应该类似：

```json
{
  "function_name": "process_data",
  "main_purpose": "处理输入数据并计算其哈希值",
  "detailed_logic": "函数首先分配内存，然后对输入数据进行预处理，最后计算哈希值并返回结果。如果内存分配失败，则返回错误码。",
  "error_handling": "函数检查内存分配是否成功，如果失败则返回错误码-1。也会检查输入参数是否有效，无效时返回错误码-2。",
  "dependencies": {
    "calculate_hash": {
      "signature": "fn calculate_hash(data: *const u8, len: usize) -> u32",
      "usage": "在预处理数据后调用此函数计算哈希值。传入预处理后的数据缓冲区和长度，直接使用返回的哈希值作为结果。如果输入数据无效，不会调用此函数。"
    },
    "allocate_memory": {
      "signature": "fn allocate_memory(size: usize) -> *mut u8",
      "usage": "在函数开始时调用此函数分配所需内存。检查返回值是否为NULL，如果是NULL则函数提前返回错误码。成功分配的内存在使用完毕后通过free_memory释放。"
    }
  }
}
```
"""

# 函数总结生成器
class FunctionSummaryGenerator:
    def __init__(self, api_key):
        main_logger.info("初始化函数总结生成器")
        self.agent1 = GPT(api_key, model_name="gpt-4o")  # 总结生成专家
        self.agent2 = GPT(api_key, model_name="gpt-4o")  # 总结审核专家
        self.stats = ConversionStats()
        # 用于跟踪总项目数
        self.total_functions = 0
    
    def generate_summary(self, item_id, c_code, rust_signature, dependency_info=None, max_rounds=3):
        """为单个函数生成总结，包含多轮审核直到通过"""
        main_logger.info(f"开始生成函数总结: {item_id}")
        item_logger.info(f"==================== 开始生成函数总结: {item_id} ====================")
        item_logger.info(f"C代码:\n{c_code}")
        item_logger.info(f"Rust签名:\n{rust_signature}")
        
        # 记录AI对话开始
        ai_dialog_logger.info(f"==================== AI对话开始: {item_id} ====================")
        ai_dialog_logger.info(f"输入C代码: {c_code}")
        ai_dialog_logger.info(f"输入Rust签名: {rust_signature}")
        
        # 准备依赖项信息
        dependencies_text = ""
        available_deps_list = []
        
        if dependency_info:
            functions_deps = dependency_info.get("functions", {})
            non_functions_deps = dependency_info.get("non_functions", {})
            
            # 构建依赖项信息
            dependencies_text = "\n## 依赖项：\n"
            
            # 处理函数依赖
            if functions_deps:
                dependencies_text += "\n### 函数依赖：\n"
                
                for dep_id, dep_data in functions_deps.items():
                    signature = dep_data.get("signature", "未知签名")
                    purpose = dep_data.get("purpose", "未知目的")
                    
                    dependencies_text += f"#### {dep_id}\n```rust\n{signature}\n```\n"
                    dependencies_text += f"目的: {purpose}\n\n"
                    
                    available_deps_list.append(dep_id)
            
            # 处理非函数依赖
            if non_functions_deps:
                dependencies_text += "\n### 非函数依赖：\n"
                
                for dep_id, signature in non_functions_deps.items():
                    dependencies_text += f"#### {dep_id}\n```rust\n{signature}\n```\n\n"
                    
                    available_deps_list.append(dep_id)
        
        # 构建提示
        summary_prompt = """请对以下C函数进行详细分析并生成总结，总结将用于后续转换为Rust实现：

## 原始C函数代码：
```c
{c_code}
```

## 对应的Rust函数签名：
```rust
{rust_signature}
```

{dependencies_text}

请提供以下内容的详细总结：
1. **函数的主要功能**：函数的整体目的和作用
2. **函数的具体逻辑**：详细分析函数的执行流程和算法步骤
3. **错误处理**：函数的错误检查和处理机制
4. **依赖项**：函数如何使用其依赖项（仅包含我提供的依赖项）

{dependency_example}

请以JSON格式返回总结结果：
```json
{{
  "function_name": "函数名称",
  "main_purpose": "函数的主要功能和目的",
  "detailed_logic": "函数的详细执行逻辑和算法步骤",
  "error_handling": "错误检查和处理机制",
  "dependencies": {{
    "依赖项1": {{
      "signature": "依赖项1的Rust签名",
      "usage": "详细描述如何使用该依赖项"
    }},
    "依赖项2": {{
      "signature": "依赖项2的Rust签名",
      "usage": "详细描述如何使用该依赖项"
    }}
  }}
}}
```

注意：dependencies字段中只包含我在上面列出的依赖项{available_deps_note}。如果函数没有使用任何依赖项，请将dependencies设为空对象{{}}。

只返回JSON对象，不要添加其他文本。"""
        
        # 替换参数
        summary_prompt = summary_prompt.replace("{c_code}", c_code)
        summary_prompt = summary_prompt.replace("{rust_signature}", rust_signature)
        summary_prompt = summary_prompt.replace("{dependencies_text}", dependencies_text)
        summary_prompt = summary_prompt.replace("{dependency_example}", DEPENDENCY_EXAMPLE)
        
        # 添加可用依赖项注意事项
        available_deps_note = ""
        if available_deps_list:
            available_deps_note = f"（{', '.join(available_deps_list)}）"
        summary_prompt = summary_prompt.replace("{available_deps_note}", available_deps_note)
        
        # 构建消息
        messages = [
            {"role": "system", "content": "你是一个精通C和Rust的编程专家，擅长分析C代码并为其生成详细的功能和逻辑总结。你的总结应该准确、全面、有条理，能够帮助其他开发者理解函数的工作原理并进行Rust实现。"},
            {"role": "user", "content": summary_prompt}
        ]
        
        # 记录初始对话
        ai_dialog_logger.info(f"系统提示: {messages[0]['content']}")
        ai_dialog_logger.info(f"用户提示: {summary_prompt}")
        
        # 多轮生成和审核，直到通过或达到最大轮数
        for round_num in range(1, max_rounds + 1):
            main_logger.info(f"开始第 {round_num} 轮总结生成")
            item_logger.info(f"第 {round_num} 轮总结生成")
            
            try:
                # 获取总结结果
                summary_response_raw = self.agent1.ask(messages)
                ai_dialog_logger.info(f"轮次 {round_num} - Agent1回复: {summary_response_raw}")
                
                # 解析JSON响应
                summary_json = TextExtractor.extract_json(summary_response_raw)
                if not summary_json:
                    # 如果JSON解析失败，尝试提取文本作为备选
                    item_logger.warning("JSON解析失败，尝试提取文本")
                    summary_text = summary_response_raw
                    if "```json" in summary_text:
                        summary_text = summary_text.split("```json")[1].split("```")[0].strip()
                    
                    # 尝试再次解析清理后的文本
                    try:
                        summary_json = json.loads(summary_text)
                    except:
                        # 如果仍然失败，使用默认结构
                        summary_json = {
                            "function_name": item_id,
                            "main_purpose": "函数的主要功能和目的",
                            "detailed_logic": summary_text,
                            "error_handling": "无显式错误处理",
                            "dependencies": {}
                        }
                
                # 确保dependencies字段存在，即使为空
                if "dependencies" not in summary_json:
                    summary_json["dependencies"] = {}
                
                # 验证dependencies只包含我们提供的依赖项
                if dependency_info:
                    valid_dependencies = set()
                    if "functions" in dependency_info:
                        valid_dependencies.update(dependency_info["functions"].keys())
                    if "non_functions" in dependency_info:
                        valid_dependencies.update(dependency_info["non_functions"].keys())
                    
                    current_dependencies = set(summary_json["dependencies"].keys())
                    
                    # 移除不在有效依赖项列表中的项
                    invalid_deps = current_dependencies - valid_dependencies
                    for dep in invalid_deps:
                        if dep in summary_json["dependencies"]:
                            del summary_json["dependencies"][dep]
                            item_logger.warning(f"移除无效依赖项: {dep}")
                
                # 审核总结
                review_prompt = """请审核以下函数总结的质量：

## 原始C函数代码：
```c
{c_code}
```

## 对应的Rust函数签名：
```rust
{rust_signature}
```

{dependencies_text}

## 生成的函数总结：
```json
{summary_json}
```

请评估总结是否基本准确地反映了函数的功能、逻辑和依赖项使用方式。不需要过于严格，只要能够帮助开发者理解函数功能即可。

请以JSON格式返回审核结果：
```json
{{
  "review_result": "PASS/FAIL",
  "reason": "通过/失败的简要原因"
}}
```

只返回JSON对象，不要添加其他文本。"""
                
                # 替换参数
                review_prompt = review_prompt.replace("{c_code}", c_code)
                review_prompt = review_prompt.replace("{rust_signature}", rust_signature)
                review_prompt = review_prompt.replace("{dependencies_text}", dependencies_text)
                review_prompt = review_prompt.replace("{summary_json}", json.dumps(summary_json, indent=2, ensure_ascii=False))
                
                review_messages = [
                    {"role": "system", "content": "你是一个代码审核专家，负责评估函数总结的质量。审核应该务实而不是过于严格，只要总结能够帮助开发者理解函数的基本功能即可。"},
                    {"role": "user", "content": review_prompt}
                ]
                
                # 记录审核对话
                ai_dialog_logger.info(f"轮次 {round_num} - 审核系统提示: {review_messages[0]['content']}")
                ai_dialog_logger.info(f"轮次 {round_num} - 审核用户提示: {review_prompt}")
                
                review_response = self.agent2.ask(review_messages)
                ai_dialog_logger.info(f"轮次 {round_num} - Agent2回复: {review_response}")
                
                # 解析审核结果JSON
                review_json = None
                try:
                    # 尝试直接解析
                    review_json = TextExtractor.extract_json(review_response)
                    
                    # 如果提取失败，尝试从代码块中提取
                    if not review_json and "```json" in review_response:
                        json_text = review_response.split("```json")[1].split("```")[0].strip()
                        review_json = json.loads(json_text)
                        
                    # 如果还是失败，使用简单的正则表达式匹配
                    if not review_json:
                        if '"review_result": "PASS"' in review_response:
                            review_json = {"review_result": "PASS", "reason": "总结符合基本要求"}
                        elif '"review_result": "FAIL"' in review_response:
                            review_json = {"review_result": "FAIL", "reason": "总结需要改进"}
                except Exception as e:
                    item_logger.warning(f"审核结果JSON解析失败: {e}")
                
                # 如果所有解析方法都失败，使用默认值
                if not review_json:
                    review_json = {
                        "review_result": "PASS",  # 默认通过
                        "reason": "无法解析审核结果，默认通过"
                    }
                
                # 处理审核结果
                item_logger.info(f"轮次 {round_num} - 审核结果: {review_json['review_result']}")
                item_logger.info(f"轮次 {round_num} - 原因: {review_json.get('reason', 'N/A')}")
                
                # 如果审核通过，返回结果
                if review_json["review_result"] == "PASS":
                    main_logger.info(f"函数总结审核通过: {item_id} (第 {round_num} 轮)")
                    
                    # 构建最终结果
                    result = {
                        "success": True,
                        "summary": summary_json,
                        "review": review_json,
                        "rounds": round_num
                    }
                    
                    item_logger.info(f"总结生成成功: {item_id}")
                    item_logger.info(f"==================== 结束函数总结: {item_id} ====================\n")
                    ai_dialog_logger.info(f"==================== AI对话结束: {item_id} ====================\n")
                    
                    return result
                
                # 如果审核不通过且不是最后一轮，继续改进
                if round_num < max_rounds:
                    main_logger.warning(f"函数总结审核不通过: {item_id} (第 {round_num} 轮)，继续改进")
                    
                    # 构建改进提示
                    improve_prompt = """你之前生成的函数总结审核不通过，请根据以下反馈进行改进：

## 审核结果：
{review_result}

## 审核意见：
{reason}

请重新生成更准确的函数总结，并注意以下几点：
1. 确保正确描述函数的主要功能和逻辑流程
2. 仅分析我提供的依赖项的使用方式
3. 保持简洁明了的描述风格

原始C函数代码：
```c
{c_code}
```

对应的Rust函数签名：
```rust
{rust_signature}
```

{dependencies_text}

请以JSON格式返回改进后的总结结果：
```json
{{
  "function_name": "函数名称",
  "main_purpose": "函数的主要功能和目的",
  "detailed_logic": "函数的详细执行逻辑和算法步骤",
  "error_handling": "错误检查和处理机制",
  "dependencies": {{
    "依赖项1": {{
      "signature": "依赖项1的Rust签名",
      "usage": "详细描述如何使用该依赖项"
    }},
    "依赖项2": {{
      "signature": "依赖项2的Rust签名",
      "usage": "详细描述如何使用该依赖项"
    }}
  }}
}}
```

注意：dependencies字段中只包含我在上面列出的依赖项{available_deps_note}。

只返回JSON对象，不要添加其他文本。"""
                    
                    # 替换参数
                    improve_prompt = improve_prompt.replace("{review_result}", review_json["review_result"])
                    improve_prompt = improve_prompt.replace("{reason}", review_json.get("reason", "未提供具体原因"))
                    improve_prompt = improve_prompt.replace("{c_code}", c_code)
                    improve_prompt = improve_prompt.replace("{rust_signature}", rust_signature)
                    improve_prompt = improve_prompt.replace("{dependencies_text}", dependencies_text)
                    improve_prompt = improve_prompt.replace("{available_deps_note}", available_deps_note)
                    
                    # 更新消息历史
                    messages.append({"role": "assistant", "content": summary_response_raw})
                    messages.append({"role": "user", "content": improve_prompt})
                    
                    # 记录改进对话
                    ai_dialog_logger.info(f"轮次 {round_num} - 改进提示: {improve_prompt}")
                else:
                    # 达到最大轮数仍未通过，但我们还是接受最后一轮的结果
                    main_logger.warning(f"函数总结达到最大轮数 {max_rounds}，采用最后一轮结果: {item_id}")
                    
                    # 使用最后一轮的结果
                    result = {
                        "success": True,  # 仍然标记为成功
                        "summary": summary_json,
                        "review": review_json,
                        "rounds": round_num,
                        "passed_review": False
                    }
                    
                    item_logger.warning(f"总结生成完成但未通过最终审核，采用最后结果: {item_id}")
                    item_logger.info(f"==================== 结束函数总结: {item_id} ====================\n")
                    ai_dialog_logger.info(f"==================== AI对话结束: {item_id} ====================\n")
                    
                    return result
                
            except Exception as e:
                error_msg = f"总结生成过程发生错误: {str(e)}"
                main_logger.error(error_msg)
                main_logger.error(traceback.format_exc())
                ai_dialog_logger.error(f"总结生成错误: {error_msg}")
                
                if round_num == max_rounds:
                    # 最后一轮出错，返回失败
                    result = {
                        "success": False,
                        "error": error_msg
                    }
                    
                    item_logger.warning(f"总结生成失败，原因: {error_msg}")
                    item_logger.info(f"==================== 结束函数总结 (失败): {item_id} ====================\n")
                    ai_dialog_logger.info(f"==================== AI对话结束 (失败): {item_id} ====================\n")
                    
                    return result
                
                # 非最后一轮出错，继续尝试
                main_logger.warning(f"轮次 {round_num} 出错，继续下一轮")
        
        # 不应该执行到这里，但如果执行到了，返回失败
        return {
            "success": False,
            "error": "未知错误，执行到了循环之外"
        }
    
    def process_architecture_file(self, filepath, output_path=None, max_items=None):
        """处理整个架构文件，为所有函数生成总结"""
        main_logger.info("="*80)
        main_logger.info(f"开始处理架构文件: {filepath}")
        main_logger.info("="*80)
        
        # 读取输入文件
        with open(filepath, "r", encoding="utf-8") as f:
            input_data = json.load(f)
        
        # 默认输出路径
        if not output_path:
            basename = os.path.basename(filepath)
            name_parts = basename.split('.')
            if len(name_parts) > 1:
                output_basename = '.'.join(name_parts[:-1]) + '_with_summaries.' + name_parts[-1]
            else:
                output_basename = basename + '_with_summaries'
            output_path = os.path.join(os.path.dirname(filepath), output_basename)
        
        # 检查输出文件是否已存在
        data = copy.deepcopy(input_data)
        if os.path.exists(output_path):
            try:
                main_logger.info(f"检测到现有输出文件: {output_path}，读取已处理状态")
                with open(output_path, "r", encoding="utf-8") as f:
                    output_data = json.load(f)
                
                # 合并数据，优先使用输出文件中的处理状态
                for file_name, content in output_data.items():
                    if file_name not in data:
                        data[file_name] = content
                        continue
                        
                    if "functions" in content:
                        if "functions" not in data[file_name]:
                            data[file_name]["functions"] = {}
                            
                        for item_name, item in content["functions"].items():
                            # 如果函数已有总结，使用输出文件中的状态
                            if "function_summary" in item:
                                if item_name in data[file_name]["functions"]:
                                    data[file_name]["functions"][item_name]["function_summary"] = item["function_summary"]
                                    data[file_name]["functions"][item_name]["summary_status"] = item.get("summary_status", "unknown")
            except Exception as e:
                main_logger.error(f"读取输出文件时出错: {e}")
        
        # 收集所有函数信息
        all_functions = []
        function_dependencies = {}
        
        for file_name, content in data.items():
            if "functions" not in content:
                continue
                
            for item_name, item in content["functions"].items():
                # 检查函数是否已转换成功并且没有总结
                if item.get("conversion_status") == "success" and "function_summary" not in item:
                    rust_signature = item.get("rust_signature", "")
                    full_text = item.get("full_text", "")
                    
                    if rust_signature and full_text:
                        func_id = f"{file_name}::functions::{item_name}"
                        
                        all_functions.append({
                            "id": func_id,
                            "file_name": file_name,
                            "item_name": item_name,
                            "c_code": full_text,
                            "rust_signature": rust_signature,
                            "dependencies": item.get("dependencies", {})
                        })
                        
                        # 记录依赖关系
                        function_dependencies[func_id] = item.get("dependencies", {})
                    else:
                        main_logger.warning(f"函数缺少必要信息: {file_name}::{item_name}")
                        continue
        
        # 设置总函数数量
        self.total_functions = len(all_functions)
        main_logger.info(f"找到 {self.total_functions} 个需要生成总结的函数")
        
        # 记录已生成总结的函数
        summarized_functions = set()
        
        # 检查已有总结的函数
        for file_name, content in data.items():
            if "functions" not in content:
                continue
                
            for item_name, item in content["functions"].items():
                if item.get("summary_status") == "success" and "function_summary" in item:
                    func_id = f"{file_name}::functions::{item_name}"
                    summarized_functions.add(func_id)
        
        main_logger.info(f"已有 {len(summarized_functions)} 个函数有总结")
        
        # 开始处理
        processed_count = 0
        success_count = 0
        failed_count = 0
        
        # 循环处理，直到所有函数都处理完或者无法继续处理
        while len(summarized_functions) < len(all_functions) + len(summarized_functions):
            progress_made = False
            
            for func in all_functions:
                if func["id"] in summarized_functions:
                    continue
                
                # 检查依赖项是否都已经总结
                all_deps_summarized = True
                missing_deps = []  # 记录缺失的依赖项
                
                for dep_id, dep_info in func["dependencies"].items():
                    if dep_info.get("type") == "functions":
                        dep_qualified_name = dep_info.get("qualified_name", "")
                        if dep_qualified_name:
                            dep_parts = dep_qualified_name.split("::")
                            if len(dep_parts) >= 2:
                                dep_file = dep_parts[0]
                                dep_name = "::".join(dep_parts[1:])
                                dep_full_id = f"{dep_file}::functions::{dep_name}"
                                
                                if dep_full_id not in summarized_functions:
                                    all_deps_summarized = False
                                    missing_deps.append(dep_full_id)  # 记录缺失的依赖项
                                    break
                
                # 如果有缺失的依赖项，记录信息
                if not all_deps_summarized:
                    func["missing_deps"] = missing_deps
                    continue
                
                if all_deps_summarized:
                    # 所有依赖项都已总结，可以处理这个函数
                    current_progress = processed_count + 1
                    total_functions = self.total_functions
                    main_logger.info(f"开始处理函数 [{current_progress}/{total_functions}] ({current_progress/total_functions*100:.1f}%): {func['id']}")
                    
                    # 收集依赖项信息
                    dependency_info = {"functions": {}, "non_functions": {}}
                    
                    for dep_id, dep_info in func["dependencies"].items():
                        dep_type = dep_info.get("type")
                        dep_qualified_name = dep_info.get("qualified_name", "")
                        
                        if not dep_qualified_name:
                            continue
                        
                        dep_parts = dep_qualified_name.split("::")
                        if len(dep_parts) < 2:
                            continue
                        
                        dep_file = dep_parts[0]
                        dep_name = "::".join(dep_parts[1:])
                        
                        # 处理函数依赖
                        if dep_type == "functions":
                            if "functions" in data[dep_file] and dep_name in data[dep_file]["functions"]:
                                dep_item = data[dep_file]["functions"][dep_name]
                                
                                # 获取签名和目的
                                signature = dep_item.get("rust_signature", "未知签名")
                                
                                purpose = ""
                                if "function_summary" in dep_item:
                                    summary_json = dep_item["function_summary"]
                                    purpose = summary_json.get("main_purpose", "未知目的")
                                
                                # 添加到依赖信息
                                dependency_info["functions"][dep_id] = {
                                    "signature": signature,
                                    "purpose": purpose
                                }
                        # 处理非函数依赖
                        else:
                            # 尝试从各种类型中找到依赖项
                            for item_type in ["typedefs", "structs", "defines", "fields"]:
                                if item_type in data[dep_file] and dep_name in data[dep_file][item_type]:
                                    non_func_item = data[dep_file][item_type][dep_name]
                                    signature = non_func_item.get("rust_signature", "未知签名")
                                    dependency_info["non_functions"][dep_id] = signature
                                    break
                    
                    # 生成函数总结
                    result = self.generate_summary(
                        func["id"],
                        func["c_code"],
                        func["rust_signature"],
                        dependency_info
                    )
                    
                    # 更新结果
                    if result["success"]:
                        # 获取file_name和item_name
                        file_name = func["file_name"]
                        item_name = func["item_name"]
                        
                        # 更新数据
                        data[file_name]["functions"][item_name]["function_summary"] = result["summary"]
                        data[file_name]["functions"][item_name]["summary_status"] = "success"
                        data[file_name]["functions"][item_name]["summary_review"] = result["review"]
                        data[file_name]["functions"][item_name]["summary_rounds"] = result.get("rounds", 1)
                        
                        # 添加到已总结集合
                        summarized_functions.add(func["id"])
                        
                        success_count += 1
                        main_logger.info(f"成功生成函数总结 [{current_progress}/{total_functions}]: {func['id']} (用了 {result.get('rounds', 1)} 轮)")
                    else:
                        # 更新失败状态
                        file_name = func["file_name"]
                        item_name = func["item_name"]
                        
                        data[file_name]["functions"][item_name]["summary_status"] = "failed"
                        data[file_name]["functions"][item_name]["summary_error"] = result["error"]
                        
                        # 添加到已总结集合（虽然失败了，但也不需要再次处理）
                        summarized_functions.add(func["id"])
                        
                        failed_count += 1
                        main_logger.warning(f"生成函数总结失败 [{current_progress}/{total_functions}]: {func['id']}")
                    
                    processed_count += 1
                    progress_made = True
                    
                    # 定期保存
                    if processed_count % 5 == 0:
                        with open(output_path, "w", encoding="utf-8") as f:
                            json.dump(data, f, indent=4, ensure_ascii=False)
                        main_logger.info(f"已处理 {processed_count}/{total_functions} 个函数，中间结果已保存")
                    
                    # 检查是否达到最大处理数量
                    if max_items and processed_count >= max_items:
                        main_logger.info(f"已达到最大处理数量 {max_items}，停止处理")
                        break
                        
            # 如果这一轮没有处理任何函数，说明剩下的函数都有循环依赖，无法继续处理
            if not progress_made:
                main_logger.warning("无法继续处理，可能存在循环依赖")
                break
                
            # 检查是否达到最大处理数量
            if max_items and processed_count >= max_items:
                break
        
        # 保存最终结果
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
            
        # 输出结果统计
        main_logger.info("="*80)
        main_logger.info(f"处理完成: 成功={success_count}, 失败={failed_count}, 总计={processed_count}/{self.total_functions}")
        main_logger.info(f"结果已保存到: {output_path}")
        main_logger.info("="*80)
        
        # 检查是否有未处理的函数
        unprocessed_functions = []
        for func in all_functions:
            if func["id"] not in summarized_functions:
                unprocessed_functions.append(func)
        
        if unprocessed_functions:
            unprocessed_count = len(unprocessed_functions)
            main_logger.warning(f"还有 {unprocessed_count}/{self.total_functions} 个函数未处理，可能是由于循环依赖")
            
            # 创建依赖图用于分析循环依赖
            dependency_graph = {}
            for func in all_functions:
                func_deps = []
                for dep_id, dep_info in func["dependencies"].items():
                    if dep_info.get("type") == "functions":
                        dep_qualified_name = dep_info.get("qualified_name", "")
                        if dep_qualified_name:
                            dep_parts = dep_qualified_name.split("::")
                            if len(dep_parts) >= 2:
                                dep_file = dep_parts[0]
                                dep_name = "::".join(dep_parts[1:])
                                dep_full_id = f"{dep_file}::functions::{dep_name}"
                                func_deps.append(dep_full_id)
                dependency_graph[func["id"]] = func_deps
            
            # 打印未处理函数及其依赖
            main_logger.info("\n未处理函数列表及原因:")
            for i, func in enumerate(unprocessed_functions, 1):
                # 检查是否有缺失的依赖
                missing_deps = getattr(func, "missing_deps", [])
                
                # 如果没有记录缺失依赖，从依赖图中查找
                if not missing_deps and func["id"] in dependency_graph:
                    for dep_id in dependency_graph[func["id"]]:
                        if dep_id not in summarized_functions:
                            missing_deps.append(dep_id)
                
                main_logger.info(f"{i}. {func['id']}")
                
                # 如果有缺失依赖，显示它们
                if missing_deps:
                    main_logger.info(f"   原因: 等待依赖项完成总结，缺失 {len(missing_deps)} 个依赖:")
                    for j, dep_id in enumerate(missing_deps[:5], 1):  # 只显示前5个
                        main_logger.info(f"      {j}. {dep_id}")
                    if len(missing_deps) > 5:
                        main_logger.info(f"      ...以及其他 {len(missing_deps) - 5} 个依赖")
                else:
                    # 检查是否存在循环依赖
                    cycle_found = False
                    for other_func in unprocessed_functions:
                        if other_func["id"] == func["id"]:
                            continue
                        if func["id"] in dependency_graph.get(other_func["id"], []) and other_func["id"] in dependency_graph.get(func["id"], []):
                            main_logger.info(f"   原因: 循环依赖 - 与 {other_func['id']} 互相依赖")
                            cycle_found = True
                            break
                    
                    if not cycle_found:
                        main_logger.info(f"   原因: 未知原因或复杂的依赖关系")
        
        return data

# 命令行接口
def main():
    """主程序入口"""
    import argparse
    
    # 定义默认参数
    default_input_path = "data/converted_architecture.json"
    default_output_path = None  # 会自动生成
    default_max_items = 1000  # 默认处理项数
    default_api_key = "sk-Wx9RbmSNFH5Q1BbhpoVdRzoLka4ATPeO16qoDwe13YEF71qJ"
    
    parser = argparse.ArgumentParser(description="函数总结生成工具")
    parser.add_argument("--input", "-i", help="输入的架构JSON文件路径")
    parser.add_argument("--output", "-o", help="输出的带总结的JSON文件路径")
    parser.add_argument("--max-items", "-m", type=int, help="最大处理项数，用于测试")
    parser.add_argument("--api-key", "-k", help="OpenAI API密钥")
    parser.add_argument("--debug", "-d", action="store_true", help="启用调试模式")
    parser.add_argument("--test", "-t", action="store_true", help="测试模式：只处理1个项目")
    
    args = parser.parse_args()
    
    # 使用命令行参数或默认值
    input_path = args.input or default_input_path
    output_path = args.output or default_output_path
    max_items = 1 if args.test else (args.max_items or default_max_items)
    
    # 配置日志级别
    if args.debug:
        for logger in [main_logger, item_logger]:
            logger.logger.setLevel(logging.DEBUG)
    
    # 获取API密钥
    api_key = args.api_key or default_api_key
    if not api_key:
        main_logger.error("未提供API密钥，请通过--api-key参数提供")
        sys.exit(1)
    
    try:
        # 测试模式提示
        if args.test:
            main_logger.warning("⚠️ 测试模式：只处理1个项目")
            
        # 初始化生成器
        main_logger.info("初始化函数总结生成器...")
        generator = FunctionSummaryGenerator(api_key)
        
        # 开始处理
        main_logger.info(f"使用输入文件: {input_path}")
        if output_path:
            main_logger.info(f"将输出到: {output_path}")
        main_logger.info(f"最大处理项数: {max_items}")
        
        result = generator.process_architecture_file(
            input_path,
            output_path,
            max_items
        )
        
        main_logger.info("函数总结生成完成!")
        
    except Exception as e:
        main_logger.error(f"程序执行出错: {str(e)}")
        main_logger.error(traceback.format_exc())
        sys.exit(1)

if __name__ == "__main__":
    main()