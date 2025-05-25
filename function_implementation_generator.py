import json
import os
import sys
import time
import logging
import traceback
import re
from datetime import datetime

# 导入工具模块
from sig_utils.gpt_client import GPT
from sig_utils.stats_collector import ConversionStats
from sig_utils.text_extractor import TextExtractor
from sig_utils.prompt_templates import PromptTemplates

# 导入C2Rust转换器中的功能
from c2rust_converter_new import Logger, C2RustConverter

# 配置目录
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_DIR = os.path.join(BASE_DIR, "logs")
DATA_DIR = os.path.join(BASE_DIR, "data")
os.makedirs(LOG_DIR, exist_ok=True)
os.makedirs(DATA_DIR, exist_ok=True)

# 配置日志
main_logger = Logger("func_impl_main")
interaction_logger = Logger("func_impl_interaction")
stats_logger = Logger("func_impl_stats", console_output=False)
item_logger = Logger("func_impl_items", console_output=False)
ai_dialog_logger = Logger("func_impl_ai_dialog", console_output=False)

class FunctionImplementationGenerator:
    """函数实现生成器 - 将函数摘要转换为具体的Rust实现"""
    
    def __init__(self, api_key, model="gpt-4o"):
        main_logger.info("初始化函数实现生成器")
        self.agent1 = GPT(api_key, model_name=model)  # 实现生成专家
        self.agent2 = GPT(api_key, model_name=model)  # 实现审核专家
        self.stats = ConversionStats()
        
        # 编译检查器（从C2Rust转换器中借用）
        self.c2r_converter = C2RustConverter(api_key, enable_compile_check=True, max_fix_rounds=5)
        main_logger.info("✅ 初始化完成 - 使用模型: " + model)
    
    def generate_implementation_from_json(self, json_file, output_file=None, max_functions=None):
        """从JSON文件中生成函数实现"""
        main_logger.info(f"开始从JSON生成函数实现: {json_file}")
        
        # 读取JSON文件
        try:
            with open(json_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except Exception as e:
            main_logger.error(f"读取JSON文件失败: {e}")
            return False
        
        # 默认输出文件名
        if output_file is None:
            output_file = os.path.join(DATA_DIR, "implemented_functions.json")
        
        # 检查输出文件是否已存在，如果存在则加载已处理的内容
        processed_functions = set()
        if os.path.exists(output_file):
            try:
                with open(output_file, 'r', encoding='utf-8') as f:
                    existing_data = json.load(f)
                    for file_name, content in existing_data.items():
                        if "functions" in content:
                            for func_name, func_info in content["functions"].items():
                                if func_info.get("implementation_status") == "success":
                                    processed_functions.add(f"{file_name}::functions::{func_name}")
                                    main_logger.info(f"跳过已处理的函数: {func_name}")
            except Exception as e:
                main_logger.warning(f"读取现有输出文件失败，将创建新文件: {e}")
                existing_data = {}
        else:
            existing_data = {}
        
        # 复制原始数据结构
        result = data.copy() if not existing_data else existing_data
        
        # 跟踪已经实现的函数
        implemented_functions = processed_functions.copy()  # 初始化为已处理的函数
        
        # 统计信息
        total_functions = 0
        success_count = 0
        failure_count = 0
        skipped_count = 0
        
        # 计算总函数数量
        for file_name, content in data.items():
            if "functions" in content:
                for func_name, func_info in content["functions"].items():
                    if "function_summary" in func_info and "rust_signature" in func_info:
                        total_functions += 1
        
        main_logger.info(f"找到 {total_functions} 个可实现函数")
        
        # 实现计数器
        implemented_count = 0
        
        # 遍历所有文件和函数
        for file_name, content in data.items():
            # 确保文件结构在结果中存在
            if file_name not in result:
                result[file_name] = {}
            if "functions" not in result[file_name]:
                result[file_name]["functions"] = {}
                
            # 如果文件没有函数，跳过
            if "functions" not in content:
                continue
                
            # 遍历所有函数
            for func_name, func_info in content["functions"].items():
                # 生成完整函数ID
                func_id = f"{file_name}::functions::{func_name}"
                
                # 如果已处理过，跳过
                if func_id in processed_functions:
                    skipped_count += 1
                    main_logger.debug(f"跳过已处理的函数: {func_name}")
                    continue
                
                # 确保函数结构在结果中存在
                if func_name not in result[file_name]["functions"]:
                    result[file_name]["functions"][func_name] = {}
                
                # 检查是否有必要的信息进行实现
                if not self._has_required_info(func_info):
                    main_logger.warning(f"函数 {func_name} 缺少摘要或签名，跳过")
                    result[file_name]["functions"][func_name]["implementation_status"] = "skipped"
                    result[file_name]["functions"][func_name]["reason"] = "缺少必要信息(摘要或签名)"
                    skipped_count += 1
                    continue
                
                # 检查依赖项是否已实现
                dependencies = func_info.get("dependencies", {})
                if not self._check_dependencies_implemented(dependencies, implemented_functions):
                    main_logger.info(f"函数 {func_name} 的依赖项尚未全部实现，暂时跳过")
                    skipped_count += 1
                    continue
                
                # 显示进度
                implemented_count += 1
                progress = f"[{implemented_count}/{total_functions}]"
                main_logger.info(f"{progress} 开始生成函数实现: {func_name}")
                
                try:
                    # 提取所需信息
                    func_summary = func_info.get("function_summary", {})
                    rust_signature = func_info.get("rust_signature", "")
                    
                    # 收集依赖项信息
                    dependency_info = self._collect_dependency_info(data, dependencies)
                    
                    # 生成并审核函数实现
                    implementation_result = self.generate_with_review_cycle(
                        func_name, 
                        rust_signature, 
                        func_summary, 
                        dependency_info
                    )
                    
                    if implementation_result["success"]:
                        # 进行编译检查 - 传递完整的数据
                        compile_result = self._check_compilation(
                            implementation_result["implementation"],
                            dependency_info["code_signatures"],
                            data  # 传递完整的数据
                        )
                        
                        # 如果编译通过
                        if compile_result["success"]:
                            implementation = implementation_result["implementation"]
                            result[file_name]["functions"][func_name]["rust_implementation"] = implementation
                            result[file_name]["functions"][func_name]["implementation_status"] = "success"
                            result[file_name]["functions"][func_name]["review_rounds"] = implementation_result.get("review_rounds", 1)
                            main_logger.info(f"{progress} ✅ 成功生成并通过编译: {func_name} (审核轮次: {implementation_result.get('review_rounds', 1)})")
                            success_count += 1
                            implemented_functions.add(func_id)  # 添加到已实现集合
                        else:
                            # 编译失败，尝试修复
                            main_logger.warning(f"{progress} ⚠️ 编译失败，尝试修复: {func_name}")
                            fix_result = self._fix_implementation(
                                implementation_result["implementation"],
                                compile_result["errors"],
                                dependency_info["code_signatures"],
                                data  # 传递完整的数据
                            )
                            
                            if fix_result["success"]:
                                # 修复成功
                                implementation = fix_result["implementation"]
                                result[file_name]["functions"][func_name]["rust_implementation"] = implementation
                                result[file_name]["functions"][func_name]["implementation_status"] = "success"
                                result[file_name]["functions"][func_name]["required_fix"] = True
                                result[file_name]["functions"][func_name]["review_rounds"] = implementation_result.get("review_rounds", 1)
                                result[file_name]["functions"][func_name]["fix_rounds"] = fix_result["rounds"]
                                main_logger.info(f"{progress} ✅ 修复成功: {func_name} (审核轮次: {implementation_result.get('review_rounds', 1)}, 修复轮次: {fix_result['rounds']})")
                                success_count += 1
                                implemented_functions.add(func_id)  # 添加到已实现集合
                            else:
                                # 修复失败
                                result[file_name]["functions"][func_name]["implementation_status"] = "failed"
                                result[file_name]["functions"][func_name]["reason"] = "编译错误修复失败"
                                result[file_name]["functions"][func_name]["compile_errors"] = compile_result["errors"]
                                result[file_name]["functions"][func_name]["last_attempt"] = implementation_result["implementation"]
                                main_logger.error(f"{progress} ❌ 编译错误修复失败: {func_name}")
                                failure_count += 1
                    else:
                        # 实现失败
                        result[file_name]["functions"][func_name]["implementation_status"] = "failed"
                        result[file_name]["functions"][func_name]["reason"] = implementation_result["error"]
                        if "last_attempt" in implementation_result:
                            result[file_name]["functions"][func_name]["last_attempt"] = implementation_result["last_attempt"]
                        main_logger.error(f"{progress} ❌ 实现失败: {func_name}")
                        failure_count += 1
                
                except Exception as e:
                    # 处理异常
                    error_msg = f"处理函数 {func_name} 时发生错误: {str(e)}"
                    main_logger.error(error_msg)
                    main_logger.error(traceback.format_exc())
                    result[file_name]["functions"][func_name]["implementation_status"] = "error"
                    result[file_name]["functions"][func_name]["reason"] = error_msg
                    failure_count += 1
                
                # 定期保存结果
                if implemented_count % 5 == 0:
                    with open(output_file, 'w', encoding='utf-8') as f:
                        json.dump(result, f, indent=4, ensure_ascii=False)
                    main_logger.info(f"已处理 {implemented_count} 个函数，中间结果已保存")
                
                # 如果设置了最大处理函数数，检查是否达到
                if max_functions and implemented_count >= max_functions:
                    main_logger.info(f"已达到最大处理函数数 {max_functions}，停止处理")
                    break
            
            # 如果已达到最大处理数量，跳出循环
            if max_functions and implemented_count >= max_functions:
                break
        
        # 保存最终结果
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(result, f, indent=4, ensure_ascii=False)
        
        # 输出统计信息
        main_logger.info("="*60)
        main_logger.info(f"函数实现生成完成！总计: {total_functions} 个函数")
        main_logger.info(f"成功: {success_count}, 失败: {failure_count}, 跳过: {skipped_count}")
        main_logger.info(f"结果已保存到: {output_file}")
        main_logger.info("="*60)
        
        return result
    
    def _has_required_info(self, func_info):
        """检查函数是否有足够的信息进行实现"""
        # 必须有函数摘要和Rust签名
        has_summary = "function_summary" in func_info and isinstance(func_info["function_summary"], dict)
        has_signature = "rust_signature" in func_info and isinstance(func_info["rust_signature"], str)
        
        # 函数摘要中必须有main_purpose
        if has_summary:
            has_main_purpose = "main_purpose" in func_info["function_summary"]
        else:
            has_main_purpose = False
        
        return has_signature and has_main_purpose
    
    def _collect_dependency_info(self, data, dependencies):
        """收集依赖项的信息"""
        dependency_info = {
            "function_deps": {},   # 函数依赖: {dep_id: {signature, summary}}
            "other_deps": {},      # 非函数依赖: {dep_id: signature}
            "code_signatures": {}  # 所有依赖的签名: {dep_id: code}
        }
        
        if not dependencies:
            return dependency_info
        
        # 遍历所有依赖项
        for dep_id, dep_info in dependencies.items():
            # 跳过没有类型或限定名的依赖
            if not dep_info or "type" not in dep_info or "qualified_name" not in dep_info:
                continue
            
            dep_type = dep_info["type"]
            qualified_name = dep_info["qualified_name"]
            
            # 解析qualified_name获取文件名和项目名
            parts = qualified_name.split("::")
            if len(parts) < 2:
                continue
            
            file_name = parts[0]
            item_name = "::".join(parts[1:])
            
            # 跳过在数据中找不到的文件
            if file_name not in data:
                continue
            
            # 对于函数依赖
            if dep_type == "functions":
                if "functions" in data[file_name] and item_name in data[file_name]["functions"]:
                    func_info = data[file_name]["functions"][item_name]
                    
                    # 获取函数签名
                    signature = func_info.get("rust_signature", "")
                    
                    # 获取函数摘要的main_purpose
                    summary = None
                    if "function_summary" in func_info and "main_purpose" in func_info["function_summary"]:
                        summary = func_info["function_summary"]["main_purpose"]
                    
                    if signature:
                        dependency_info["function_deps"][dep_id] = {
                            "signature": signature,
                            "summary": summary
                        }
                        dependency_info["code_signatures"][dep_id] = signature
            
            # 对于其他类型依赖
            else:
                if dep_type in data[file_name] and item_name in data[file_name][dep_type]:
                    # 获取签名
                    signature = data[file_name][dep_type][item_name].get("rust_signature", "")
                    
                    if signature:
                        dependency_info["other_deps"][dep_id] = signature
                        dependency_info["code_signatures"][dep_id] = signature
        
        return dependency_info
    def _check_dependencies_implemented(self, dependencies, implemented_functions):
        """检查所有函数依赖是否已实现"""
        if not dependencies:
            return True
        
        missing_deps = []
        for dep_id, dep_info in dependencies.items():
            if not dep_info or "type" not in dep_info or "qualified_name" not in dep_info:
                continue
            
            dep_type = dep_info["type"]
            qualified_name = dep_info["qualified_name"]
            
            # 只检查函数类型的依赖
            if dep_type == "functions":
                parts = qualified_name.split("::")
                if len(parts) < 2:
                    continue
                
                file_name = parts[0]
                item_name = "::".join(parts[1:])
                
                dep_full_id = f"{file_name}::functions::{item_name}"
                if dep_full_id not in implemented_functions:
                    missing_deps.append(dep_id)
        
        if missing_deps:
            main_logger.debug(f"未实现的依赖项: {', '.join(missing_deps)}")
            return False
        return True    
    def generate_with_review_cycle(self, func_name, rust_signature, func_summary, dependency_info, max_review_rounds=3):
        """生成函数实现并与审核AI交互循环，直到审核通过或达到最大轮数"""
        main_logger.info(f"为函数 {func_name} 启动生成-审核循环")
        
        # 检查基本参数
        if not rust_signature or not func_summary:
            return {
                "success": False,
                "error": "缺少函数签名或摘要信息"
            }
        
        # 提取摘要信息
        main_purpose = func_summary.get("main_purpose", "")
        detailed_logic = func_summary.get("detailed_logic", "")
        error_handling = func_summary.get("error_handling", "")
        
        if not main_purpose:
            return {
                "success": False,
                "error": "缺少函数主要目的描述"
            }
        
        # 构建函数依赖列表
        function_deps_text = ""
        if dependency_info["function_deps"]:
            function_deps_text = "### 函数依赖项:\n"
            for dep_id, dep_data in dependency_info["function_deps"].items():
                function_deps_text += f"#### {dep_id}\n```rust\n{dep_data['signature']}\n```\n"
                if dep_data["summary"]:
                    function_deps_text += f"主要功能: {dep_data['summary']}\n\n"
        
        # 构建其他依赖列表
        other_deps_text = ""
        if dependency_info["other_deps"]:
            other_deps_text = "### 其他依赖项:\n"
            for dep_id, signature in dependency_info["other_deps"].items():
                other_deps_text += f"#### {dep_id}\n```rust\n{signature}\n```\n\n"
        
        # 构建初始实现提示
        initial_prompt = f"""为这个Rust函数实现代码:

    ## 函数签名:
    ```rust
    {rust_signature}
    ```

    ## 函数摘要:
    - **主要目的**: {main_purpose}
    """

        # 添加详细逻辑和错误处理（如果有）
        if detailed_logic:
            initial_prompt += f"- **详细逻辑**: {detailed_logic}\n"
        if error_handling:
            initial_prompt += f"- **错误处理**: {error_handling}\n"
        
        # 添加依赖信息
        if function_deps_text or other_deps_text:
            initial_prompt += "\n## 依赖项:\n" + function_deps_text + other_deps_text
        
        # 添加实现指南
        initial_prompt += """
    ## 实现要求:
    1. 完全遵循函数签名，不要修改签名部分
    2. 基于函数摘要中描述的功能实现代码
    3. 处理所有可能的错误情况
    4. 使用提供的依赖项（如果有）
    5. 代码要简洁高效，符合Rust的习惯用法
    6. 不要添加use语句或其他导入语句
    7. 只返回函数实现代码，无需解释

    直接返回实现代码:
    ```rust
    // 你的实现代码...
    ```
    """
        
        # 生成-审核循环
        current_implementation = None
        review_history = []
        success = False
        
        for review_round in range(1, max_review_rounds + 1):
            main_logger.info(f"开始第 {review_round}/{max_review_rounds} 轮生成-审核")
            
            try:
                # 构建当前轮次的生成提示
                if review_round == 1:
                    # 首轮使用初始提示
                    generation_messages = [
                        {"role": "system", "content": "你是一个专业的Rust开发专家，擅长将函数描述转换为高质量的代码。请直接输出代码，不要添加任何解释或导入语句。"},
                        {"role": "user", "content": initial_prompt}
                    ]
                else:
                    # 后续轮次加入审核反馈
                    last_review = review_history[-1]
                    feedback_prompt = f"""请根据审核意见修改Rust函数实现:

    ## 函数签名:
    ```rust
    {rust_signature}
    ```

    ## 函数摘要:
    - **主要目的**: {main_purpose}
    """
                    if detailed_logic:
                        feedback_prompt += f"- **详细逻辑**: {detailed_logic}\n"
                    if error_handling:
                        feedback_prompt += f"- **错误处理**: {error_handling}\n"
                    
                    if function_deps_text or other_deps_text:
                        feedback_prompt += "\n## 依赖项:\n" + function_deps_text + other_deps_text
                    
                    feedback_prompt += f"""
    ## 当前实现:
    ```rust
    {current_implementation}
    ```

    ## 审核意见:
    {last_review["reason"]}

    问题:
    {', '.join(last_review.get("issues", ["无具体问题"]))}

    建议:
    {', '.join(last_review.get("suggestions", ["无具体建议"]))}

    ## 修改要求:
    1. 根据审核意见修改代码
    2. 不要修改函数签名
    3. 不要添加use语句或其他导入语句
    4. 只返回修改后的完整函数实现

    直接返回修改后的实现代码:
    ```rust
    // 修改后的实现代码...
    ```
    """
                    generation_messages = [
                        {"role": "system", "content": "你是一个专业的Rust开发专家，擅长将函数描述转换为高质量的代码。请直接输出代码，不要添加任何解释或导入语句。"},
                        {"role": "user", "content": feedback_prompt}
                    ]
                
                # 记录对话
                ai_dialog_logger.info(f"=========== 函数 {func_name} 第 {review_round} 轮生成 ===========")
                ai_dialog_logger.info(f"生成提示: {generation_messages[1]['content']}")
                
                # 调用AI生成实现 - 使用消息数组格式
                response = self.agent1.ask(generation_messages)
                ai_dialog_logger.info(f"AI生成回复: {response}")
                
                # 提取代码
                implementation_code = TextExtractor.extract_code_block(response)
                
                if not implementation_code:
                    # 如果找不到代码块，尝试直接使用整个响应
                    implementation_code = response.strip()
                    # 继续尝试过滤，只保留看起来像代码的部分
                    if "fn " in implementation_code:
                        start_idx = implementation_code.find("fn ")
                        implementation_code = implementation_code[start_idx:].strip()
                
                # 如果还是无法获得有效代码
                if not implementation_code or "fn " not in implementation_code:
                    return {
                        "success": False,
                        "error": "无法提取实现代码",
                        "last_attempt": response
                    }
                
                # 更新当前实现
                current_implementation = implementation_code
                
                # 验证实现是否与签名匹配
                if not self._is_valid_implementation(rust_signature, current_implementation):
                    main_logger.warning(f"函数 {func_name} 的实现与签名不匹配，尝试修复")
                    fixed_implementation = self._fix_implementation_signature(rust_signature, current_implementation)
                    
                    if fixed_implementation:
                        current_implementation = fixed_implementation
                    else:
                        return {
                            "success": False,
                            "error": "实现与签名不匹配，无法修复",
                            "last_attempt": current_implementation
                        }
                
                # 审核实现
                review_messages = [
                    {"role": "system", "content": "你是一个严格的Rust代码审核专家，负责评估函数实现是否符合要求和最佳实践。"},
                    {"role": "user", "content": self._build_review_prompt(func_name, rust_signature, current_implementation, func_summary)}
                ]
                
                review_response = self.agent2.ask(review_messages)
                ai_dialog_logger.info(f"AI审核回复: {review_response}")
                
                # 提取JSON结果
                review_result = TextExtractor.extract_json(review_response)
                
                if not review_result or "passed" not in review_result:
                    # 如果JSON解析失败，尝试从文本判断是否通过
                    passed = "passed" in review_response.lower() and not ("not passed" in review_response.lower() or "failed" in review_response.lower())
                    review_result = {
                        "passed": passed,
                        "reason": "无法解析JSON结果，基于文本判断",
                        "issues": [],
                        "suggestions": []
                    }
                
                # 记录审核结果
                review_history.append(review_result)
                
                # 检查是否通过审核
                if review_result["passed"]:
                    main_logger.info(f"函数 {func_name} 第 {review_round} 轮审核通过")
                    success = True
                    break
                else:
                    main_logger.warning(f"函数 {func_name} 第 {review_round} 轮审核未通过: {review_result['reason']}")
                    
                    # 如果达到最大轮数，使用最后一个版本
                    if review_round >= max_review_rounds:
                        main_logger.warning(f"函数 {func_name} 达到最大审核轮数 {max_review_rounds}")
                        # 如果最后一轮审核问题不严重，也视为成功
                        if "minor" in review_result["reason"].lower() or "小问题" in review_result["reason"]:
                            main_logger.info(f"函数 {func_name} 最终版本问题较小，视为可接受")
                            success = True
                        break
            
            except Exception as e:
                error_msg = f"生成或审核过程发生错误: {str(e)}"
                main_logger.error(error_msg)
                ai_dialog_logger.error(error_msg)
                return {
                    "success": False,
                    "error": error_msg,
                    "last_attempt": current_implementation if current_implementation else "无有效实现"
                }
        
        # 返回结果
        if success:
            return {
                "success": True,
                "implementation": current_implementation,
                "review_rounds": len(review_history),
                "review_history": review_history
            }
        else:
            return {
                "success": False,
                "error": f"审核未通过，达到最大轮数 {max_review_rounds}",
                "last_attempt": current_implementation,
                "review_history": review_history
            }
    def _build_review_prompt(self, func_name, rust_signature, implementation, func_summary):
        """构建审核提示"""
        # 提取摘要信息
        main_purpose = func_summary.get("main_purpose", "")
        detailed_logic = func_summary.get("detailed_logic", "")
        error_handling = func_summary.get("error_handling", "")
        
        # 构建审核提示
        review_prompt = f"""审核这个Rust函数的实现，评估它是否正确、完整、高效：

    ## 原始函数签名:
    ```rust
    {rust_signature}
    ```

    ## 函数摘要:
    - **主要目的**: {main_purpose}
    """

        # 添加详细逻辑和错误处理（如果有）
        if detailed_logic:
            review_prompt += f"- **详细逻辑**: {detailed_logic}\n"
        if error_handling:
            review_prompt += f"- **错误处理**: {error_handling}\n"
        
        # 添加实现代码
        review_prompt += f"""
    ## 实现代码:
    ```rust
    {implementation}
    ```

    ## 审核标准:
    1. 实现是否完全符合函数签名
    2. 实现是否完全符合函数描述的目的和逻辑
    3. 错误处理是否充分
    4. 代码是否简洁高效、符合Rust习惯
    5. 是否有潜在的bug或内存安全问题
    6. 确认没有不必要的导入语句

    请按照以下格式返回审核结果:
    ```json
    {{
    "passed": true/false,
    "reason": "通过或失败的理由",
    "issues": ["问题1", "问题2", ...],
    "suggestions": ["建议1", "建议2", ...]
    }}
    ```
    """
        return review_prompt
    def _review_implementation(self, func_name, rust_signature, implementation, func_summary):
        """审核函数实现"""
        main_logger.info(f"审核函数 {func_name} 的实现")
        
        # 提取摘要信息
        main_purpose = func_summary.get("main_purpose", "")
        detailed_logic = func_summary.get("detailed_logic", "")
        error_handling = func_summary.get("error_handling", "")
        
        # 构建审核提示
        review_prompt = f"""审核这个Rust函数的实现，评估它是否正确、完整、高效：

## 原始函数签名:
```rust
{rust_signature}
```

## 函数摘要:
- **主要目的**: {main_purpose}
"""

        # 添加详细逻辑和错误处理（如果有）
        if detailed_logic:
            review_prompt += f"- **详细逻辑**: {detailed_logic}\n"
        if error_handling:
            review_prompt += f"- **错误处理**: {error_handling}\n"
        
        # 添加实现代码
        review_prompt += f"""
## 实现代码:
```rust
{implementation}
```

## 审核标准:
1. 实现是否完全符合函数签名
2. 实现是否完全符合函数描述的目的和逻辑
3. 错误处理是否充分
4. 代码是否简洁、高效、符合Rust习惯
5. 是否有潜在的bug或内存安全问题
6. 确认没有不必要的导入语句

请按照以下格式返回审核结果:
```json
{{
  "passed": true/false,
  "reason": "通过或失败的理由",
  "issues": ["问题1", "问题2", ...],
  "suggestions": ["建议1", "建议2", ...]
}}
```
"""
        
        # 记录对话
        ai_dialog_logger.info(f"=========== 审核函数 {func_name} 的实现 ===========")
        ai_dialog_logger.info(f"审核提示: {review_prompt}")
        
        try:
            # 调用AI进行审核 - 使用消息数组格式
            response = self.agent2.ask([
                {"role": "system", "content": "你是一个严格的Rust代码审核专家，负责评估函数实现是否符合要求和最佳实践。"},
                {"role": "user", "content": review_prompt}
            ])
            
            ai_dialog_logger.info(f"AI审核回复: {response}")
            
            # 提取JSON结果
            result_json = TextExtractor.extract_json(response)
            
            if not result_json or "passed" not in result_json:
                # 如果JSON解析失败，尝试从文本判断是否通过
                passed = "passed" in response.lower() and not ("not passed" in response.lower() or "failed" in response.lower())
                result_json = {
                    "passed": passed,
                    "reason": "无法解析JSON结果，基于文本判断",
                    "issues": [],
                    "suggestions": []
                }
            
            return result_json
            
        except Exception as e:
            error_msg = f"审核实现时发生错误: {str(e)}"
            main_logger.error(error_msg)
            ai_dialog_logger.error(error_msg)
            return {
                "passed": False,
                "reason": error_msg,
                "issues": ["审核过程发生错误"],
                "suggestions": []
            }
    
    def _is_valid_implementation(self, signature, implementation):
        """验证实现是否与签名匹配"""
        # 从签名中提取函数名和参数
        sig_match = re.search(r'fn\s+(\w+)\s*\((.*?)\)', signature)
        if not sig_match:
            return False
        
        func_name = sig_match.group(1)
        
        # 从实现中查找相同的函数定义
        impl_match = re.search(r'fn\s+(\w+)\s*\((.*?)\)', implementation)
        if not impl_match:
            return False
        
        impl_name = impl_match.group(1)
        
        # 检查函数名是否匹配
        return func_name == impl_name
    
    def _fix_implementation_signature(self, signature, implementation):
        """修复实现以匹配签名"""
        # 提取签名中的函数名和参数部分
        sig_match = re.search(r'fn\s+(\w+)\s*\((.*?)\)(\s*->\s*[^{]+)?', signature)
        if not sig_match:
            return None
        
        func_name = sig_match.group(1)
        params = sig_match.group(2)
        return_type = sig_match.group(3) if sig_match.group(3) else ""
        
        # 查找实现中的函数体
        impl_match = re.search(r'{([\s\S]*)}$', implementation)
        if not impl_match:
            return None
        
        func_body = impl_match.group(1)
        
        # 构建修复后的实现
        fixed_impl = f"fn {func_name}({params}){return_type} {{\n{func_body}\n}}"
        
        return fixed_impl
    
    def _check_compilation(self, implementation, dependencies, data):
        """检查函数实现是否能编译通过，包含完整的依赖环境"""
        main_logger.info("检查函数实现的编译状态")
        
        import tempfile
        import subprocess
        import os
        
        # 创建临时项目目录
        with tempfile.TemporaryDirectory() as temp_dir:
            # 创建Cargo.toml
            with open(os.path.join(temp_dir, "Cargo.toml"), "w") as f:
                f.write("""[package]
    name = "rust_implementation_check"
    version = "0.1.0"
    edition = "2021"

    [dependencies]
    libc = "0.2"
    """)
            
            # 创建src目录
            src_dir = os.path.join(temp_dir, "src")
            os.makedirs(src_dir, exist_ok=True)
            
            # 创建main.rs
            with open(os.path.join(src_dir, "main.rs"), "w", encoding="utf-8") as f:
                f.write("// 自动生成的编译验证代码\n")
                f.write("#![allow(unused_variables, dead_code, unused_imports, non_camel_case_types, non_snake_case, non_upper_case_globals)]\n\n")
                
                # 添加常用导入
                f.write("use std::os::raw::*;\n")
                f.write("use std::ptr;\n")
                f.write("use std::ffi::c_void;\n")
                f.write("extern crate libc;\n\n")
                
                f.write("fn main() {}\n\n")
                
                # 收集并去重所有类型定义
                if data:
                    # 用于去重的字典，键为"kind::实际类型名"
                    all_converted_items = {}
                    skipped_items = []
                    
                    # 1. 收集非函数项（类型定义、结构体等）
                    for file_name, content in data.items():
                        for kind in ["fields", "defines", "typedefs", "structs"]:
                            if kind not in content:
                                continue
                            
                            for item_name, item_data in content[kind].items():
                                if "rust_signature" in item_data:
                                    rust_code = item_data.get("rust_signature", "").strip()
                                    if rust_code:
                                        # 提取实际类型名（用于去重）
                                        actual_type_name = self._extract_type_name_from_code(rust_code, kind)
                                        if actual_type_name:
                                            # 创建唯一键
                                            unique_key = f"{kind}::{actual_type_name}"
                                            
                                            # 去重：如果已有同名定义，跳过
                                            if unique_key in all_converted_items:
                                                skipped_items.append({
                                                    "id": f"{file_name}::{kind}::{item_name}",
                                                    "type": actual_type_name,
                                                    "reason": f"已存在定义，来自 {all_converted_items[unique_key]['file']}::{all_converted_items[unique_key]['kind']}::{all_converted_items[unique_key]['name']}"
                                                })
                                                continue
                                            
                                            # 记录新项
                                            all_converted_items[unique_key] = {
                                                "id": f"{file_name}::{kind}::{item_name}",
                                                "name": item_name,
                                                "file": file_name,
                                                "kind": kind,
                                                "code": rust_code,
                                                "actual_name": actual_type_name,
                                                "priority": 1  # 非函数项优先
                                            }
                    
                    # 2. 收集已实现的函数（无需去重）
                    implemented_functions = []
                    for file_name, content in data.items():
                        if "functions" not in content:
                            continue
                        
                        for func_name, func_info in content["functions"].items():
                            if func_info.get("implementation_status") == "success" and "rust_implementation" in func_info:
                                rust_code = func_info.get("rust_implementation", "").strip()
                                if rust_code:
                                    implemented_functions.append({
                                        "id": f"{file_name}::functions::{func_name}",
                                        "name": func_name,
                                        "file": file_name,
                                        "kind": "functions",
                                        "code": rust_code,
                                        "priority": 2  # 函数实现次优先
                                    })
                    
                    # 按优先级排序，先输出类型定义，再输出函数实现
                    all_items = list(all_converted_items.values()) + implemented_functions
                    all_items.sort(key=lambda x: x["priority"])
                    
                    # 记录去重信息
                    if skipped_items:
                        main_logger.debug(f"编译检查：跳过了 {len(skipped_items)} 个重复定义")
                        for item in skipped_items[:3]:  # 仅显示前3个
                            main_logger.debug(f"  - 跳过 {item['id']} (类型: {item['type']}), 原因: {item['reason']}")
                    
                    # 写入所有依赖项
                    f.write("// ================ 所有类型定义和已实现函数 ================\n\n")
                    
                    for item in all_items:
                        f.write(f"// 来自 {item['file']}::{item['kind']}::{item['name']}\n")
                        f.write(f"{item['code']}\n\n")
                
                # 添加直接依赖项（向后兼容）
                if dependencies:
                    f.write("// ================ 直接依赖项 ================\n\n")
                    for dep_id, dep_code in dependencies.items():
                        f.write(f"// 依赖: {dep_id}\n")
                        f.write(f"{dep_code}\n\n")
                
                # 添加当前要验证的函数实现
                f.write("// ================ 当前验证的函数实现 ================\n\n")
                f.write(implementation)
            
            # 运行cargo check
            try:
                result = subprocess.run(
                    ["cargo", "check"],
                    cwd=temp_dir,
                    capture_output=True,
                    text=True,
                    timeout=30
                )
                
                # 提取编译错误
                errors = []
                if result.returncode != 0:
                    stderr = result.stderr
                    lines = stderr.split("\n")
                    current_error = []
                    in_error = False
                    
                    for line in lines:
                        # 检测错误开始
                        if 'error[' in line or line.strip().startswith('error:'):
                            if current_error:
                                errors.append("\n".join(current_error))
                            current_error = [line]
                            in_error = True
                        # 继续收集错误信息
                        elif in_error and (line.startswith('  ') or line.startswith(' -->') or line.strip().startswith('|')):
                            current_error.append(line)
                        # 空行可能表示错误结束
                        elif in_error and line.strip() == '':
                            if current_error:
                                errors.append("\n".join(current_error))
                            current_error = []
                            in_error = False
                    
                    # 添加最后一个错误
                    if current_error and in_error:
                        errors.append("\n".join(current_error))
                
                return {
                    "success": result.returncode == 0,
                    "stderr": result.stderr,
                    "stdout": result.stdout,
                    "errors": errors
                }
                
            except subprocess.TimeoutExpired:
                return {
                    "success": False,
                    "stderr": "编译超时",
                    "stdout": "",
                    "errors": ["编译超时"]
                }
            except FileNotFoundError:
                return {
                    "success": False,
                    "stderr": "未找到cargo命令，请确保已安装Rust",
                    "stdout": "",
                    "errors": ["未找到cargo命令"]
                }

    def _extract_type_name_from_code(self, code, kind):
        """从代码中提取类型名，用于去重"""
        import re
        
        # 匹配不同类型的定义
        if kind == "structs":
            # 结构体定义
            match = re.search(r'(?:pub\s+)?struct\s+(\w+)', code)
            if match:
                return match.group(1)
        elif kind == "typedefs":
            # 类型别名定义
            match = re.search(r'(?:pub\s+)?type\s+(\w+)\s*=', code)
            if match:
                return match.group(1)
        elif kind == "defines":
            # 常量定义
            match = re.search(r'(?:pub\s+)?const\s+(\w+):', code)
            if match:
                return match.group(1)
        elif kind == "fields":
            # 字段/变量定义
            match = re.search(r'(?:pub\s+)?static(?:\s+mut)?\s+(\w+):', code)
            if match:
                return match.group(1)
        
        # 如果没有匹配到任何模式，返回None
        return None
    def _fix_implementation(self, implementation, compile_errors, dependencies, data):
        """修复编译错误"""
        main_logger.info(f"开始修复编译错误 (共 {len(compile_errors)} 个)")
        
        # 使用C2Rust转换器的错误修复功能
        max_fix_rounds = 5
        rounds = 0
        current_impl = implementation
        
        for round_num in range(1, max_fix_rounds + 1):
            main_logger.info(f"修复轮次 {round_num}/{max_fix_rounds}")
            
            # 提取最关键的错误消息（用于提示）
            error_summaries = []
            for error in compile_errors[:5]:  # 仅使用前5个错误
                # 尝试提取错误的第一行作为摘要
                error_lines = error.strip().split('\n')
                if error_lines:
                    error_line = error_lines[0].strip()
                    # 如果是长行，只取前150个字符
                    if len(error_line) > 150:
                        error_line = error_line[:150] + "..."
                    error_summaries.append(error_line)
            
            # 构建错误修复的提示
            fix_prompt = f"""修复这个Rust函数实现中的编译错误:

    ## 当前实现:
    ```rust
    {current_impl}
    ```

    ## 编译错误:
    {chr(10).join(error_summaries)}

    ## 修复要求:
    1. 保持函数签名不变，只修改实现部分
    2. 修复所有编译错误
    3. 不要改变函数的基本行为和算法
    4. 确保代码简洁、高效
    5. 不要添加任何导入语句，编译环境已经提供了所有必要的类型和函数定义

    直接返回修复后的完整函数实现:
    ```rust
    // 修复后的代码...
    ```
    """
            
            # 记录对话
            ai_dialog_logger.info(f"=========== 修复轮次 {round_num}/{max_fix_rounds} ===========")
            ai_dialog_logger.info(f"修复提示: {fix_prompt}")
            
            try:
                # 调用AI进行修复 - 使用消息数组格式
                response = self.agent1.ask([
                    {"role": "system", "content": "你是一个专门修复Rust编译错误的专家。请直接返回修复后的代码，不要添加任何解释或导入语句。"},
                    {"role": "user", "content": fix_prompt}
                ])
                
                ai_dialog_logger.info(f"AI修复回复: {response}")
                
                # 提取代码块
                fixed_code = TextExtractor.extract_code_block(response)
                
                if not fixed_code:
                    # 如果找不到代码块，尝试直接使用整个响应
                    fixed_code = response.strip()
                    # 继续尝试过滤，只保留看起来像代码的部分
                    if "fn " in fixed_code:
                        start_idx = fixed_code.find("fn ")
                        fixed_code = fixed_code[start_idx:].strip()
                
                # 如果还是无法获得有效代码
                if not fixed_code or "fn " not in fixed_code:
                    main_logger.warning(f"无法提取修复代码，跳过轮次 {round_num}")
                    continue
                
                # 更新当前实现
                current_impl = fixed_code
                rounds = round_num
                
                # 重新检查编译 - 使用完整的数据参数
                compile_result = self._check_compilation(current_impl, dependencies, data)
                
                if compile_result["success"]:
                    # 修复成功
                    main_logger.info(f"✅ 编译错误修复成功，用了 {round_num} 轮")
                    return {
                        "success": True,
                        "implementation": current_impl,
                        "rounds": round_num
                    }
                else:
                    # 更新错误列表
                    compile_errors = compile_result["errors"]
                    main_logger.warning(f"轮次 {round_num} 后仍有 {len(compile_errors)} 个编译错误")
                    
                    # 如果是最后一轮，返回失败
                    if round_num >= max_fix_rounds:
                        main_logger.error("达到最大修复轮数，修复失败")
                        break
            
            except Exception as e:
                error_msg = f"修复过程发生错误: {str(e)}"
                main_logger.error(error_msg)
                ai_dialog_logger.error(error_msg)
                break
        
        # 修复失败
        return {
            "success": False,
            "implementation": current_impl,
            "rounds": rounds,
            "error": "达到最大修复轮数仍未解决编译错误"
        }
def main():
    """主程序入口"""
    import argparse
    
    # 定义参数
    parser = argparse.ArgumentParser(description="Rust函数实现生成器")
    parser.add_argument("--input", "-i", help="输入JSON文件路径", default="data/converted_architecture_with_summaries.json")
    parser.add_argument("--output", "-o", help="输出JSON文件路径", default="data/implemented_functions.json")
    parser.add_argument("--max", "-m", type=int, help="最大处理函数数量", default=None)
    parser.add_argument("--api-key", "-k", help="OpenAI API密钥", default=None)
    parser.add_argument("--model", help="使用的AI模型", default="gpt-4o")
    parser.add_argument("--test", "-t", action="store_true", help="测试模式，只处理1个函数")
    parser.add_argument("--generate-validation", "-v", action="store_true", help="生成验证项目")
    parser.add_argument("--validation-dir", default="validation_project", help="验证项目输出目录")
    
    args = parser.parse_args()
    
    # 使用环境变量或默认值
    api_key = args.api_key or os.environ.get("OPENAI_API_KEY") or "sk-Wx9RbmSNFH5Q1BbhpoVdRzoLka4ATPeO16qoDwe13YEF71qJ"
    
    # 测试模式只处理1个函数
    max_functions = 1 if args.test else args.max
    
    # 初始化生成器
    generator = FunctionImplementationGenerator(api_key, model=args.model)
    
    # 生成函数实现
    result = generator.generate_implementation_from_json(
        args.input, 
        args.output, 
        max_functions
    )
    
    # 生成验证项目
    if args.generate_validation:
        # 重新加载结果数据
        with open(args.output, 'r', encoding='utf-8') as f:
            result_data = json.load(f)
        
        generator.generate_validation_project(result_data, args.validation_dir)
        main_logger.info(f"验证项目已生成到: {args.validation_dir}")
        main_logger.info("要验证实现正确性，请执行:")
        main_logger.info(f"  cd {args.validation_dir}")
        main_logger.info("  cargo check")

if __name__ == "__main__":
    main()