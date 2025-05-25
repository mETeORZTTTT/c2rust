import json
import os
import re
import logging
import tempfile
import shutil
import traceback
import subprocess

from .gpt_client import GPT
from .rust_compiler import RustCompiler

logger = logging.getLogger("implement")

class FunctionImplementer:
    """C到Rust函数实现转换器"""
    
    def __init__(self, architecture_file, output_file=None, api_key=None):
        """初始化函数实现转换器
        
        Args:
            architecture_file: 包含已转换签名的架构文件路径
            output_file: 输出结果的文件路径
            api_key: OpenAI API密钥
        """
        self.architecture_file = architecture_file
        self.output_file = output_file or architecture_file.replace(".json", "_implemented.json")
        
        # 获取API密钥
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY")
        if not self.api_key:
            raise ValueError("未提供API密钥，请通过参数或OPENAI_API_KEY环境变量设置")
            
        self.gpt = GPT(api_key=self.api_key, model_name="gpt-4o")
        self.temp_dir = tempfile.mkdtemp(prefix="rust_compile_")
        logger.info(f"创建临时目录: {self.temp_dir}")
        
        # 加载架构数据
        self.architecture_data = self.load_architecture()
        
    def load_architecture(self):
        """加载架构文件"""
        try:
            with open(self.architecture_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"无法加载架构文件: {e}")
            return None
            
    def find_implementable_functions(self, data):
        """查找可以实现的函数（所有依赖都已满足）
        
        返回格式：[(file_name, item_name, item), ...]
        """
        implementable = []
        
        # 查找已实现的依赖项
        implemented = {}
        for file_name, content in data.items():
            for kind in ["fields", "defines", "typedefs", "structs", "functions"]:
                if kind not in content:
                    continue
                    
                for item_name, item in content[kind].items():
                    if item.get("conversion_status") == "success":
                        full_id = f"{file_name}::{kind}::{item_name}"
                        implemented[full_id] = True
                        # 对于函数，需要检查是否已有实现
                        if kind == "functions" and not item.get("rust_implementation"):
                            # 检查是否所有依赖都已转换成功
                            deps = item.get("dependencies", {})
                            if all(self._is_dependency_implemented(dep_id, dep_info, data, implemented) 
                                  for dep_id, dep_info in deps.items()):
                                implementable.append((file_name, item_name, item))
        
        return implementable
    
    def _is_dependency_implemented(self, dep_id, dep_info, data, implemented):
        """检查依赖项是否已实现"""
        # 如果依赖项已在实现列表中，则返回True
        if dep_id in implemented:
            return True
            
        # 如果依赖信息不完整，无法检查
        if not dep_info:
            return False
            
        # 获取依赖项的类型和限定名称
        dep_type = dep_info.get("type")
        dep_qualified_name = dep_info.get("qualified_name")
        
        if not dep_type or not dep_qualified_name:
            return False
            
        # 解析依赖名称
        dep_parts = dep_qualified_name.split("::")
        if len(dep_parts) < 2:
            return False
            
        dep_file = dep_parts[0]
        dep_item_name = "::".join(dep_parts[1:])
        
        # 检查依赖项是否已实现
        if dep_file in data and dep_type in data[dep_file] and dep_item_name in data[dep_file][dep_type]:
            return data[dep_file][dep_type][dep_item_name].get("conversion_status") == "success"
            
        return False
    
    def get_dependency_c_code(self, dep_id, dep_info):
        """获取依赖项的原始C代码
        
        Args:
            dep_id: 依赖项ID
            dep_info: 依赖项信息
            
        Returns:
            原始C代码或None
        """
        if not dep_info:
            return None
            
        dep_type = dep_info.get("type")
        dep_qualified_name = dep_info.get("qualified_name")
        
        if not dep_type or not dep_qualified_name:
            return None
            
        # 解析依赖名称
        dep_parts = dep_qualified_name.split("::")
        if len(dep_parts) < 2:
            return None
            
        dep_file = dep_parts[0]
        dep_item_name = "::".join(dep_parts[1:])
        
        # 获取原始C代码
        if dep_file in self.architecture_data and dep_type in self.architecture_data[dep_file]:
            if dep_item_name in self.architecture_data[dep_file][dep_type]:
                return self.architecture_data[dep_file][dep_type][dep_item_name].get("full_text")
        
        return None
        
    def collect_dependency_info(self, deps, data):
        """收集依赖项的签名和摘要信息
        
        Args:
            deps: 依赖项字典
            data: 架构数据
            
        Returns:
            依赖项信息字典 {dep_id: {name, type, rust_signature, rust_implementation, function_summary}, ...}
        """
        dependencies_info = {}
        
        for dep_id, dep_info in deps.items():
            if not dep_info:
                continue
                
            dep_type = dep_info.get("type")
            dep_qualified_name = dep_info.get("qualified_name")
            
            if not dep_type or not dep_qualified_name:
                continue
                
            dep_parts = dep_qualified_name.split("::")
            if len(dep_parts) < 2:
                continue
                
            dep_file = dep_parts[0]
            dep_item_name = "::".join(dep_parts[1:])
            
            # 查找依赖项信息
            if dep_file in data and dep_type in data[dep_file] and dep_item_name in data[dep_file][dep_type]:
                dep_item = data[dep_file][dep_type][dep_item_name]
                
                if dep_item.get("conversion_status") == "success":
                    dependency_info = {
                        "name": dep_item_name,
                        "type": dep_type,
                        "rust_signature": dep_item.get("rust_signature", ""),
                        "c_code": dep_item.get("full_text", "")
                    }
                    
                    # 对于函数类型，添加摘要和实现信息
                    if dep_type == "functions":
                        dependency_info["function_summary"] = dep_item.get("function_summary", "")
                        dependency_info["rust_implementation"] = dep_item.get("rust_implementation", "")
                    
                    dependencies_info[dep_id] = dependency_info
        
        return dependencies_info
    
    def generate_rust_implementation(self, c_code, function_name, rust_signature, dependencies_info):
        """生成Rust函数实现
        
        Args:
            c_code: C函数代码
            function_name: 函数名称
            rust_signature: Rust函数签名
            dependencies_info: 依赖项信息字典
            
        Returns:
            Rust函数实现代码
        """
        logger.info(f"为函数 {function_name} 生成Rust实现")
        
        # 格式化依赖函数信息 - 只包含签名和摘要，不包含完整实现
        function_deps_text = ""
        other_deps_text = ""
        
        for dep_id, info in dependencies_info.items():
            if info["type"] == "functions":
                function_deps_text += f"### 依赖函数: {info['name']}\n"
                function_deps_text += f"签名: {info['rust_signature']}\n"
                if info.get("function_summary"):
                    function_deps_text += f"摘要: {info['function_summary']}\n\n"
                else:
                    function_deps_text += "\n"
            else:
                other_deps_text += f"### 其他依赖项: {dep_id}\n"
                other_deps_text += f"类型: {info['type']}\n"
                other_deps_text += f"Rust签名: {info['rust_signature']}\n\n"
        
        # 定义工具调用说明
        tools_description = """
在生成过程中，你可以使用以下工具获取更多信息:

1. 获取依赖函数的Rust实现代码:
   用法: GET_DEPENDENCY_RUST_CODE(dependency_id)
   例如: GET_DEPENDENCY_RUST_CODE(file_name::functions::some_function)
   
2. 获取依赖函数的原始C代码:
   用法: GET_DEPENDENCY_C_CODE(dependency_id)
   例如: GET_DEPENDENCY_C_CODE(file_name::functions::some_function)

如需使用工具，请使用<tool>工具名(参数)</tool>格式。
"""
        
        prompt = f"""
请将以下C函数转换为功能等价的Rust实现。我们需要的是功能等价而非一比一翻译，请生成符合Rust惯用法的高质量代码。

## C函数代码:
```c
{c_code}
```

## 目标Rust函数签名:
```rust
{rust_signature}
```

## 依赖函数信息（签名和摘要）:
{function_deps_text}

## 其他依赖项:
{other_deps_text}

{tools_description}

## 极其重要的注意事项：
1. 只生成单个函数实现，不要定义任何结构体、类型或其他函数
2. 假设所有依赖项（结构体、类型、函数）都已经在外部定义好
3. 不要重新定义任何现有类型、结构体或枚举
4. 不要在函数外部添加任何代码，只实现函数本身
5. 遵循给定的函数签名，不要修改参数和返回类型

请编写完整的Rust函数实现，遵循以下要求:
1. 严格遵守给定的Rust函数签名
2. 充分利用Rust的安全特性（所有权、借用检查等）
3. 避免unsafe代码，除非绝对必要
4. 使用适当的Rust错误处理方式
5. 保持与原C代码相同的功能逻辑，但可以采用更符合Rust风格的实现方式
6. 添加必要的注释解释复杂逻辑
7. 确保代码符合Rust的惯用做法
8. 如果需要查看依赖函数的实现或原始C代码，可以使用工具调用

只返回最终的Rust函数实现代码，中间的工具调用会被自动处理。
"""
        
        try:
            # 定义对话历史记录
            messages = [
                {"role": "system", "content": "你是一个专业的C到Rust代码转换专家。你的任务是将C代码转换为惯用的Rust实现，保持功能等价，但优化代码风格。你可以使用工具调用获取更多上下文信息。"},
                {"role": "user", "content": prompt}
            ]
            
            # 处理多轮对话，支持工具调用
            max_rounds = 5  # 最大对话轮数
            current_round = 0
            
            while current_round < max_rounds:
                current_round += 1
                
                # 获取模型回复
                response = self.gpt.ask(messages)
                
                # 检查是否有工具调用
                c_code_calls = re.findall(r'<tool>GET_DEPENDENCY_C_CODE\((.*?)\)</tool>', response)
                rust_code_calls = re.findall(r'<tool>GET_DEPENDENCY_RUST_CODE\((.*?)\)</tool>', response)
                
                if not c_code_calls and not rust_code_calls:
                    # 没有工具调用，返回最终结果
                    # 提取代码块
                    code_match = re.search(r"```rust\s*(.*?)\s*```", response, re.DOTALL)
                    if code_match:
                        return code_match.group(1).strip()
                    else:
                        # 如果没有代码块标记，尝试直接使用返回内容
                        return response.strip()
                
                # 处理C代码工具调用
                for dep_id in c_code_calls:
                    # 解析依赖ID
                    dep_parts = dep_id.strip().split("::")
                    if len(dep_parts) >= 3:
                        file_name = dep_parts[0]
                        item_type = dep_parts[1]
                        item_name = "::".join(dep_parts[2:])
                        
                        # 获取依赖项信息
                        if file_name in self.architecture_data and item_type in self.architecture_data[file_name]:
                            if item_name in self.architecture_data[file_name][item_type]:
                                dep_item = self.architecture_data[file_name][item_type][item_name]
                                c_code = dep_item.get("full_text", "未找到原始C代码")
                                
                                # 添加工具调用结果到对话
                                messages.append({"role": "assistant", "content": f"<tool>GET_DEPENDENCY_C_CODE({dep_id})</tool>"})
                                messages.append({"role": "user", "content": f"这是 {dep_id} 的原始C代码:\n```c\n{c_code}\n```\n\n请基于这些信息继续完成转换。"})
                            else:
                                messages.append({"role": "assistant", "content": f"<tool>GET_DEPENDENCY_C_CODE({dep_id})</tool>"})
                                messages.append({"role": "user", "content": f"未找到 {dep_id} 的原始C代码。请基于已有信息完成转换。"})
                        else:
                            messages.append({"role": "assistant", "content": f"<tool>GET_DEPENDENCY_C_CODE({dep_id})</tool>"})
                            messages.append({"role": "user", "content": f"未找到 {dep_id} 的原始C代码。请基于已有信息完成转换。"})
                
                # 处理Rust代码工具调用
                for dep_id in rust_code_calls:
                    # 解析依赖ID
                    dep_parts = dep_id.strip().split("::")
                    if len(dep_parts) >= 3:
                        file_name = dep_parts[0]
                        item_type = dep_parts[1]
                        item_name = "::".join(dep_parts[2:])
                        
                        # 获取依赖项信息
                        if file_name in self.architecture_data and item_type in self.architecture_data[file_name]:
                            if item_name in self.architecture_data[file_name][item_type]:
                                dep_item = self.architecture_data[file_name][item_type][item_name]
                                rust_impl = dep_item.get("rust_implementation", "")
                                
                                if rust_impl:
                                    # 添加工具调用结果到对话
                                    messages.append({"role": "assistant", "content": f"<tool>GET_DEPENDENCY_RUST_CODE({dep_id})</tool>"})
                                    messages.append({"role": "user", "content": f"这是 {dep_id} 的Rust实现:\n```rust\n{rust_impl}\n```\n\n请基于这些信息继续完成转换。"})
                                else:
                                    messages.append({"role": "assistant", "content": f"<tool>GET_DEPENDENCY_RUST_CODE({dep_id})</tool>"})
                                    messages.append({"role": "user", "content": f"未找到 {dep_id} 的Rust实现。请基于已有信息完成转换。"})
                            else:
                                messages.append({"role": "assistant", "content": f"<tool>GET_DEPENDENCY_RUST_CODE({dep_id})</tool>"})
                                messages.append({"role": "user", "content": f"未找到 {dep_id} 的Rust实现。请基于已有信息完成转换。"})
                        else:
                            messages.append({"role": "assistant", "content": f"<tool>GET_DEPENDENCY_RUST_CODE({dep_id})</tool>"})
                            messages.append({"role": "user", "content": f"未找到 {dep_id} 的Rust实现。请基于已有信息完成转换。"})
            
            # 如果超过最大轮数还未完成，返回最后一轮的结果
            response = self.gpt.ask(messages)
            code_match = re.search(r"```rust\s*(.*?)\s*```", response, re.DOTALL)
            if code_match:
                return code_match.group(1).strip()
            else:
                return response.strip()
                
        except Exception as e:
            logger.error(f"生成Rust实现失败: {e}")
            return ""
    
    def collect_full_dependency_chain(self, file_name, function_name, data, collected=None):
        """递归收集完整依赖链
        
        Args:
            file_name: 文件名
            function_name: 函数名
            data: 架构数据
            collected: 已收集的依赖项(递归用)
            
        Returns:
            完整依赖链 {dep_id: dep_info, ...}
        """
        if collected is None:
            collected = {}
            
        # 当前函数的ID
        current_id = f"{file_name}::functions::{function_name}"
        if current_id in collected:
            return collected
            
        # 获取当前函数项
        if file_name in data and "functions" in data[file_name] and function_name in data[file_name]["functions"]:
            function_item = data[file_name]["functions"][function_name]
            
            # 获取直接依赖
            deps = function_item.get("dependencies", {})
            
            # 处理每个依赖
            for dep_id, dep_info in deps.items():
                if dep_info and dep_id not in collected:
                    collected[dep_id] = dep_info
                    
                    # 如果是函数类型，递归处理
                    if dep_info.get("type") == "functions":
                        dep_qualified_name = dep_info.get("qualified_name")
                        if dep_qualified_name:
                            dep_parts = dep_qualified_name.split("::")
                            if len(dep_parts) >= 2:
                                dep_file = dep_parts[0]
                                dep_func_name = "::".join(dep_parts[1:])
                                self.collect_full_dependency_chain(dep_file, dep_func_name, data, collected)
        
        return collected
    
    def fix_implementation(self, function_name, c_code, rust_signature, dependencies_info, 
                         failed_implementation, error_message):
        """修复失败的Rust实现
        
        Args:
            function_name: 函数名称
            c_code: C函数代码
            rust_signature: Rust函数签名
            dependencies_info: 依赖项信息字典
            failed_implementation: 失败的Rust实现
            error_message: 编译错误信息
            
        Returns:
            修复后的Rust实现
        """
        logger.info(f"修复函数 {function_name} 的实现")
        
        # 格式化依赖函数信息 - 只包含签名和摘要，不包含完整实现
        function_deps_text = ""
        other_deps_text = ""
        
        for dep_id, info in dependencies_info.items():
            if info["type"] == "functions":
                function_deps_text += f"### 依赖函数: {info['name']}\n"
                function_deps_text += f"签名: {info['rust_signature']}\n"
                if info.get("function_summary"):
                    function_deps_text += f"摘要: {info['function_summary']}\n\n"
                else:
                    function_deps_text += "\n"
            else:
                other_deps_text += f"### 其他依赖项: {dep_id}\n"
                other_deps_text += f"类型: {info['type']}\n"
                other_deps_text += f"Rust签名: {info['rust_signature']}\n\n"
        
        # 强化过滤编译错误信息，只保留错误，排除所有警告
        error_sections = []
        current_section = []
        in_error_section = False
        in_warning_section = False
        
        for line in error_message.split("\n"):
            line_lower = line.lower()
            
            # 检查是否进入警告部分
            if "warning:" in line_lower:
                in_warning_section = True
                continue
                
            # 检查是否退出警告部分
            if in_warning_section and (not line.strip() or not (line.startswith(" ") or line.startswith("="))):
                in_warning_section = False
                
            # 如果在警告部分中，跳过这一行
            if in_warning_section:
                continue
                
            # 检查是否是错误行开始
            if "error[" in line_lower or "error:" in line_lower:
                # 如果已经在一个错误部分，保存它
                if in_error_section and current_section:
                    error_sections.append("\n".join(current_section))
                    current_section = []
                
                in_error_section = True
                current_section.append(line)
            
            # 如果在错误部分中且行有内容，添加到当前部分
            elif in_error_section and (line.startswith(" ") or line.startswith("=") or line.strip()):
                current_section.append(line)
            
            # 如果在错误部分但遇到空行，结束当前部分
            elif in_error_section and not line.strip():
                error_sections.append("\n".join(current_section))
                current_section = []
                in_error_section = False
        
        # 添加最后一个错误部分（如果有）
        if in_error_section and current_section:
            error_sections.append("\n".join(current_section))
        
        # 过滤掉任何包含"warning"的部分
        error_sections = [section for section in error_sections if "warning:" not in section.lower()]
        
        # 合并所有错误部分
        filtered_error = "\n\n".join(error_sections)
        
        # 确保至少保留一部分错误信息
        if not filtered_error and "error" in error_message.lower():
            # 简单提取所有带有"error"的行
            error_lines = [line for line in error_message.split("\n") if "error:" in line.lower() or "error[" in line.lower()]
            filtered_error = "\n".join(error_lines)
        
        # 定义工具调用说明
        tools_description = """
在修复过程中，你可以使用以下工具获取更多信息:

1. 获取依赖函数的Rust实现代码:
   用法: GET_DEPENDENCY_RUST_CODE(dependency_id)
   例如: GET_DEPENDENCY_RUST_CODE(file_name::functions::some_function)
   
2. 获取依赖函数的原始C代码:
   用法: GET_DEPENDENCY_C_CODE(dependency_id)
   例如: GET_DEPENDENCY_C_CODE(file_name::functions::some_function)

如需使用工具，请使用<tool>工具名(参数)</tool>格式。
"""
        
        prompt = f"""
请修复以下Rust函数实现中的编译错误。

## C函数原始代码:
```c
{c_code}
```

## Rust函数签名:
```rust
{rust_signature}
```

## 依赖函数信息（签名和摘要）:
{function_deps_text}

## 其他依赖项:
{other_deps_text}

## 当前Rust实现(有错误):
```rust
{failed_implementation}
```

## 编译错误信息:
```
{filtered_error}
```

{tools_description}

## 极其重要的注意事项：
1. 只生成单个函数实现，不要定义任何结构体、类型或其他函数
2. 假设所有依赖项（结构体、类型、函数）都已经在外部定义好
3. 不要重新定义任何现有类型、结构体或枚举
4. 不要在函数外部添加任何代码，只实现函数本身
5. 遵循给定的函数签名，不要修改参数和返回类型
6. 只专注于修复错误，不要重写整个函数逻辑（除非必要）

请修复上述编译错误，提供正确的Rust函数实现。遵循以下要求:
1. 严格遵守给定的Rust函数签名
2. 充分利用Rust的安全特性（所有权、借用检查等）
3. 避免unsafe代码，除非绝对必要
4. 解决所有编译错误
5. 保持与原C代码相同的功能逻辑
6. 如果需要查看依赖函数的实现或原始C代码，可以使用工具调用

只返回最终的Rust函数实现代码，不需要解释。中间的工具调用会被自动处理。
"""
        
        try:
            # 定义对话历史记录
            messages = [
                {"role": "system", "content": "你是一个专业的Rust代码修复专家。你的任务是修复Rust代码中的编译错误，保持功能等价性。你可以使用工具调用获取更多上下文信息。"},
                {"role": "user", "content": prompt}
            ]
            
            # 处理多轮对话，支持工具调用
            max_rounds = 5  # 最大对话轮数
            current_round = 0
            
            while current_round < max_rounds:
                current_round += 1
                
                # 获取模型回复
                response = self.gpt.ask(messages)
                
                # 检查是否有工具调用
                c_code_calls = re.findall(r'<tool>GET_DEPENDENCY_C_CODE\((.*?)\)</tool>', response)
                rust_code_calls = re.findall(r'<tool>GET_DEPENDENCY_RUST_CODE\((.*?)\)</tool>', response)
                
                if not c_code_calls and not rust_code_calls:
                    # 没有工具调用，返回最终结果
                    # 提取代码块
                    code_match = re.search(r"```rust\s*(.*?)\s*```", response, re.DOTALL)
                    if code_match:
                        return code_match.group(1).strip()
                    else:
                        # 如果没有代码块标记，尝试直接使用返回内容
                        return response.strip()
                
                # 处理C代码工具调用
                for dep_id in c_code_calls:
                    # 解析依赖ID
                    dep_parts = dep_id.strip().split("::")
                    if len(dep_parts) >= 3:
                        file_name = dep_parts[0]
                        item_type = dep_parts[1]
                        item_name = "::".join(dep_parts[2:])
                        
                        # 获取依赖项信息
                        if file_name in self.architecture_data and item_type in self.architecture_data[file_name]:
                            if item_name in self.architecture_data[file_name][item_type]:
                                dep_item = self.architecture_data[file_name][item_type][item_name]
                                c_code = dep_item.get("full_text", "未找到原始C代码")
                                
                                # 添加工具调用结果到对话
                                messages.append({"role": "assistant", "content": f"<tool>GET_DEPENDENCY_C_CODE({dep_id})</tool>"})
                                messages.append({"role": "user", "content": f"这是 {dep_id} 的原始C代码:\n```c\n{c_code}\n```\n\n请基于这些信息继续修复。"})
                            else:
                                messages.append({"role": "assistant", "content": f"<tool>GET_DEPENDENCY_C_CODE({dep_id})</tool>"})
                                messages.append({"role": "user", "content": f"未找到 {dep_id} 的原始C代码。请基于已有信息完成修复。"})
                        else:
                            messages.append({"role": "assistant", "content": f"<tool>GET_DEPENDENCY_C_CODE({dep_id})</tool>"})
                            messages.append({"role": "user", "content": f"未找到 {dep_id} 的原始C代码。请基于已有信息完成修复。"})
                
                # 处理Rust代码工具调用
                for dep_id in rust_code_calls:
                    # 解析依赖ID
                    dep_parts = dep_id.strip().split("::")
                    if len(dep_parts) >= 3:
                        file_name = dep_parts[0]
                        item_type = dep_parts[1]
                        item_name = "::".join(dep_parts[2:])
                        
                        # 获取依赖项信息
                        if file_name in self.architecture_data and item_type in self.architecture_data[file_name]:
                            if item_name in self.architecture_data[file_name][item_type]:
                                dep_item = self.architecture_data[file_name][item_type][item_name]
                                rust_impl = dep_item.get("rust_implementation", "")
                                
                                if rust_impl:
                                    # 添加工具调用结果到对话
                                    messages.append({"role": "assistant", "content": f"<tool>GET_DEPENDENCY_RUST_CODE({dep_id})</tool>"})
                                    messages.append({"role": "user", "content": f"这是 {dep_id} 的Rust实现:\n```rust\n{rust_impl}\n```\n\n请基于这些信息继续修复。"})
                                else:
                                    messages.append({"role": "assistant", "content": f"<tool>GET_DEPENDENCY_RUST_CODE({dep_id})</tool>"})
                                    messages.append({"role": "user", "content": f"未找到 {dep_id} 的Rust实现。请基于已有信息完成修复。"})
                            else:
                                messages.append({"role": "assistant", "content": f"<tool>GET_DEPENDENCY_RUST_CODE({dep_id})</tool>"})
                                messages.append({"role": "user", "content": f"未找到 {dep_id} 的Rust实现。请基于已有信息完成修复。"})
                        else:
                            messages.append({"role": "assistant", "content": f"<tool>GET_DEPENDENCY_RUST_CODE({dep_id})</tool>"})
                            messages.append({"role": "user", "content": f"未找到 {dep_id} 的Rust实现。请基于已有信息完成修复。"})
            
            # 如果超过最大轮数还未完成，返回最后一轮的结果
            response = self.gpt.ask(messages)
            code_match = re.search(r"```rust\s*(.*?)\s*```", response, re.DOTALL)
            if code_match:
                return code_match.group(1).strip()
            else:
                return response.strip()
                
        except Exception as e:
            logger.error(f"修复Rust实现失败: {e}")
            return failed_implementation
    
    def run_differential_fuzzing(self, function_name, c_code, rust_implementation, dependencies_info):
        """运行差分模糊测试，验证Rust实现与C实现的功能等价性
        
        Args:
            function_name: 函数名称
            c_code: C函数代码
            rust_implementation: Rust函数实现
            dependencies_info: 依赖项信息字典
            
        Returns:
            (测试成功标志, 测试结果信息)
        """
        logger.info(f"为函数 {function_name} 运行差分模糊测试")
        
        # 创建差分测试项目
        test_dir = os.path.join(self.temp_dir, f"diff_test_{function_name}")
        os.makedirs(test_dir, exist_ok=True)
        
        # 生成测试代码
        test_code = self.generate_fuzzing_test_code(function_name, c_code, rust_implementation, dependencies_info)
        
        # 保存测试代码到文件
        test_file_path = os.path.join(test_dir, "fuzzing_test.rs")
        with open(test_file_path, "w") as f:
            f.write(test_code)
        
        # 创建Cargo.toml
        cargo_file_path = os.path.join(test_dir, "Cargo.toml")
        with open(cargo_file_path, "w") as f:
            f.write("""
[package]
name = "diff_test"
version = "0.1.0"
edition = "2021"

[dependencies]
libc = "0.2"
rand = "0.8"
            """)
        
        # 运行测试
        try:
            result = subprocess.run(
                ["cargo", "test"],
                cwd=test_dir,
                capture_output=True,
                text=True,
                timeout=60
            )
            
            if result.returncode == 0:
                return True, "差分测试通过"
            else:
                return False, f"差分测试失败:\n{result.stderr}"
        except subprocess.TimeoutExpired:
            return False, "差分测试超时"
        except Exception as e:
            return False, f"差分测试异常: {str(e)}"
    
    def generate_fuzzing_test_code(self, function_name, c_code, rust_implementation, dependencies_info):
        """生成差分模糊测试代码
        
        Args:
            function_name: 函数名称
            c_code: C函数代码
            rust_implementation: Rust函数实现
            dependencies_info: 依赖项信息字典
            
        Returns:
            测试代码
        """
        # 格式化依赖项信息
        deps_text = ""
        for dep_id, info in dependencies_info.items():
            deps_text += f"### 依赖项: {dep_id}\n"
            deps_text += f"类型: {info['type']}\n"
            deps_text += f"Rust签名: {info['rust_signature']}\n"
            if info.get("rust_implementation"):
                deps_text += f"实现:\n```rust\n{info['rust_implementation']}\n```\n\n"
            else:
                deps_text += "\n"
        
        prompt = f"""
请为以下函数创建一个差分模糊测试(Differential Fuzzing Test)，用于验证Rust实现与原始C实现的行为一致性。

## C函数代码:
```c
{c_code}
```

## Rust函数实现:
```rust
{rust_implementation}
```

## 依赖项:
{deps_text}

请创建完整的Rust测试代码，包括:
1. 将C代码封装为FFI函数
2. 生成随机测试输入的代码
3. 同时调用C和Rust实现的代码
4. In检查结果是否一致的逻辑

测试应该:
- 随机生成有效的输入数据
- 同时调用C和Rust实现
- 比较结果是否一致
- 报告任何差异

请提供完整的测试代码，可以直接编译运行。
"""
        
        try:
            messages = [
                {"role": "system", "content": "你是一个专业的测试工程师，擅长编写跨语言差分测试。"},
                {"role": "user", "content": prompt}
            ]
            response = self.gpt.ask(messages)
            
            # 提取代码块
            code_match = re.search(r"```rust\s*(.*?)\s*```", response, re.DOTALL)
            if code_match:
                return code_match.group(1).strip()
            else:
                # 如果没有代码块标记，尝试直接使用返回内容
                return response.strip()
        except Exception as e:
            logger.error(f"生成差分测试代码失败: {e}")
            return "// 无法生成差分测试代码"
    
    def implement_function(self, file_name, function_name, item, data):
        """实现单个函数的Rust代码
        
        Args:
            file_name: 文件名
            function_name: 函数名
            item: 函数项信息
            data: 架构数据
            
        Returns:
            成功标志
        """
        logger.info(f"开始处理函数: {file_name}::{function_name}")
        
        # 获取C代码
        c_code = item.get("full_text", "")
        if not c_code:
            logger.error(f"函数 {function_name} 缺少C代码")
            return False
        
        # 获取Rust签名
        rust_signature = item.get("rust_signature", "")
        if not rust_signature:
            logger.error(f"函数 {function_name} 缺少Rust签名")
            return False
        
        # 1. 收集完整依赖链
        full_deps = self.collect_full_dependency_chain(file_name, function_name, data)
        logger.info(f"函数 {function_name} 的完整依赖链包含 {len(full_deps)} 个项")
        
        # 2. 收集依赖项信息
        dependencies_info = self.collect_dependency_info(full_deps, data)
        logger.debug(f"函数 {function_name} 的依赖项: {list(dependencies_info.keys())}")
        
        # 3. 生成Rust实现
        rust_implementation = self.generate_rust_implementation(
            c_code, function_name, rust_signature, dependencies_info
        )
        
        if not rust_implementation:
            logger.error(f"无法为函数 {function_name} 生成Rust实现")
            return False
        
        logger.debug(f"函数 {function_name} 的Rust实现: {rust_implementation}")
        
        # 4. 验证编译
        project_dir = RustCompiler.create_test_project(
            function_name, rust_implementation, dependencies_info, self.temp_dir
        )
        success, error_message = RustCompiler.verify_compilation(project_dir)
        
        # 如果编译失败，尝试修复实现
        if not success:
            logger.warning(f"函数 {function_name} 的Rust实现编译失败: {error_message}")
            
            # 最多尝试3次修复
            for attempt in range(3):
                logger.info(f"尝试修复函数 {function_name} 的实现 (第 {attempt+1} 次)")
                
                # 修复实现
                rust_implementation = self.fix_implementation(
                    function_name, c_code, rust_signature, dependencies_info, 
                    rust_implementation, error_message
                )
                
                # 再次验证编译
                project_dir = RustCompiler.create_test_project(
                    function_name, rust_implementation, dependencies_info, self.temp_dir
                )
                success, error_message = RustCompiler.verify_compilation(project_dir)
                
                if success:
                    logger.info(f"函数 {function_name} 的Rust实现修复成功")
                    break
                    
                logger.warning(f"函数 {function_name} 的修复后实现仍编译失败: {error_message}")
            
            if not success:
                logger.error(f"无法修复函数 {function_name} 的Rust实现")
                item["implementation_status"] = "failed"
                item["implementation_error"] = error_message
                return False
        
        # 保存实现到数据中
        item["rust_implementation"] = rust_implementation
        item["implementation_status"] = "success"
        
        # 5. 运行差分模糊测试(可选)
        # fuzzing_success, fuzzing_result = self.run_differential_fuzzing(
        #     function_name, c_code, rust_implementation, dependencies_info
        # )
        # item["fuzzing_result"] = fuzzing_result
        # item["fuzzing_status"] = "success" if fuzzing_success else "failed"
        
        logger.info(f"函数 {function_name} 的Rust实现成功")
        return True
    
    def implement_all(self, max_items=None):
        """实现所有可实现的函数
        
        Args:
            max_items: 最大处理项数
            
        Returns:
            成功标志
        """
        # 加载架构数据
        data = self.load_architecture()
        if not data:
            return False
        
        # 查找可实现的函数
        implementable = self.find_implementable_functions(data)
        logger.info(f"找到 {len(implementable)} 个可实现的函数")
        
        if max_items:
            implementable = implementable[:max_items]
            logger.info(f"将处理前 {max_items} 个函数")
        
        # 实现函数
        success_count = 0
        for i, (file_name, function_name, item) in enumerate(implementable):
            logger.info(f"处理函数 [{i+1}/{len(implementable)}]: {file_name}::{function_name}")
            
            try:
                if self.implement_function(file_name, function_name, item, data):
                    success_count += 1
                    
                    # 每实现几个函数，保存一次中间结果
                    if success_count % 5 == 0:
                        self.save_results(data)
            except Exception as e:
                logger.error(f"处理函数 {function_name} 时出错: {e}")
                logger.error(traceback.format_exc())
        
        # 保存最终结果
        self.save_results(data)
        
        logger.info(f"函数实现完成，共成功: {success_count}/{len(implementable)}")
        return True
    
    def save_results(self, data):
        """保存结果到输出文件"""
        try:
            with open(self.output_file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=4)
            logger.info(f"结果已保存到: {self.output_file}")
            return True
        except Exception as e:
            logger.error(f"保存结果失败: {e}")
            return False
    
    def cleanup(self):
        """清理临时文件"""
        try:
            shutil.rmtree(self.temp_dir)
            logger.info(f"已清理临时目录: {self.temp_dir}")
        except Exception as e:
            logger.error(f"清理临时目录失败: {e}") 