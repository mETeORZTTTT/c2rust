import json
import time
import logging
import os
import sys
import traceback
import re
import copy  # 添加深拷贝支持
from datetime import datetime

# 配置根日志器，禁止显示详细信息
logging.basicConfig(level=logging.WARNING)  # 只显示警告级别以上的信息

# 导入工具模块
from sig_utils.gpt_client import GPT
from sig_utils.stats_collector import ConversionStats
from sig_utils.c_preprocessor import CPreprocessor
from sig_utils.text_extractor import TextExtractor
from sig_utils.prompt_templates import PromptTemplates
from sig_utils.cross_file_validator import CrossFileValidator  # 新增跨文件验证器
from sig_utils.ai_implementation_detector import get_detector, quick_check_implementation  # 新增AI检测器

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
        self.logger.propagate = False  # 禁止日志向上传播到root logger
        
        # 确保处理器不会重复添加
        if not self.logger.handlers:
            # 文件处理器，使用固定文件名而非时间戳
            file_handler = logging.FileHandler(
                os.path.join(log_dir, f"{name}.log"), 
                encoding="utf-8",
                mode='w'  # 使用'w'模式，每次运行覆盖之前的日志
            )
            file_handler.setLevel(logging.DEBUG)
            
            # 格式化器
            formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
            file_handler.setFormatter(formatter)
            
            self.logger.addHandler(file_handler)
            
            # 只有在需要控制台输出时才添加控制台处理器
            if console_output:
                # 控制台处理器
                console_handler = logging.StreamHandler()
                console_handler.setLevel(logging.INFO)
                console_handler.setFormatter(formatter)
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
        """确保日志立即写入文件"""
        for handler in self.logger.handlers:
            handler.flush()

# 主日志
main_logger = Logger("c2rust_main")
interaction_logger = Logger("c2rust_interaction")
stats_logger = Logger("c2rust_stats")
item_logger = Logger("c2rust_items", console_output=False)  # 专门记录每个项目的转换细节，不输出到控制台
ai_dialog_logger = Logger("c2rust_ai_dialog", console_output=False)  # 专门记录AI对话内容

# C到Rust转换器
class C2RustConverter:
    def __init__(self, api_key, enable_compile_check=False, max_fix_rounds=5):
        main_logger.info("初始化C到Rust转换器")
        self.agent1 = GPT(api_key, model_name="gpt-4o")  # 转换专家
        self.agent2 = GPT(api_key, model_name="gpt-4o")  # 审核专家
        self.agent3 = GPT(api_key, model_name="gpt-4o")  # 仲裁专家
        self.stats = ConversionStats()
        self.preprocessor = CPreprocessor()
        self.enable_compile_check = enable_compile_check
        self.max_fix_rounds = max_fix_rounds
        
        # 跨文件验证器 - 现在主要用于记录，不强制验证
        self.cross_file_validator = CrossFileValidator()
        main_logger.info("✅ 跨文件验证器已启用（记录模式）")
        
        # 移除代码清理器，只使用AI检测器
        # self.code_sanitizer = get_sanitizer()
        # main_logger.info("🛡️ 代码清理器已启用（AI行为强制约束）")
        
        # AI实现检测器 - 用AI检测AI的额外实现
        self.ai_detector = get_detector(api_key)
        main_logger.info("🤖 AI实现检测器已启用（AI互相检测，不通过就重新生成）")
        
        if enable_compile_check:
            main_logger.info("✅ 已启用额外的详细编译验证")
            main_logger.info(f"📝 最大修复轮数: {max_fix_rounds}")
        else:
            main_logger.info("📝 使用AI检测器验证模式")
    
    def convert_with_dependencies(self, item_id, kind, c_code, dependency_code=None, max_rounds=5, max_arbitration=1, data=None, file_name=None):
        """转换单个C代码项为Rust代码，包含依赖项信息"""
        main_logger.info(f"开始转换 [{kind}]: {item_id}，含 {len(dependency_code) if dependency_code else 0} 个依赖项")
        item_logger.info(f"==================== 开始转换 [{kind}]: {item_id} ====================")
        item_logger.info(f"C代码:\n{c_code}")
        
        # 记录AI对话开始
        ai_dialog_logger.info(f"==================== AI对话开始 [{kind}]: {item_id} ====================")
        ai_dialog_logger.info(f"输入C代码: {c_code}")
        
        if dependency_code:
            item_logger.info(f"依赖项数量: {len(dependency_code)}")
            ai_dialog_logger.info(f"依赖项数量: {len(dependency_code)}")
            for dep_id, dep_code in dependency_code.items():
                item_logger.debug(f"依赖项 {dep_id}:\n{dep_code}")
                ai_dialog_logger.debug(f"依赖项 {dep_id}: {dep_code}")
                
        self.stats.record_start(item_id, kind)
        
        # 预处理C代码
        preprocessed = self.preprocessor.preprocess(c_code)
        special_constructs = preprocessed["special_constructs"]
        
        # 检查是否为头文件保护宏
        if kind == "define" and preprocessed.get("is_header_guard", False):
            main_logger.info(f"检测到头文件保护宏，跳过转换: {item_id}")
            item_logger.info(f"检测到头文件保护宏，跳过转换")
            ai_dialog_logger.info(f"检测到头文件保护宏，跳过转换")
            item_logger.info(f"==================== 结束转换 [{kind}]: {item_id} ====================\n")
            
            # 记录跳过的头文件保护宏
            self.stats.record_success(item_id, kind, 0, {
                "c_code": c_code,
                "rust_code": "// 头文件保护宏在Rust中不需要，已忽略"
            }, is_skipped=True)
            
            return {
                "success": True,
                "rust_code": "// 头文件保护宏在Rust中不需要，已忽略",
                "rounds": 0,
                "conversion_history": [],
                "is_header_guard": True
            }
        
        # 准备特殊结构信息
        special_structures_text = ""
        for construct_type, items in special_constructs.items():
            if items:
                special_structures_text += f"- {construct_type}: {len(items)}个\n"
                for item in items[:3]:  # 仅展示前3个
                    special_structures_text += f"  * {item['full_text']}\n"
        
        # 准备依赖项信息
        dependencies_text = ""
        if dependency_code:
            dependencies_text = "\n## 依赖项的Rust代码：\n"
            for dep_id, rust_code in dependency_code.items():
                dependencies_text += f"### {dep_id}\n```rust\n{rust_code}\n```\n\n"
        
        # 构建JSON格式的提示
        json_prompt = f"""请将以下C语言定义转换为Rust代码，并以JSON格式返回结果：

## 原始C代码：
```c
{c_code}
```
"""
        
        # 检查是否为函数指针类型定义
        is_function_pointer = (kind == "typedefs" and 
                             "(" in c_code and ")" in c_code and 
                             (c_code.strip().endswith(")") or "(*" in c_code))
        
        if is_function_pointer:
            json_prompt += """
## 特别注意：函数指针类型转换
这是一个函数指针类型定义。请转换为Rust的函数类型：
- C格式：`typedef return_type FuncName(param_types)`
- Rust格式：`type FuncName = fn(param_types) -> return_type;`
- 如果涉及C ABI，使用：`type FuncName = unsafe extern "C" fn(param_types) -> return_type;`
- 只输出一行类型定义，不要添加其他代码
"""
            
            if special_structures_text:
                json_prompt += f"""
## 代码分析
我已检测到代码中包含以下特殊结构，请在转换时特别注意：
{special_structures_text}
"""
            
            if dependencies_text:
                json_prompt += f"""
{dependencies_text}
请在转换时参考上述依赖项的Rust代码，保持一致的风格和命名。
"""
            
            # 添加对函数的特殊指示
            if kind == "function":
                json_prompt += """
## 特别注意
只转换函数签名，不实现函数体。函数体使用 { unimplemented!() } 或 { todo!() } 占位。
"""
            
        json_prompt += """
## 转换要求
请按照Rust的惯用法进行转换，尽量使用安全Rust特性，只在必要时使用unsafe。
注意处理指针、特殊类型和命名规范。如果使用unsafe，请添加注释解释原因。

**重要：不要生成任何导入语句（use、mod等），只生成核心的类型定义、结构体或函数签名。**

## 输出格式
请以JSON格式返回转换结果，包含以下字段：
```json
{
  "rust_code": "转换后的Rust代码",
  "confidence": "HIGH/MEDIUM/LOW",
  "warnings": ["警告信息列表"],
  "unsafe_used": true/false,
  "unsafe_reason": "如果使用了unsafe，请说明原因"
}
```

只返回JSON对象，不要添加其他文本。
"""
        
        messages = [
            {"role": "system", "content": PromptTemplates.AGENT1_SYSTEM},
            {"role": "user", "content": json_prompt}
        ]
        
        # 记录初始对话
        ai_dialog_logger.info(f"系统提示: {PromptTemplates.AGENT1_SYSTEM}")
        ai_dialog_logger.info(f"用户提示: {json_prompt}")
        
        conversion_history = []
        arbitration_count = 0
        
        # 转换循环
        for round_num in range(1, max_rounds + 1):
            item_logger.info(f"开始第 {round_num} 轮转换")
            
            try:
                # 1. 获取Agent1的转换结果
                item_logger.info(f"第 {round_num} 轮: 正在获取转换结果...")
                start_time = time.time()
                rust_response_raw = self.agent1.ask(messages)
                ai_dialog_logger.info(f"转换轮 {round_num} - Agent1回复: {rust_response_raw}")
                item_logger.info(f"第 {round_num} 轮: 获取转换结果用时 {time.time() - start_time:.2f} 秒")
                
                # 解析JSON响应
                rust_response_json = TextExtractor.extract_json(rust_response_raw)
                if not rust_response_json:
                    # 如果JSON解析失败，尝试提取代码块作为备选
                    item_logger.warning("JSON解析失败，尝试提取代码块")
                    rust_code = TextExtractor.extract_code_block(rust_response_raw)
                    rust_response_json = {
                        "rust_code": rust_code,
                        "confidence": "LOW",
                        "warnings": ["JSON格式解析失败，使用备选方案"],
                        "unsafe_used": "unsafe" in rust_code.lower(),
                        "unsafe_reason": "未提供原因"
                    }
                
                rust_code = rust_response_json.get("rust_code", "")
                
                # 验证提取的代码是否正确
                if "json" in rust_code.lower() or "{" in rust_code and "}" in rust_code and "rust_code" in rust_code:
                    main_logger.warning(f"检测到转换代码提取错误，包含JSON格式文本")
                    ai_dialog_logger.warning(f"转换代码提取错误，当前内容: {rust_code}")
                    
                    # 如果是第一轮就出现提取错误，说明TextExtractor有bug，尝试重新开始
                    if round_num == 1:
                        main_logger.warning(f"第一轮转换即出现代码提取错误，重新开始转换: {item_id}")
                        # 重新开始转换，但限制重试次数
                        if not hasattr(self, '_restart_count'):
                            self._restart_count = {}
                        
                        restart_key = f"{item_id}_{kind}"
                        current_restarts = self._restart_count.get(restart_key, 0)
                        
                        if current_restarts < 2:  # 最多重启2次
                            self._restart_count[restart_key] = current_restarts + 1
                            main_logger.info(f"重新开始转换 (第 {current_restarts + 1} 次重启): {item_id}")
                            ai_dialog_logger.info(f"重新开始转换 (第 {current_restarts + 1} 次重启)")
                            
                            # 重置消息历史，重新开始
                            messages = [
                                {"role": "system", "content": PromptTemplates.AGENT1_SYSTEM},
                                {"role": "user", "content": json_prompt}
                            ]
                            conversion_history = []
                            continue  # 重新开始当前轮次
                        else:
                            main_logger.error(f"代码提取错误重启次数已达上限，转换失败: {item_id}")
                            break
                    
                    # 尝试从JSON响应中提取纯代码
                    if rust_response_json and "rust_code" in rust_response_json:
                        pure_code = rust_response_json["rust_code"]
                        if pure_code and not ("json" in pure_code.lower() or "{" in pure_code and "rust_code" in pure_code):
                            rust_code = pure_code
                            main_logger.info(f"已修正转换代码提取：{rust_code[:50]}...")
                        else:
                            # 如果修正也失败，这轮转换视为失败，跳到下一轮
                            main_logger.warning(f"代码提取修正失败，跳过当前轮: {round_num}")
                            continue
                
                # 保存转换尝试
                attempt_record = {
                    "round": round_num,
                    "rust_code": rust_code,
                    "json_response": rust_response_json
                }
                conversion_history.append(attempt_record)
                
                # 格式化转换历史文本
                history_text = "\n\n## 转换历史：\n"
                for i, attempt in enumerate(conversion_history, 1):
                    history_text += f"### 尝试 {i}：\n```rust\n{attempt['rust_code']}\n```\n"
                    if "json_response" in attempt:
                        json_resp = attempt["json_response"]
                        history_text += f"置信度: {json_resp.get('confidence', 'UNKNOWN')}\n"
                        if json_resp.get("warnings"):
                            history_text += f"警告: {', '.join(json_resp['warnings'])}\n"
                        if json_resp.get("unsafe_used"):
                            history_text += f"Unsafe原因: {json_resp.get('unsafe_reason', '未说明')}\n"
                    if "review" in attempt:
                        history_text += f"审核结果: {attempt['review']['result']}\n"
                        history_text += f"原因: {attempt['review']['reason']}\n"
                    if "compile_result" in attempt:
                        compile_res = attempt["compile_result"]
                        history_text += f"编译结果: {'成功' if compile_res['success'] else '失败'}\n"
                        if not compile_res["success"] and compile_res["errors"]:
                            history_text += f"编译错误: {len(compile_res['errors'])} 个错误\n"
                    if "fix_result" in attempt:
                        fix_res = attempt["fix_result"]
                        history_text += f"修复结果: {'成功' if fix_res['success'] else '失败'}\n"
                        if fix_res.get("fix_rounds"):
                            history_text += f"修复轮数: {fix_res['fix_rounds']}\n"
                    history_text += "\n"
                
                # 2. 让Agent2审核结果
                item_logger.info(f"第 {round_num} 轮: 开始审核转换结果...")
                start_time = time.time()
                review_prompt = PromptTemplates.AGENT2_WITH_HISTORY
                review_prompt = review_prompt.replace("{c_code}", c_code)
                review_prompt = review_prompt.replace("{rust_code}", rust_code)
                review_prompt = review_prompt.replace("{conversion_history}", history_text)
                
                review_messages = [
                    {"role": "system", "content": PromptTemplates.AGENT2_SYSTEM},
                    {"role": "user", "content": review_prompt}
                ]
                
                # 记录审核对话
                ai_dialog_logger.info(f"审核轮 {round_num} - 系统提示: {PromptTemplates.AGENT2_SYSTEM}")
                ai_dialog_logger.info(f"审核轮 {round_num} - 用户提示: {review_prompt}")
                
                try:
                    review_response = self.agent2.ask(review_messages)
                    ai_dialog_logger.info(f"审核轮 {round_num} - Agent2回复: {review_response}")
                    item_logger.info(f"第 {round_num} 轮: 审核结果获取用时 {time.time() - start_time:.2f} 秒")
                    review_json = TextExtractor.extract_json(review_response)
                    
                    if not review_json:
                        item_logger.warning("无法解析审核结果JSON，尝试再次解析")
                        # 尝试简单的解析方案
                        if '"result": "PASS"' in review_response:
                            review_json = {"result": "PASS", "reason": "审核通过"}
                        elif '"result": "FAIL"' in review_response:
                            reason_match = re.search(r'"reason":\s*"([^"]+)"', review_response)
                            reason = reason_match.group(1) if reason_match else "未通过审核，但未提供具体原因"
                            review_json = {"result": "FAIL", "reason": reason}
                        else:
                            review_json = {"result": "FAIL", "reason": "无法解析审核结果"}
                            item_logger.warning(f"无法解析的审核响应: {review_response[:200]}...")
                    
                    # 记录审核结果
                    attempt_record["review"] = review_json
                    item_logger.info(f"审核结果: {review_json['result']}")
                    item_logger.debug(f"审核原因: {review_json['reason']}")
                    
                except Exception as e:
                    item_logger.error(f"审核过程发生错误: {str(e)}")
                    ai_dialog_logger.error(f"审核轮 {round_num} 错误: {str(e)}")
                    attempt_record["review"] = {"result": "ERROR", "reason": f"审核过程错误: {str(e)}"}
                    # 如果是第一轮，直接失败；否则尝试使用上一轮结果继续
                    if round_num == 1:
                        raise
                    item_logger.warning("由于审核错误，将使用上一轮结果继续")
                    review_json = {"result": "FAIL", "reason": "审核过程发生错误，将重新尝试"}
                
                # 3. 根据审核结果决定下一步
                if review_json["result"] == "PASS":
                    # 审核通过，进行AI实现检测
                    main_logger.info(f"🤖 第 {round_num} 轮: 开始AI实现检测...")
                    
                    # 收集已知依赖项
                    known_dependencies = []
                    if dependency_code:
                        known_dependencies = list(dependency_code.keys())
                    
                    # AI检测器检查是否有额外实现
                    detection_result = self.ai_detector.detect_extra_implementation(
                        rust_code, kind, known_dependencies
                    )
                    
                    attempt_record["ai_detection"] = detection_result
                    
                    if detection_result["is_clean"]:
                        # AI检测通过，继续进行编译验证（如果启用）
                        main_logger.info(f"✅ [{kind}]: {item_id} AI检测通过")
                        
                        # 如果启用了编译检查，进行编译验证
                        if self.enable_compile_check:
                            main_logger.info(f"🔧 第 {round_num} 轮: 开始编译验证...")
                            
                            # 收集依赖项代码（用于编译验证）
                            compile_dependencies = {}
                            if dependency_code:
                                compile_dependencies = dependency_code
                            
                            # 编译验证
                            compile_result = self._compile_rust_code(rust_code, kind, compile_dependencies, data)
                            attempt_record["compile_result"] = compile_result
                            
                            if compile_result["success"]:
                                # 编译成功，转换完成
                                main_logger.info(f"✅ [{kind}]: {item_id} 编译验证通过，转换成功，用了 {round_num} 轮")
                            else:
                                # 编译失败，尝试修复
                                compile_errors = compile_result["errors"]
                                main_logger.warning(f"🔧 [{kind}]: {item_id} 编译失败，有 {len(compile_errors)} 个错误，开始修复...")
                                
                                # 启动修复流程
                                fix_result = self._fix_compile_errors(rust_code, compile_errors, item_id, kind, compile_dependencies, data)
                                attempt_record["fix_result"] = fix_result
                                
                                if fix_result["success"]:
                                    # 修复成功，使用修复后的代码
                                    rust_code = fix_result["rust_code"]
                                    main_logger.info(f"✅ [{kind}]: {item_id} 编译错误修复成功，转换成功，用了 {round_num} 轮 + {fix_result['fix_rounds']} 轮修复")
                                    
                                    # 更新转换记录
                                    attempt_record["rust_code"] = rust_code
                                    attempt_record["json_response"]["rust_code"] = rust_code
                                else:
                                    # 修复失败
                                    if round_num >= max_rounds:
                                        main_logger.error(f"❌ [{kind}]: {item_id} 编译错误修复失败且达到最大轮数")
                                        self.stats.record_failure(item_id, kind, "编译错误修复失败", {
                                            "c_code": c_code,
                                            "rust_code": rust_code,
                                            "compile_errors": compile_errors,
                                            "fix_result": fix_result
                                        })
                                        return {
                                            "success": False,
                                            "error": f"编译错误修复失败: {fix_result.get('error', '未知错误')}",
                                            "conversion_history": conversion_history,
                                            "compile_result": compile_result,
                                            "fix_result": fix_result
                                        }
                                    else:
                                        # 继续下一轮，将编译错误作为反馈
                                        feedback_prompt = f"""你的Rust代码编译失败，需要修复：

编译错误：
{chr(10).join(f"- {error.split(chr(10))[0]}" for error in compile_errors[:3])}

修复建议：
- 检查类型定义的正确性
- 确保所有依赖项已正确引用
- 避免重复定义
- 简化复杂的实现

请修正这些问题并生成新的JSON格式结果：
```json
{{
  "rust_code": "修正后的Rust代码",
  "confidence": "HIGH/MEDIUM/LOW", 
  "warnings": ["警告信息列表"],
  "unsafe_used": true/false,
  "unsafe_reason": "如果使用了unsafe，请说明原因"
}}
```

只返回JSON对象，不要添加其他文本。
"""
                                        messages.append({"role": "assistant", "content": rust_response_raw})
                                        messages.append({"role": "user", "content": feedback_prompt})
                                        ai_dialog_logger.info(f"编译失败反馈轮 {round_num}: {feedback_prompt}")
                                        continue  # 继续下一轮
                        else:
                            # 未启用编译检查，AI检测通过即表示成功
                            main_logger.info(f"✅ [{kind}]: {item_id} AI检测通过，转换成功，用了 {round_num} 轮")
                        
                        # 记录到跨文件验证器（仅记录，不验证）
                        if self.cross_file_validator:
                            unique_key = self.cross_file_validator._generate_unique_key(kind, item_id, rust_code)
                            if unique_key not in self.cross_file_validator.global_converted_items:
                                from sig_utils.cross_file_validator import CodeItem
                                code_item = CodeItem(
                                    file_name=file_name or "unknown_file",
                                    kind=kind,
                                    item_name=item_id,
                                    actual_name=self.cross_file_validator._extract_actual_name(rust_code, kind),
                                    rust_code=rust_code.strip(),
                                    original_type=kind
                                )
                                self.cross_file_validator.global_converted_items[unique_key] = code_item
                                self.cross_file_validator._update_global_state(code_item)
                        
                    self.stats.record_success(item_id, kind, round_num, {
                        "c_code": c_code,
                            "rust_code": rust_code,
                            "json_response": rust_response_json,
                            "ai_detection": detection_result,
                            "compile_result": attempt_record.get("compile_result"),
                            "fix_result": attempt_record.get("fix_result")
                    })
                    result = {
                        "success": True,
                        "rust_code": rust_code,
                        "rounds": round_num,
                            "conversion_history": conversion_history,
                            "json_response": rust_response_json,
                            "ai_detection": detection_result,
                            "compile_result": attempt_record.get("compile_result"),
                            "fix_result": attempt_record.get("fix_result")
                    }
                    item_logger.info(f"转换成功，用了{round_num}轮")
                    item_logger.info(f"最终Rust代码:\n{rust_code}")
                    ai_dialog_logger.info(f"转换成功，最终代码: {rust_code}")
                    return result
                else:
                        # AI检测发现问题
                        violations = detection_result["violations"]
                        # 处理violations可能是字典列表的情况
                        if violations and isinstance(violations[0], dict):
                            violation_summary = "; ".join([
                                v.get("details", str(v)) if isinstance(v, dict) else str(v) 
                                for v in violations
                            ])
                        else:
                            violation_summary = "; ".join(violations) if violations else "未知违规"
                        
                        main_logger.warning(f"🤖 [{kind}]: {item_id} AI检测发现问题: {violation_summary}")
                        item_logger.warning(f"AI检测结果: {detection_result}")
                        
                        # 如果是最后一轮则失败，否则继续
                        if round_num >= max_rounds:
                            main_logger.error(f"❌ [{kind}]: {item_id} AI检测失败且达到最大轮数")
                            self.stats.record_failure(item_id, kind, "AI检测发现额外实现", {
                                "c_code": c_code,
                                "rust_code": rust_code,
                                "ai_detection": detection_result
                            })
                            return {
                                "success": False,
                                "error": f"AI检测发现问题: {violation_summary}",
                                "conversion_history": conversion_history,
                                "ai_detection": detection_result
                            }
                        else:
                            # 继续下一轮，将AI检测结果作为反馈
                            feedback_prompt = f"""你的Rust代码AI检测发现了问题：

检测结果：
- 有具体实现: {detection_result['has_implementation']}
- 有重定义: {detection_result['has_redefinition']}
- 严重程度: {detection_result['severity']}

违规项：
{chr(10).join(f"- {v}" for v in detection_result['violations'])}

修复建议：{detection_result['recommendation']}

请修正这些问题并生成新的JSON格式结果：
```json
{{
  "rust_code": "修正后的Rust代码",
  "confidence": "HIGH/MEDIUM/LOW",
  "warnings": ["警告信息列表"],
  "unsafe_used": true/false,
  "unsafe_reason": "如果使用了unsafe，请说明原因"
}}
```

只返回JSON对象，不要添加其他文本。
"""
                            messages.append({"role": "assistant", "content": rust_response_raw})
                            messages.append({"role": "user", "content": feedback_prompt})
                            ai_dialog_logger.info(f"AI检测失败反馈轮 {round_num}: {feedback_prompt}")
                            continue  # 继续下一轮
                
                # 如果多次失败，考虑使用Agent3仲裁
                if round_num >= 3 and arbitration_count < max_arbitration:
                    item_logger.info(f"进行第 {arbitration_count + 1} 次仲裁")
                    arbitration_count += 1
                    
                    # 准备仲裁提示
                    arbitration_prompt = PromptTemplates.AGENT3_PROMPT
                    arbitration_prompt = arbitration_prompt.replace("{c_code}", c_code)
                    arbitration_prompt = arbitration_prompt.replace("{rust_code}", rust_code)
                    arbitration_prompt = arbitration_prompt.replace("{conversion_history}", history_text)
                    arbitration_prompt = arbitration_prompt.replace("{attempts}", str(round_num))
                    arbitration_prompt = arbitration_prompt.replace("{latest_feedback}", review_json["reason"])
                    
                    arbitration_messages = [
                        {"role": "system", "content": PromptTemplates.AGENT3_SYSTEM},
                        {"role": "user", "content": arbitration_prompt}
                    ]
                    
                    # 记录仲裁对话
                    ai_dialog_logger.info(f"仲裁轮 {arbitration_count} - 系统提示: {PromptTemplates.AGENT3_SYSTEM}")
                    ai_dialog_logger.info(f"仲裁轮 {arbitration_count} - 用户提示: {arbitration_prompt}")
                    
                    # 获取仲裁结果
                    arbitration_response = self.agent3.ask(arbitration_messages)
                    ai_dialog_logger.info(f"仲裁轮 {arbitration_count} - Agent3回复: {arbitration_response}")
                    arbitration_code = TextExtractor.extract_code_block(arbitration_response)
                    
                    # 移除仲裁代码的强制清理，让AI检测器来判断
                    # ===== 原来的仲裁代码清理已移除 =====
                    
                    # 保存仲裁结果
                    arbitration_record = {
                        "round": f"{round_num}-仲裁",
                        "rust_code": arbitration_code,
                        "arbitration": True
                    }
                    conversion_history.append(arbitration_record)
                    
                    # 继续用仲裁结果去审核
                    rust_code = arbitration_code
                    
                    # 跳过后续步骤，直接进入下一轮
                    continue
                
                # 将审核结果添加到对话中，继续下一轮
                # 构建反馈提示
                feedback_prompt = f"""你的Rust代码未通过审核，原因是:

{review_json['reason']}

请修正这些问题并生成新的JSON格式结果：
```json
{{
  "rust_code": "修正后的Rust代码",
  "confidence": "HIGH/MEDIUM/LOW",
  "warnings": ["警告信息列表"],
  "unsafe_used": true/false,
  "unsafe_reason": "如果使用了unsafe，请说明原因"
}}
```

只返回JSON对象，不要添加其他文本。
"""
                
                messages.append({"role": "assistant", "content": rust_response_raw})
                messages.append({"role": "user", "content": feedback_prompt})
                
                # 记录反馈对话
                ai_dialog_logger.info(f"反馈轮 {round_num} - 用户反馈: {feedback_prompt}")
            
            except Exception as e:
                error_msg = f"转换过程发生错误: {str(e)}"
                main_logger.error(error_msg)
                main_logger.error(traceback.format_exc())
                ai_dialog_logger.error(f"转换轮 {round_num} 发生异常: {error_msg}")
                
                self.stats.record_failure(item_id, kind, "转换过程异常", {
                    "c_code": c_code,
                    "error": str(e)
                })
                
                result = {
                    "success": False,
                    "error": error_msg,
                    "conversion_history": conversion_history
                }
                item_logger.warning(f"转换失败，原因: {error_msg}")
                if 'last_rust_code' in result and result['last_rust_code']:
                    item_logger.info(f"最后尝试的Rust代码:\n{result['last_rust_code']}")
                ai_dialog_logger.info(f"==================== AI对话结束 [{kind}]: {item_id} (失败) ====================")
                return result
        
        # 达到最大轮数仍未成功
        main_logger.warning(f"❌ [{kind}]: {item_id} 达到最大轮数 {max_rounds}，转换失败")
        self.stats.record_failure(item_id, kind, "达到最大轮数", {
            "c_code": c_code,
            "last_attempt": rust_code if 'rust_code' in locals() else None,
            "last_review": review_json["reason"] if 'review_json' in locals() else None
        })
        
        result = {
            "success": False,
            "error": "达到最大轮数",
            "last_rust_code": rust_code if 'rust_code' in locals() else None,
            "conversion_history": conversion_history
        }
        item_logger.warning(f"转换失败，原因: 达到最大轮数")
        if 'last_rust_code' in result and result['last_rust_code']:
            item_logger.info(f"最后尝试的Rust代码:\n{result['last_rust_code']}")
        ai_dialog_logger.info(f"==================== AI对话结束 [{kind}]: {item_id} (达到最大轮数) ====================")
        return result
    
    def process_architecture_file(self, filepath, output_path=None, max_items=None):
        """处理整个架构文件"""
        main_logger.info("="*80)
        main_logger.info(f"开始处理架构文件: {filepath}")
        main_logger.info("="*80)
        
        # 读取输入文件
        with open(filepath, "r", encoding="utf-8") as f:
            input_data = json.load(f)
        
        # 默认输出路径
        if not output_path:
            output_path = filepath  # 直接写回原始文件
        
        # 检查输出文件是否已存在，如果存在则读取之前的处理状态
        data = copy.deepcopy(input_data)  # 使用深拷贝而非浅拷贝
        if output_path != filepath and os.path.exists(output_path):
            try:
                main_logger.info(f"检测到现有输出文件: {output_path}，读取已处理状态")
                with open(output_path, "r", encoding="utf-8") as f:
                    output_data = json.load(f)
                
                # 合并数据，优先使用输出文件中的处理状态
                for file_name, content in output_data.items():
                    if file_name not in data:
                        data[file_name] = content
                        continue
                        
                    for kind in ["fields", "defines", "typedefs", "structs", "functions"]:
                        if kind not in content:
                            continue
                            
                        if kind not in data[file_name]:
                            data[file_name][kind] = content[kind]
                            continue
                            
                        for item_name, item in content[kind].items():
                            # 如果项目已成功转换，使用输出文件中的状态
                            if item.get("conversion_status") == "success":
                                data[file_name][kind][item_name] = item
            except Exception as e:
                main_logger.error(f"读取输出文件时出错: {e}")
        
        # 重新分类函数类型的define和typedef到functions类别
        main_logger.info("正在重新分类函数类型的define和typedef项目...")
        reclassified_count = 0
        
        for file_name, content in data.items():
            if "functions" not in content:
                content["functions"] = {}
            
            # 检查defines中的函数宏
            if "defines" in content:
                to_move = []
                for item_name, item_data in content["defines"].items():
                    if self._should_treat_as_function(item_name, item_data):
                        to_move.append((item_name, item_data))
                
                for item_name, item_data in to_move:
                    # 移动到functions类别
                    content["functions"][item_name] = item_data.copy()
                    content["functions"][item_name]["original_type"] = "define"
                    # 从defines中删除
                    del content["defines"][item_name]
                    reclassified_count += 1
                    main_logger.info(f"将define函数宏 {item_name} 重新分类到functions")
            
            # typedef中的函数指针保持不变（它们是类型定义，不是函数实现）
        
        if reclassified_count > 0:
            main_logger.info(f"共重新分类了 {reclassified_count} 个函数类型项目")
        
        # 初始化已处理项跟踪
        processed_items = set()
        
        # 首先标记所有已成功转换的项目为已处理
        for file_name, content in data.items():
            for kind in ["fields", "defines", "typedefs", "structs", "functions"]:
                if kind not in content:
                    continue
                
                for item_name, item in content[kind].items():
                    if item.get("conversion_status") == "success":
                        full_id = f"{file_name}::{kind}::{item_name}"
                        processed_items.add(full_id)
        
        # 计算总项目数和未处理项目数
        total_items = 0
        remaining_items = 0
        for file_name, content in data.items():
            for kind in ["fields", "defines", "typedefs", "structs", "functions"]:
                if kind in content:
                    kind_items = len(content[kind])
                    total_items += kind_items
                    # 计算该类型中未处理的项目数量
                    for item_name in content[kind]:
                        full_id = f"{file_name}::{kind}::{item_name}"
                        if full_id not in processed_items:
                            remaining_items += 1
        
        main_logger.info(f"总项目数: {total_items}, 已处理: {len(processed_items)}, 剩余: {remaining_items}")
        
        # 转换基础结构
        processing_items = set()  # 当前正在处理的项目
        max_to_process = remaining_items  # 使用未处理项目数而不是总项目数
        item_count = 0
        success_count = 0
        skipped_count = 0
        failed_count = 0
        
        # 先处理基础结构
        for file_name, content in data.items():
            # 处理结构体、类型定义等基础结构
            for kind in ["fields", "defines", "typedefs", "structs"]:
                if kind not in content:
                    continue
                    
                for item_name, item in content[kind].items():
                    # 生成完整ID
                    full_id = f"{file_name}::{kind}::{item_name}"
                    
                    # 如果已经处理过，跳过
                    if full_id in processed_items:
                        continue
                    
                    # 检查依赖项
                    deps = item.get("dependencies", {})
                    all_deps_processed = True
                    missing_deps = []
                    
                    # 如果没有依赖，或者所有依赖都已处理或正在处理（避免循环依赖）
                    if not deps or all(
                        self._is_dependency_processed(dep_id, dep_info, data, processed_items, processing_items)
                        for dep_id, dep_info in deps.items()
                    ):
                        # 显示进度信息
                        current_progress = item_count + 1
                        progress_percent = (current_progress / max_to_process) * 100 if max_to_process > 0 else 0
                        main_logger.info(f"处理项目 [{current_progress}/{max_to_process}] ({progress_percent:.1f}%) - [{kind}]: {item_name}")
                        
                        # 获取完整文本
                        full_text = item.get("full_text")
                        if not full_text:
                            main_logger.warning(f"[{kind}]: {item_name} 缺少full_text字段，跳过")
                            processed_items.add(full_id)
                            continue
                        
                        # 收集依赖项的已转换代码
                        dependency_code = {}
                        for dep_id, dep_info in deps.items():
                            if not self._is_dependency_processed(dep_id, dep_info, data, processed_items, processing_items):
                                all_deps_processed = False
                                missing_deps.append((dep_id, dep_info))
                                break
                                
                            # 收集依赖项代码
                            dep_code = self._collect_dependency_code(dep_id, dep_info, data)
                            dependency_code.update(dep_code)
                        
                        # 转换代码
                        processing_items.add(full_id)  # 标记为正在处理
                        try:
                            result = self.convert_with_dependencies(
                                item_name, kind, full_text, dependency_code, 
                                data=data, file_name=file_name  # 传入文件名
                            )
                            
                            # 更新结果
                            if result["success"]:
                                item["rust_signature"] = result["rust_code"]
                                item["conversion_status"] = "success"
                                
                                # 检查是否为头文件保护宏，这种情况不计入常规转换轮数
                                if result.get("is_header_guard", False):
                                    item["is_header_guard"] = True
                                    main_logger.info(f"[{kind}]: {item_name} 是头文件保护宏，已跳过")
                                    # 不重复输出项目信息，减少日志量
                                    # item_logger.info(f"跳过头文件保护宏")
                                    skipped_count += 1
                                else:
                                    item["conversion_rounds"] = result["rounds"]
                                    main_logger.info(f"成功转换 [{kind}]: {item_name} (用了{result['rounds']}轮)")
                                    success_count += 1
                                    
                                    # 新增：添加到跨文件验证器并进行实时验证
                                    if self.cross_file_validator:
                                        # 先添加到验证器
                                        added = self.cross_file_validator.add_converted_item(
                                            file_name=file_name or "unknown_file",  # 使用传入的文件名
                                            kind=kind,
                                            item_name=item_name,
                                            rust_code=result["rust_code"],
                                            original_type=item.get("original_type", None)
                                        )
                                        
                                        if added:
                                            # 只在启用编译验证时才进行实时验证
                                            if self.enable_compile_check:
                                                # 进行实时编译验证
                                                validation_result = self.cross_file_validator.validate_rust_code(
                                                    result["rust_code"], kind, f"{file_name}::{item_name}"
                                                )
                                                if validation_result["success"]:
                                                    main_logger.info(f"✅ 跨文件验证成功 [{kind}]: {item_name}")
                                                else:
                                                    main_logger.warning(f"⚠️ 跨文件验证失败 [{kind}]: {item_name}")
                                                    for error in validation_result["errors"][:2]:  # 只显示前2个错误
                                                        main_logger.warning(f"   错误: {error.split(chr(10))[0]}...")
                                            else:
                                                main_logger.debug(f"📝 已记录到验证器（跳过验证）: [{kind}]: {item_name}")
                                        else:
                                            main_logger.debug(f"跨文件验证器：跳过重复项目 [{kind}]: {item_name}")
                            else:
                                item["conversion_status"] = "failed"
                                item["failure_reason"] = result.get("reason", "转换失败，无具体原因")
                                main_logger.warning(f"转换失败 [{kind}]: {item_name}, 原因: {item['failure_reason']}")
                                failed_count += 1
                        except Exception as e:
                            main_logger.error(f"处理 [{kind}]: {item_name} 时发生错误: {e}")
                            item["conversion_status"] = "error"
                            item["failure_reason"] = str(e)
                            failed_count += 1
                        finally:
                            processed_items.add(full_id)  # 无论成功失败，都标记为已处理
                            processing_items.remove(full_id)  # 从正在处理中移除
                        
                        # 定期保存结果
                        item_count += 1
                        if item_count % 10 == 0:
                            with open(output_path, "w", encoding="utf-8") as f:
                                json.dump(data, f, indent=4, ensure_ascii=False)
                                
                        # 如果设置了最大处理数量，检查是否已达到
                        if max_items and item_count >= max_items:
                            main_logger.info(f"已达到最大处理数量 {max_items}，停止处理")
                            break
                            
                    else:
                        # 依赖项未处理完成，记录未处理的依赖
                        for dep_id, dep_info in deps.items():
                            if not self._is_dependency_processed(dep_id, dep_info, data, processed_items, processing_items):
                                missing_deps.append((dep_id, dep_info))
                                
                # 如果达到最大处理数量，跳出循环
                if max_items and item_count >= max_items:
                    break
                    
            # 如果达到最大处理数量，跳出循环
            if max_items and item_count >= max_items:
                break
                
        # 如果基础结构都处理了但还有剩余项，开始处理函数
        if (not max_items or item_count < max_items) and item_count < total_items:
            # 处理函数
            for file_name, content in data.items():
                if "functions" not in content:
                    continue
                    
                for item_name, item in content["functions"].items():
                    # 生成完整ID
                    full_id = f"{file_name}::functions::{item_name}"
                    
                    # 如果已经处理过，跳过
                    if full_id in processed_items:
                        continue
                    
                    # 检查依赖项
                    deps = item.get("dependencies", {})
                    all_deps_processed = True
                    missing_deps = []
                    
                    # 如果没有依赖，或者所有依赖都已处理或正在处理（避免循环依赖）
                    if not deps or all(
                        self._is_dependency_processed(dep_id, dep_info, data, processed_items, processing_items)
                        for dep_id, dep_info in deps.items()
                    ):
                        # 显示进度信息
                        current_progress = item_count + 1
                        progress_percent = (current_progress / max_to_process) * 100 if max_to_process > 0 else 0
                        main_logger.info(f"处理函数 [{current_progress}/{max_to_process}] ({progress_percent:.1f}%) - [functions]: {item_name}")
                        
                        # 获取完整文本
                        full_text = item.get("full_text")
                        if not full_text:
                            main_logger.warning(f"[functions]: {item_name} 缺少full_text字段，跳过")
                            processed_items.add(full_id)
                            continue
                        
                        # 收集依赖项的已转换代码
                        dependency_code = {}
                        for dep_id, dep_info in deps.items():
                            if not self._is_dependency_processed(dep_id, dep_info, data, processed_items, processing_items):
                                all_deps_processed = False
                                missing_deps.append((dep_id, dep_info))
                                break
                                
                            # 收集依赖项代码
                            dep_code = self._collect_dependency_code(dep_id, dep_info, data)
                            dependency_code.update(dep_code)
                        
                        # 转换代码
                        processing_items.add(full_id)  # 标记为正在处理
                        try:
                            result = self.convert_with_dependencies(
                                item_name, "functions", full_text, dependency_code, 
                                data=data, file_name=file_name  # 传入文件名
                            )
                            
                            # 更新结果
                            if result["success"]:
                                item["rust_signature"] = result["rust_code"]
                                item["conversion_status"] = "success"
                                item["conversion_rounds"] = result["rounds"]
                                main_logger.info(f"成功转换函数: {item_name} (用了{result['rounds']}轮)")
                                success_count += 1
                                
                                # 新增：添加到跨文件验证器并进行实时验证
                                if self.cross_file_validator:
                                    # 先添加到验证器
                                    added = self.cross_file_validator.add_converted_item(
                                        file_name=file_name or "unknown_file",  # 使用传入的文件名
                                        kind="functions",
                                        item_name=item_name,
                                        rust_code=result["rust_code"],
                                        original_type=item.get("original_type", None)
                                    )
                                    
                                    if added:
                                        # 只在启用编译验证时才进行实时验证
                                        if self.enable_compile_check:
                                            # 进行实时编译验证
                                            validation_result = self.cross_file_validator.validate_rust_code(
                                                result["rust_code"], "functions", f"{file_name}::{item_name}"
                                            )
                                            if validation_result["success"]:
                                                main_logger.info(f"✅ 跨文件验证成功 [functions]: {item_name}")
                                            else:
                                                main_logger.warning(f"⚠️ 跨文件验证失败 [functions]: {item_name}")
                                                for error in validation_result["errors"][:2]:  # 只显示前2个错误
                                                    main_logger.warning(f"   错误: {error.split(chr(10))[0]}...")
                                        else:
                                            main_logger.debug(f"📝 已记录到验证器（跳过验证）: [functions]: {item_name}")
                                    else:
                                        main_logger.debug(f"跨文件验证器：跳过重复函数 {item_name}")
                            else:
                                item["conversion_status"] = "failed"
                                item["failure_reason"] = result.get("reason", "转换失败，无具体原因")
                                main_logger.warning(f"转换失败 [functions]: {item_name}, 原因: {item['failure_reason']}")
                                failed_count += 1
                        except Exception as e:
                            main_logger.error(f"处理 [functions]: {item_name} 时发生错误: {e}")
                            item["conversion_status"] = "error"
                            item["failure_reason"] = str(e)
                            failed_count += 1
                        finally:
                            processed_items.add(full_id)  # 无论成功失败，都标记为已处理
                            processing_items.remove(full_id)  # 从正在处理中移除
                        
                        # 定期保存结果
                        item_count += 1
                        if item_count % 10 == 0:
                            with open(output_path, "w", encoding="utf-8") as f:
                                json.dump(data, f, indent=4, ensure_ascii=False)
                                
                        # 如果设置了最大处理数量，检查是否已达到
                        if max_items and item_count >= max_items:
                            main_logger.info(f"已达到最大处理数量 {max_items}，停止处理")
                            break
                            
                    else:
                        # 依赖项未处理完成，记录未处理的依赖
                        for dep_id, dep_info in deps.items():
                            if not self._is_dependency_processed(dep_id, dep_info, data, processed_items, processing_items):
                                missing_deps.append((dep_id, dep_info))
                                
                # 如果达到最大处理数量，跳出循环
                if max_items and item_count >= max_items:
                    break
        
        # 保存结果
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
            
        # 输出结果统计
        main_logger.info("="*80)
        main_logger.info(f"处理完成: 成功={success_count}, 跳过={skipped_count}, 失败={failed_count}")
        main_logger.info(f"总项目数: {total_items}, 已处理: {len(processed_items)}")
        
        # 检查是否有未处理的项目
        if len(processed_items) < total_items:
            main_logger.warning(f"有 {total_items - len(processed_items)} 个项目未处理，可能是由于循环依赖或缺失依赖")
            main_logger.info("未处理项目及其依赖:")
            
            # 展示未处理项目及其依赖
            for file_name, content in data.items():
                for kind in ["fields", "defines", "typedefs", "structs", "functions"]:
                    if kind not in content:
                        continue
                        
                    for item_name, item in content[kind].items():
                        full_id = f"{file_name}::{kind}::{item_name}"
                        if full_id not in processed_items:
                            deps = item.get("dependencies", {})
                            if not deps:
                                continue  # 跳过没有依赖的项目

                            main_logger.info(f"  {full_id}:")
                            main_logger.info(f"    依赖项: {list(deps.keys())}")
                            missing_deps = []
                            for dep_id, dep_info in deps.items():
                                if not self._is_dependency_processed(dep_id, dep_info, data, processed_items, set()):
                                    missing_deps.append(dep_id)
                            main_logger.info(f"    未处理依赖: {missing_deps}")
                            
        main_logger.info("="*80)
        
        return data

    def _is_dependency_processed(self, dep_id, dep_info, data, processed_items, processing_items=None):
        """检查依赖项是否已处理"""
        # 首先检查dep_id是否直接在processed_items中
        if dep_id in processed_items:
            return True
        
        # 检查是否正在处理中（用于处理循环依赖）
        if processing_items and dep_id in processing_items:
            return True
            
        # 如果依赖信息不完整，无法进一步检查
        if not dep_info:
            return False
            
        # 获取依赖项的类型和名称
        dep_type = dep_info.get("type")
        dep_qualified_name = dep_info.get("qualified_name")
        
        if not dep_type or not dep_qualified_name:
            return False
            
        # 对于函数依赖，直接返回True，不再检查其是否已处理
        if dep_type == "functions":
            return True
        
        # 解析qualified_name获取文件名和项目名
        dep_parts = dep_qualified_name.split("::")
        if len(dep_parts) < 2:
            return False
        
        dep_file = dep_parts[0]  # 第一部分是文件名
        dep_name = "::".join(dep_parts[1:])  # 剩余部分是项目名
        
        # 首先尝试使用依赖信息中指定的类型
        full_dep_id = f"{dep_file}::{dep_type}::{dep_name}"
        if full_dep_id in processed_items:
            return True
        
        # 如果指定类型找不到，尝试在数据中搜索实际位置
        if dep_file in data:
            # 首先检查指定类型
            if dep_type in data[dep_file]:
                # 尝试直接匹配dep_name
                if dep_name in data[dep_file][dep_type]:
                    item = data[dep_file][dep_type][dep_name]
                    if item.get("conversion_status") == "success":
                            return True
                    
                    # 如果直接匹配失败，尝试通过name字段匹配
                    for item_key, item_data in data[dep_file][dep_type].items():
                        if item_data.get("conversion_status") == "success":
                            # 检查name字段是否匹配
                            if item_data.get("name") == dep_name:
                                main_logger.debug(f"通过name字段匹配到依赖: {dep_name} -> {item_key}")
                                return True
                            
                            # 检查从rust_signature中提取的类型名是否匹配
                            rust_signature = item_data.get("rust_signature", "")
                            if rust_signature:
                                extracted_name = self._extract_type_name_from_rust_code(rust_signature, dep_type)
                                if extracted_name == dep_name:
                                    main_logger.debug(f"通过提取类型名匹配到依赖: {dep_name} -> {item_key}")
                                    return True
            
            # 如果指定类型中找不到，搜索其他类型（解决类型分类错误问题）
            for actual_type in ["fields", "defines", "typedefs", "structs", "functions"]:
                if actual_type == dep_type:
                    continue  # 跳过已检查的类型
                    
                if actual_type in data[dep_file]:
                    # 尝试直接匹配
                    if dep_name in data[dep_file][actual_type]:
                        item = data[dep_file][actual_type][dep_name]
                        if item.get("conversion_status") == "success":
                            actual_full_id = f"{dep_file}::{actual_type}::{dep_name}"
                            if actual_full_id in processed_items:
                                main_logger.debug(f"依赖项类型不匹配: {dep_qualified_name} 期望={dep_type}, 实际={actual_type}")
                                return True
                    
                    # 尝试通过name字段匹配
                    for item_key, item_data in data[dep_file][actual_type].items():
                        if item_data.get("conversion_status") == "success":
                            if item_data.get("name") == dep_name:
                                main_logger.debug(f"跨类型通过name字段匹配到依赖: {dep_name} -> {actual_type}::{item_key}")
                    return True
        
        return False

    def _collect_dependency_code(self, dep_id, dep_info, data):
        """收集依赖项的代码"""
        dependency_code = {}
        
        if not dep_info:
            return dependency_code
            
        dep_type = dep_info.get("type")
        dep_qualified_name = dep_info.get("qualified_name")
        
        if not dep_type or not dep_qualified_name:
            return dependency_code
            
        # 解析依赖名称
        dep_parts = dep_qualified_name.split("::")
        if len(dep_parts) < 2:
            return dependency_code
            
        dep_file = dep_parts[0]
        dep_name = "::".join(dep_parts[1:])
        
        # 查找依赖项
        if dep_file in data and dep_type in data[dep_file]:
            # 尝试直接匹配dep_name
            dep_item = data[dep_file][dep_type].get(dep_name)
            if dep_item and dep_item.get("conversion_status") == "success":
                # 添加已转换的代码
                rust_code = dep_item.get("rust_signature", "")
                if rust_code:
                    # 对于函数，确保有默认实现（用于编译验证）
                    if dep_type == "functions":
                        # 如果是函数，生成默认实现用于编译验证
                        if "fn " in rust_code:
                            rust_code = self._generate_default_implementation(rust_code)
                    
                    dependency_code[dep_id] = rust_code
            return dependency_code
        # 如果直接匹配失败，尝试通过name字段匹配
        for item_key, item_data in data[dep_file][dep_type].items():
                if item_data.get("conversion_status") == "success":
                    # 检查name字段是否匹配
                    if item_data.get("name") == dep_name:
                        rust_code = item_data.get("rust_signature", "")
                        if rust_code:
                            if dep_type == "functions" and "fn " in rust_code:
                                rust_code = self._generate_default_implementation(rust_code)
                            dependency_code[dep_id] = rust_code
                            main_logger.debug(f"通过name字段收集到依赖代码: {dep_name}")
                            return dependency_code
                    
                    # 检查从rust_signature中提取的类型名是否匹配
                    rust_signature = item_data.get("rust_signature", "")
                    if rust_signature:
                        extracted_name = self._extract_type_name_from_rust_code(rust_signature, dep_type)
                        if extracted_name == dep_name:
                            rust_code = rust_signature
                            if dep_type == "functions" and "fn " in rust_code:
                                rust_code = self._generate_default_implementation(rust_code)
                            dependency_code[dep_id] = rust_code
                            main_logger.debug(f"通过提取类型名收集到依赖代码: {dep_name}")
                            return dependency_code
        
        return dependency_code

    def _generate_default_implementation(self, rust_signature):
        """为Rust函数签名生成默认实现，用于验证编译正确性"""
        if "fn " not in rust_signature:
            return rust_signature
            
        # 提取返回类型
        if " -> " in rust_signature:
            # 有显式返回类型
            return_part = rust_signature.split(" -> ")[1]
            return_type = return_part.split("{")[0].strip() if "{" in return_part else return_part.strip()
            
            # 根据返回类型生成默认值
            default_values = {
                "bool": "false",
                "i8": "0i8", "i16": "0i16", "i32": "0i32", "i64": "0i64", "i128": "0i128",
                "u8": "0u8", "u16": "0u16", "u32": "0u32", "u64": "0u64", "u128": "0u128",
                "f32": "0.0f32", "f64": "0.0f64",
                "usize": "0usize", "isize": "0isize",
                "char": "'\\0'",
                "()": "return",
            }
            
            # 处理指针类型
            if "*" in return_type:
                default_impl = "std::ptr::null_mut()" if "mut" in return_type else "std::ptr::null()"
            # 处理Option类型
            elif "Option<" in return_type:
                default_impl = "None"
            # 处理Result类型
            elif "Result<" in return_type:
                default_impl = "Err(\"未实现\".into())"
            # 处理字符串类型
            elif return_type in ["String", "&str"]:
                default_impl = "String::new()" if return_type == "String" else "\"\""
            # 处理已知基础类型
            elif return_type in default_values:
                default_impl = default_values[return_type]
            else:
                # 未知类型，使用unimplemented!
                default_impl = "unimplemented!()"
                
        else:
            # 无返回类型（返回()）
            default_impl = "return"
            
        # 替换函数体
        if "{" in rust_signature:
            signature_part = rust_signature.split("{")[0]
            return f"{signature_part} {{\n    {default_impl}\n}}"
        else:
            return f"{rust_signature} {{\n    {default_impl}\n}}"
    
    def generate_validation_project(self, data, output_dir="validation_project"):
        """生成用于验证签名的Rust项目"""
        import os
        
        os.makedirs(output_dir, exist_ok=True)
        os.makedirs(f"{output_dir}/src", exist_ok=True)
        
        # 创建Cargo.toml
        with open(f"{output_dir}/Cargo.toml", "w", encoding="utf-8") as f:
            f.write("""[package]
name = "signature_validator"
version = "0.1.0"
edition = "2021"

[dependencies]
""")
        
        # 收集所有转换成功的项目，按依赖关系排序
        all_items = []
        item_dependencies = {}  # 存储每个项目的依赖关系
        
        for file_name, content in data.items():
            # 处理所有类型的项目
            for kind in ["fields", "defines", "typedefs", "structs", "functions"]:
                if kind not in content:
                    continue
                    
                for item_name, item_data in content[kind].items():
                    if item_data.get("conversion_status") == "success":
                        rust_code = item_data.get("rust_signature", "")
                        if rust_code and rust_code.strip():
                            
                            # 过滤掉前向声明（如 struct Node;）
                            if self._is_forward_declaration(rust_code, kind):
                                main_logger.debug(f"跳过前向声明: {rust_code.strip()}")
                                continue
                            
                            item_id = f"{file_name}::{kind}::{item_name}"
                            
                            # 为函数生成默认实现
                            if kind == "functions" or item_data.get("original_type") == "define":
                                if "fn " in rust_code:
                                    impl_code = self._generate_default_implementation(rust_code)
                                else:
                                    impl_code = rust_code  # 可能是宏定义
                            else:
                                impl_code = rust_code  # struct, typedef等直接使用
                            
                            all_items.append({
                                "id": item_id,
                                "name": item_name,
                                "file": file_name,
                                "kind": kind,
                                "original_type": item_data.get("original_type", kind),
                                "code": impl_code,
                                "dependencies": item_data.get("dependencies", {})
                            })
                            
                            # 记录依赖关系
                            item_dependencies[item_id] = item_data.get("dependencies", {})
        
        # 按依赖关系排序（基础类型在前，依赖的在后）
        def sort_by_dependencies(items):
            sorted_items = []
            processed = set()
            
            def can_process(item):
                # 检查是否所有依赖都已处理
                for dep_id in item["dependencies"]:
                    if dep_id not in processed:
                        return False
                return True
            
            remaining_items = items[:]
            while remaining_items:
                made_progress = False
                for i, item in enumerate(remaining_items):
                    if can_process(item):
                        sorted_items.append(item)
                        processed.add(item["id"])
                        remaining_items.pop(i)
                        made_progress = True
                        break
                
                if not made_progress:
                    # 可能有循环依赖，添加剩余项目
                    main_logger.warning(f"检测到可能的循环依赖，剩余 {len(remaining_items)} 个项目")
                    sorted_items.extend(remaining_items)
                    break
            
            return sorted_items
        
        # 对项目进行依赖排序
        sorted_items = sort_by_dependencies(all_items)
        
        # 创建main.rs
        with open(f"{output_dir}/src/main.rs", "w", encoding="utf-8") as f:
            f.write("// 自动生成的转换结果验证代码（按依赖关系排序）\n")
            f.write("#![allow(unused_variables, dead_code, unused_imports, non_camel_case_types, non_snake_case, non_upper_case_globals)]\n\n")
            
            # 添加常用导入
            f.write("use std::os::raw::*;\n")
            f.write("use std::ptr;\n")
            f.write("use std::any::Any;\n\n")
            
            f.write("fn main() {\n")
            f.write(f"    println!(\"验证了 {len(sorted_items)} 个转换项目（按依赖关系排序）\");\n")
            
            # 按类型统计
            type_counts = {}
            for item in sorted_items:
                kind = item["kind"]
                type_counts[kind] = type_counts.get(kind, 0) + 1
            
            for kind, count in type_counts.items():
                f.write(f"    println!(\"  {kind}: {count} 个\");\n")
            
            f.write("}\n\n")
            
            # 按排序后的顺序添加代码
            current_kind = None
            for item in sorted_items:
                if item["kind"] != current_kind:
                    current_kind = item["kind"]
                    f.write(f"// ==================== {current_kind.upper()} ====================\n\n")
                
                f.write(f"// 来自文件: {item['file']}")
                if item["original_type"] != item["kind"]:
                    f.write(f" (原类型: {item['original_type']})")
                
                # 显示依赖关系
                if item["dependencies"]:
                    f.write(f" [依赖: {len(item['dependencies'])} 个]")
                
                f.write("\n")
                f.write(f"{item['code']}\n\n")
        
        main_logger.info(f"生成验证项目到: {output_dir}")
        main_logger.info(f"包含 {len(sorted_items)} 个项目（按依赖关系排序）:")
        for kind, count in type_counts.items():
            main_logger.info(f"  {kind}: {count} 个")
        
        return output_dir

    def _identify_function_like_items(self, data):
        """识别define和typedef中的函数类型项目"""
        function_like_items = {
            "function_macros": [],      # define中的函数宏
            "function_pointers": [],    # typedef中的函数指针
            "actual_functions": []      # 真正的函数
        }
        
        for file_name, content in data.items():
            # 检查defines中的函数宏
            if "defines" in content:
                for item_name, item in content["defines"].items():
                    full_text = item.get("full_text", "")
                    # 简单检测是否为函数宏（包含括号和参数）
                    if "(" in item_name and ")" in full_text:
                        function_like_items["function_macros"].append({
                            "file": file_name,
                            "name": item_name,
                            "type": "function_macro",
                            "item": item
                        })
            
            # 检查typedefs中的函数指针
            if "typedefs" in content:
                for item_name, item in content["typedefs"].items():
                    full_text = item.get("full_text", "")
                    # 检测函数指针类型定义
                    if "(*" in full_text or "( *" in full_text:
                        function_like_items["function_pointers"].append({
                            "file": file_name,
                            "name": item_name,
                            "type": "function_pointer",
                            "item": item
                        })
            
            # 收集真正的函数
            if "functions" in content:
                for item_name, item in content["functions"].items():
                    function_like_items["actual_functions"].append({
                        "file": file_name,
                        "name": item_name,
                        "type": "function",
                        "item": item
                    })
        
        return function_like_items

    def _compile_rust_code(self, rust_code, item_type="unknown", dependencies=None, data=None):
        """编译单个Rust代码片段，返回编译结果，使用所有已转换代码作为上下文"""
        import tempfile
        import subprocess
        import os
        
        # 创建临时目录
        with tempfile.TemporaryDirectory() as temp_dir:
            # 创建Cargo项目结构
            src_dir = os.path.join(temp_dir, "src")
            os.makedirs(src_dir)
            
            # 创建Cargo.toml
            with open(os.path.join(temp_dir, "Cargo.toml"), "w") as f:
                f.write("""[package]
name = "rust_validation"
version = "0.1.0"
edition = "2021"

[dependencies]
""")
            
            # 创建main.rs
            with open(os.path.join(src_dir, "main.rs"), "w") as f:
                f.write("// 自动生成的编译验证代码（使用所有已转换项目）\n")
                f.write("#![allow(unused_variables, dead_code, unused_imports, non_camel_case_types, non_snake_case, non_upper_case_globals)]\n\n")
                
                # 添加常用导入和类型定义
                f.write("use std::os::raw::*;\n")
                f.write("use std::ptr;\n")
                f.write("use std::any::Any;\n")
                f.write("use std::ffi::c_void;\n\n")
                
                f.write("fn main() {}\n\n")
                
                # 清理当前代码，移除可能的导入语句（在所有分支之前定义）
                current_code_clean = self._clean_rust_code_for_validation(rust_code)
                
                # 收集所有已成功转换的代码（如果提供了data）
                all_converted_code = {}  # unique_key -> code_info
                global_constants = set()  # 收集所有全局常量名
                
                if data:
                    f.write("// ==================== 所有已转换项目（去重后） ====================\n\n")
                    
                    # 第一遍：收集所有全局常量名
                    global_constants = set()
                    for file_name, content in data.items():
                        if "defines" in content:
                            for item_name, item_data in content["defines"].items():
                                if item_data.get("conversion_status") == "success":
                                    rust_signature = item_data.get("rust_signature", "")
                                    matches = re.findall(r'(?:pub )?const (\w+):', rust_signature)
                                    global_constants.update(matches)
                    
                    # 第二遍：收集所有已成功转换的项目
                    for file_name, content in data.items():
                        for kind in ["fields", "defines", "typedefs", "structs", "functions"]:
                            if kind not in content:
                                continue
                                
                            for item_name, item_data in content[kind].items():
                                if item_data.get("conversion_status") == "success":
                                    rust_signature = item_data.get("rust_signature", "")
                                    if rust_signature and rust_signature.strip():
                                        
                                        # 为函数生成默认实现用于编译验证
                                        if kind == "functions" or item_data.get("original_type") == "define":
                                            if "fn " in rust_signature:
                                                impl_code = self._generate_default_implementation(rust_signature)
                                            else:
                                                impl_code = rust_signature  # 可能是宏定义
                                        else:
                                            impl_code = rust_signature  # struct, typedef等直接使用
                                        
                                        # 提取实际的类型名进行去重
                                        actual_name = self._extract_type_name_from_rust_code(impl_code, kind)
                                        
                                        if actual_name:
                                            # 使用实际类型名作为去重键
                                            unique_key = f"{kind}::{actual_name}"
                                            
                                            # 去重：如果已有同名定义，跳过后续的重复定义
                                            if unique_key not in all_converted_code:
                                                all_converted_code[unique_key] = {
                                                    "code": impl_code,
                                                    "kind": kind,
                                                    "file": file_name,
                                                    "item_name": item_name,
                                                    "actual_name": actual_name,
                                                    "original_type": item_data.get("original_type", kind)
                                                }
                                            else:
                                                # 记录跳过的重复定义
                                                existing = all_converted_code[unique_key]
                                                f.write(f"// 跳过重复定义: {actual_name} (来自 {file_name}::{kind}::{item_name}, 已有来自 {existing['file']}::{existing['kind']}::{existing['item_name']})\n")
                    
                    # 按类型排序输出：常量 -> 类型别名 -> 结构体 -> 函数
                    type_order = ["fields", "defines", "typedefs", "structs", "functions"]
                    
                    for kind in type_order:
                        kind_items = [(key, info) for key, info in all_converted_code.items() if info["kind"] == kind]
                        
                        if kind_items:
                            f.write(f"// ==================== {kind.upper()} ====================\n\n")
                            
                            for unique_key, item_info in kind_items:
                                f.write(f"// 来源: {item_info['file']}::{item_info['kind']}::{item_info['item_name']}")
                                if item_info["original_type"] != item_info["kind"]:
                                    f.write(f" (原类型: {item_info['original_type']})")
                                f.write(f" -> {item_info['actual_name']}\n")
                                f.write(f"{item_info['code']}\n\n")
                    
                    f.write("// ==================== 当前验证项目 ====================\n\n")
                    
                    # 清理当前代码中的重复常量定义
                    current_code_clean = self._remove_duplicate_constants_from_function(current_code_clean, global_constants)
                    
                    # 检查当前代码是否会重复定义
                    current_type_name = self._extract_type_name_from_rust_code(current_code_clean, item_type)
                    if current_type_name:
                        for unique_key, info in all_converted_code.items():
                            if info["actual_name"] == current_type_name:
                                f.write(f"// 警告：{current_type_name} 已在上面定义，当前代码应该只引用不重新定义\n")
                                break
                
                elif dependencies:
                    # 如果没有data但有dependencies，使用原有逻辑（向后兼容）
                    f.write("// ==================== 依赖项定义 ====================\n\n")
                    
                    # 按类型分组：常量 -> 类型别名 -> 结构体 -> 函数
                    const_deps = []
                    type_deps = []
                    struct_deps = []
                    function_deps = []
                    
                    for dep_id, dep_code in dependencies.items():
                        dep_code_clean = dep_code.strip()
                        if dep_code_clean.startswith("pub const"):
                            const_deps.append((dep_id, dep_code_clean))
                        elif dep_code_clean.startswith("type "):
                            type_deps.append((dep_id, dep_code_clean))
                        elif dep_code_clean.startswith("pub struct") or dep_code_clean.startswith("#["):
                            struct_deps.append((dep_id, dep_code_clean))
                        else:
                            function_deps.append((dep_id, dep_code_clean))
                    
                    # 按依赖顺序写入
                    for deps_group, group_name in [
                        (const_deps, "常量定义"),
                        (type_deps, "类型别名"),
                        (struct_deps, "结构体定义"),
                        (function_deps, "函数定义")
                    ]:
                        if deps_group:
                            f.write(f"// {group_name}\n")
                            for dep_id, dep_code in deps_group:
                                f.write(f"// 依赖项: {dep_id}\n")
                                f.write(f"{dep_code}\n\n")
                    
                    f.write("// ==================== 当前项目定义 ====================\n\n")
                
                f.write(f"// {item_type} validation\n")
                
                f.write(current_code_clean)
            
            # 运行cargo check
            try:
                result = subprocess.run(
                    ["cargo", "check"],
                    cwd=temp_dir,
                    capture_output=True,
                    text=True,
                    timeout=30
                )
                
                return {
                    "success": result.returncode == 0,
                    "stderr": result.stderr,
                    "stdout": result.stdout,
                    "errors": self._extract_compile_errors(result.stderr) if result.returncode != 0 else []
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
    
    def _clean_rust_code_for_validation(self, rust_code):
        """清理Rust代码，移除导入语句等不需要的部分"""
        lines = rust_code.split('\n')
        cleaned_lines = []
        
        for line in lines:
            line_stripped = line.strip()
            # 跳过导入语句
            if (line_stripped.startswith('use ') or 
                line_stripped.startswith('mod ') or
                line_stripped.startswith('extern crate ')):
                continue
            # 跳过空的模块声明
            if line_stripped == 'mod zopfli;' or line_stripped.startswith('mod ') and line_stripped.endswith(';'):
                continue
            cleaned_lines.append(line)
        
        return '\n'.join(cleaned_lines)
    
    def _extract_compile_errors(self, stderr):
        """从编译输出中提取错误信息，过滤掉警告"""
        errors = []
        lines = stderr.split('\n')
        current_error = []
        in_error = False
        
        for line in lines:
            # 检测错误开始
            if 'error[' in line or line.strip().startswith('error:'):
                if current_error:
                    errors.append('\n'.join(current_error))
                current_error = [line]
                in_error = True
            # 检测警告（跳过）
            elif 'warning[' in line or line.strip().startswith('warning:'):
                if current_error and in_error:
                    errors.append('\n'.join(current_error))
                current_error = []
                in_error = False
            # 继续收集错误信息
            elif in_error and (line.startswith('  ') or line.startswith(' -->') or line.strip().startswith('|')):
                current_error.append(line)
            # 空行可能表示错误结束
            elif in_error and line.strip() == '':
                if current_error:
                    errors.append('\n'.join(current_error))
                current_error = []
                in_error = False
        
        # 添加最后一个错误
        if current_error and in_error:
            errors.append('\n'.join(current_error))
        
        return errors  # 返回所有错误，不限制数量
    
    def _should_treat_as_function(self, item_name, item_data):
        """判断define或typedef项目是否应该作为函数处理"""
        full_text = item_data.get("full_text", "")
        
        # 检查define中的函数宏
        if "(" in item_name and ")" in item_name:
            return True
            
        # 检查typedef中的函数指针 - 更准确的检测
        # 函数指针通常有这些模式：
        # typedef return_type FuncName(params)
        # typedef return_type (*FuncName)(params) 
        if ("(" in full_text and ")" in full_text and 
            (full_text.strip().endswith(")") or "(*" in full_text)):
            # 这些是函数指针类型定义，但应该保持为typedef类别
            # 因为它们是类型定义，不是函数实现
            return False
            
        return False

    def _fix_compile_errors(self, rust_code, compile_errors, item_id, kind, dependencies=None, data=None):
        """专门用于修复编译错误的方法"""
        max_fix_rounds = self.max_fix_rounds
        main_logger.info(f"开始修复编译错误 [{kind}]: {item_id}，共 {len(compile_errors)} 个错误")
        
        # 记录AI对话
        ai_dialog_logger.info(f"========== 开始修复编译错误 [{kind}]: {item_id} ==========")
        if dependencies:
            ai_dialog_logger.info(f"包含 {len(dependencies)} 个依赖项")
        
        # 检查是否为函数指针类型且修复轮数过多
        is_function_pointer = (kind == "typedefs" and 
                             ("fn(" in rust_code or "extern" in rust_code))
        
        if is_function_pointer and len(compile_errors) == 2:
            # 对于函数指针类型，如果一直是2个错误，可能是AI添加了不必要的代码
            main_logger.info(f"检测到函数指针类型修复问题，使用简化策略")
            ai_dialog_logger.info(f"使用函数指针简化修复策略")
            
            # 尝试使用最简单的函数指针语法
            simple_fix_system_prompt = """你是一个专门修复Rust函数指针类型定义的专家。

当前代码是一个函数指针类型定义，但编译失败。请遵循以下原则：

1. **只输出一行代码**：`type TypeName = fn(params) -> return_type;`
2. **不要添加任何其他代码**：不要添加结构体、函数、main函数等
3. **使用最简单的语法**：优先使用 `fn(...)` 而不是 `unsafe extern "C" fn(...)`
4. **保持参数和返回类型正确**：size_t -> usize, void* -> *mut std::ffi::c_void, double -> f64
5. **不要生成导入语句**：不要使用use、mod等，直接使用类型名

请只返回修复后的单行类型定义。"""
            
            # 简化的修复消息
            simple_fix_messages = [
                {"role": "system", "content": simple_fix_system_prompt},
                {"role": "user", "content": f"""当前的函数指针类型定义编译失败：

```rust
{rust_code}
```

编译错误：
```
{chr(10).join(compile_errors)}
```

请只输出一行正确的函数指针类型定义，格式：
```json
{{
  "rust_code": "type TypeName = fn(...) -> ...;",
  "confidence": "HIGH",
  "changes_made": ["简化为单行函数指针定义"],
  "unsafe_used": false,
  "unsafe_reason": null
}}
```"""}
            ]
            
            try:
                # 尝试简化修复
                fix_response_raw = self.agent1.ask(simple_fix_messages)
                ai_dialog_logger.info(f"简化修复 - AI回复: {fix_response_raw}")
                
                fix_response_json = TextExtractor.extract_json(fix_response_raw)
                if fix_response_json:
                    simple_rust_code = fix_response_json.get("rust_code", "")
                    if simple_rust_code and simple_rust_code.count('\n') <= 2:  # 确保是简单代码
                        # 重新编译验证
                        compile_result = self._compile_rust_code(simple_rust_code, kind, dependencies, data)
                        if compile_result["success"]:
                            main_logger.info(f"✅ 简化修复成功 [{kind}]: {item_id}")
                            ai_dialog_logger.info(f"简化修复成功，最终代码: {simple_rust_code}")
                            return {
                                "success": True,
                                "rust_code": simple_rust_code,
                                "fix_rounds": 1,
                                "json_response": fix_response_json
                            }
            except Exception as e:
                main_logger.warning(f"简化修复失败: {e}，继续常规修复流程")
        
        # 构建错误修复的系统提示
        fix_system_prompt = """你是一个专门修复Rust编译错误的专家。你的任务是分析编译错误信息，并修正代码中的问题。

请遵循以下原则：
1. **最小化修改**：只修复编译错误，不添加额外功能或代码
2. **保持原始结构**：如果是类型定义，只输出类型定义；如果是结构体，只输出结构体
3. **不要添加不必要的代码**：不要添加示例函数、额外结构体、主函数等
4. **仔细分析错误根因**：理解每个编译错误的具体原因
5. **保持代码简洁**：确保修正后的代码尽可能简单和直接
6. **注意代码可能依赖其他已定义的类型，不要重复定义依赖项
7. **不要生成导入语句**：不要使用use、mod等导入语句，依赖项已在同一文件中定义

特别注意：
- 对于**函数**：只生成函数签名 + 简单占位符实现，格式：`fn name(...) -> ReturnType { unimplemented!() }` 或 `fn name(...) { /* 占位符 */ }`
- 对于函数指针类型定义（如 typedef），只需要一行 `type TypeName = fn(...) -> ...;`
- 对于结构体定义，只需要结构体本身，不要添加方法或函数
- **绝对不要**生成复杂的函数实现、业务逻辑、算法代码等
- **绝对不要**添加 `main()` 函数、`#[no_mangle]` 函数或其他不相关的代码
- **绝对不要**在函数体中定义局部变量、循环、条件判断等复杂逻辑
- 所有依赖的类型都已在同一文件中定义，直接使用类型名即可

请以JSON格式返回修复结果。"""
        
        # 构建所有编译错误的文本
        all_errors_text = "\n\n".join([f"错误 {i+1}:\n{error}" for i, error in enumerate(compile_errors)])
        
        # 构建依赖项信息
        dependencies_info = ""
        if dependencies:
            dependencies_info = "\n## 已定义的依赖项：\n"
            for dep_id, dep_code in dependencies.items():
                dependencies_info += f"### {dep_id}\n```rust\n{dep_code}\n```\n\n"
            dependencies_info += "注意：以上依赖项已经存在，不要重复定义，只需修复当前代码。\n\n"
        
        # 初始化修复对话
        fix_messages = [
            {"role": "system", "content": fix_system_prompt},
            {"role": "user", "content": f"""请修复以下Rust代码的编译错误：

{dependencies_info}## 当前需要修复的代码：
```rust
{rust_code}
```

## 编译错误：
```
{all_errors_text}
```

请修正这些编译错误并返回修复后的代码：
```json
{{
  "rust_code": "修复后的Rust代码",
  "confidence": "HIGH/MEDIUM/LOW",
  "changes_made": ["修改说明列表"],
  "unsafe_used": true/false,
  "unsafe_reason": "如果使用了unsafe，请说明原因"
}}
```

只返回JSON对象，不要添加其他文本。"""}
        ]
        
        # 记录初始对话
        ai_dialog_logger.info(f"修复系统提示: {fix_system_prompt}")
        ai_dialog_logger.info(f"修复用户提示: {fix_messages[1]['content']}")
        
        current_rust_code = rust_code
        
        # 修复循环
        for fix_round in range(1, max_fix_rounds + 1):
            main_logger.info(f"📝 修复第 {fix_round} 轮 [{kind}]: {item_id}")
            item_logger.info(f"开始第 {fix_round} 轮编译错误修复")
            
            try:
                # 获取修复结果
                fix_response_raw = self.agent1.ask(fix_messages)
                ai_dialog_logger.info(f"修复轮 {fix_round} - AI回复: {fix_response_raw}")
                
                # 解析JSON响应
                fix_response_json = TextExtractor.extract_json(fix_response_raw)
                if not fix_response_json:
                    item_logger.warning("修复结果JSON解析失败，尝试提取代码块")
                    fixed_code = TextExtractor.extract_code_block(fix_response_raw)
                    fix_response_json = {
                        "rust_code": fixed_code,
                        "confidence": "LOW",
                        "changes_made": ["JSON格式解析失败"],
                        "unsafe_used": "unsafe" in fixed_code.lower(),
                        "unsafe_reason": "未提供原因"
                    }
                
                current_rust_code = fix_response_json.get("rust_code", current_rust_code)
                
                # 移除修复后代码的强制清理，让AI检测器来判断  
                # ===== 原来的修复代码清理已移除 =====
                
                # 验证提取的代码是否正确
                if "json" in current_rust_code.lower() or "{" in current_rust_code and "}" in current_rust_code and "rust_code" in current_rust_code:
                    main_logger.warning(f"检测到代码提取错误，包含JSON格式文本")
                    ai_dialog_logger.warning(f"代码提取错误，当前内容: {current_rust_code}")
                    
                    # 记录连续提取错误次数
                    if not hasattr(self, '_extract_error_count'):
                        self._extract_error_count = {}
                    
                    error_key = f"{item_id}_{kind}"
                    self._extract_error_count[error_key] = self._extract_error_count.get(error_key, 0) + 1
                    
                    # 如果连续3次提取错误，停止修复
                    if self._extract_error_count[error_key] >= 3:
                        main_logger.error(f"连续 {self._extract_error_count[error_key]} 次代码提取错误，停止修复: {item_id}")
                        ai_dialog_logger.error(f"连续代码提取错误，停止修复")
                        return {
                            "success": False,
                            "rust_code": current_rust_code,
                            "fix_rounds": fix_round,
                            "error": "连续代码提取错误，停止修复"
                        }
                    
                    # 尝试从JSON响应中提取纯代码
                    if fix_response_json and "rust_code" in fix_response_json:
                        pure_code = fix_response_json["rust_code"]
                        if pure_code and not ("json" in pure_code.lower() or "{" in pure_code and "rust_code" in pure_code):
                            current_rust_code = pure_code
                            main_logger.info(f"已修正代码提取：{current_rust_code[:50]}...")
                            # 重置错误计数
                            self._extract_error_count[error_key] = 0
                        else:
                            # 提取修正失败，跳过这一轮修复
                            main_logger.warning(f"修复代码提取修正失败，跳过修复轮: {fix_round}")
                            continue
                else:
                    # 代码提取正常，重置错误计数
                    if hasattr(self, '_extract_error_count'):
                        error_key = f"{item_id}_{kind}"
                        self._extract_error_count[error_key] = 0
                
                main_logger.info(f"🔧 修复轮 {fix_round}: 完成代码修改")
                
                # 记录修改内容
                changes = fix_response_json.get("changes_made", [])
                if changes:
                    item_logger.info(f"修改内容: {', '.join(changes)}")
                
                # 重新编译验证（包含依赖项）
                item_logger.info(f"重新编译验证修复后的代码...")
                compile_result = self._compile_rust_code(current_rust_code, kind, dependencies, data)
                
                if compile_result["success"]:
                    # 修复成功
                    main_logger.info(f"✅ 编译错误修复成功 [{kind}]: {item_id}，用了 {fix_round} 轮")
                    ai_dialog_logger.info(f"修复成功，最终代码: {current_rust_code}")
                    return {
                        "success": True,
                        "rust_code": current_rust_code,
                        "fix_rounds": fix_round,
                        "json_response": fix_response_json
                    }
                else:
                    # 还有编译错误，继续修复
                    new_errors = compile_result["errors"]
                    main_logger.warning(f"🔧 修复轮 {fix_round}: 仍有 {len(new_errors)} 个编译错误")
                    item_logger.warning(f"修复后仍有编译错误: {len(new_errors)} 个")
                    
                    # 如果是最后一轮，返回失败
                    if fix_round >= max_fix_rounds:
                        ai_dialog_logger.info(f"修复失败，达到最大轮数，最后错误: {new_errors}")
                        break
                    
                    # 准备下一轮修复
                    new_errors_text = "\n\n".join([f"错误 {i+1}:\n{error}" for i, error in enumerate(new_errors)])
                    next_fix_prompt = f"""你的上一次修复仍有编译错误，请继续修复：

{dependencies_info}## 当前代码：
```rust
{current_rust_code}
```

## 剩余编译错误：
```
{new_errors_text}
```

**重要提醒**：
- 对于**函数**：只生成函数签名 + 简单占位符实现，如 `fn name(...) -> ReturnType {{ unimplemented!() }}`
- **绝对不要**生成复杂的函数实现、局部变量、循环、条件判断等
- **绝对不要**重复定义已存在的类型或结构体
- 只修复编译错误，保持代码简洁

请继续修正这些编译错误：
```json
{{
  "rust_code": "继续修复后的Rust代码",
  "confidence": "HIGH/MEDIUM/LOW",
  "changes_made": ["本轮修改说明列表"],
  "unsafe_used": true/false,
  "unsafe_reason": "如果使用了unsafe，请说明原因"
}}
```

只返回JSON对象，不要添加其他文本。"""

                    fix_messages.append({"role": "assistant", "content": fix_response_raw})
                    fix_messages.append({"role": "user", "content": next_fix_prompt})
                    
                    ai_dialog_logger.info(f"修复轮 {fix_round} - 继续修复提示: {next_fix_prompt}")
                    
            except Exception as e:
                error_msg = f"修复过程发生错误: {str(e)}"
                main_logger.error(error_msg)
                ai_dialog_logger.error(f"修复轮 {fix_round} 错误: {error_msg}")
                break
        
        # 修复失败
        main_logger.warning(f"❌ 编译错误修复失败 [{kind}]: {item_id}，达到最大修复轮数 {max_fix_rounds}")
        ai_dialog_logger.info(f"========== 修复失败 [{kind}]: {item_id} ==========")
        return {
            "success": False,
            "rust_code": current_rust_code,
            "fix_rounds": max_fix_rounds,
            "error": "达到最大修复轮数"
        }

    def _extract_type_name_from_rust_code(self, rust_code, kind):
        """从Rust代码中提取类型名"""
        # 处理多行代码，提取多个定义
        type_names = set()
        
        match kind:
            case "fields":
                # 在结构体中查找类型名
                matches = re.findall(r'pub struct (\w+)', rust_code)
                type_names.update(matches)
            case "defines":
                # 在宏定义中查找类型名，支持pub可选
                matches = re.findall(r'(?:pub )?const (\w+):', rust_code)
                type_names.update(matches)
            case "typedefs":
                # 在类型别名中查找类型名，支持pub可选
                matches = re.findall(r'(?:pub )?type (\w+) =', rust_code)
                type_names.update(matches)
            case "structs":
                # 在结构体中查找类型名
                matches = re.findall(r'(?:pub )?struct (\w+)', rust_code)
                type_names.update(matches)
            case "functions":
                # 在函数签名中查找类型名
                matches = re.findall(r'fn (\w+)\(', rust_code)
                type_names.update(matches)
        
        # 返回第一个找到的类型名，如果有多个的话
        return next(iter(type_names)) if type_names else None

    def _remove_duplicate_constants_from_function(self, rust_code, global_constants):
        """从函数代码中移除已在全局定义的重复常量"""
        if not global_constants:
            return rust_code
            
        lines = rust_code.split('\n')
        cleaned_lines = []
        
        for line in lines:
            line_stripped = line.strip()
            
            # 检查是否为常量定义行
            const_match = re.match(r'(\s*)(?:pub )?const (\w+):', line_stripped)
            if const_match:
                const_name = const_match.group(2)
                if const_name in global_constants:
                    # 完全跳过重复的常量定义，添加注释说明
                    cleaned_lines.append(f"{const_match.group(1)}// 重复常量 {const_name} 已在全局定义，此处移除")
                    continue
            
            # 保留其他行
            cleaned_lines.append(line)
        
        return '\n'.join(cleaned_lines)

    def _is_forward_declaration(self, rust_code, kind):
        """检查是否为前向声明"""
        rust_code_clean = rust_code.strip()
        
        # 检查结构体前向声明：struct Name;
        if rust_code_clean.startswith("struct ") and rust_code_clean.endswith(";"):
            # 确保不是完整的结构体定义（没有大括号）
            if "{" not in rust_code_clean:
                return True
        
        # 检查其他可能的前向声明模式
        if (kind in ["typedefs", "structs"] and 
            rust_code_clean.endswith(";") and 
            "{" not in rust_code_clean and
            "(" not in rust_code_clean):  # 排除函数指针
            return True
            
        return False

# 命令行接口
def main():
    """主程序入口"""
    import argparse
    import re
    
    # 定义默认参数（写死在代码中）
    default_input_path = "merged_architecture.json"
    default_output_path = os.path.join(DATA_DIR, "converted_architecture.json")
    default_max_items = 10000  # 默认处理项数
    default_api_key = "sk-Wx9RbmSNFH5Q1BbhpoVdRzoLka4ATPeO16qoDwe13YEF71qJ"
    
    # 仍然支持命令行参数，但不再要求必须提供
    parser = argparse.ArgumentParser(description="C到Rust代码转换工具")
    parser.add_argument("--input", "-i", help="输入的架构JSON文件路径")
    parser.add_argument("--output", "-o", help="输出的转换结果JSON文件路径")
    parser.add_argument("--max-items", "-m", type=int, help="最大处理项数，用于测试")
    parser.add_argument("--api-key", "-k", help="OpenAI API密钥，如不提供则从环境变量OPENAI_API_KEY获取")
    parser.add_argument("--debug", "-d", action="store_true", help="启用调试模式")
    parser.add_argument("--test", "-t", action="store_true", help="测试模式：只处理1个项目")
    parser.add_argument("--dry-run", action="store_true", help="不实际调用API，仅检查流程")
    parser.add_argument("--generate-validation", "-v", action="store_true", help="处理完成后生成验证项目")
    parser.add_argument("--validation-dir", default="validation_project", help="验证项目输出目录")
    parser.add_argument("--enable-compile-check", action="store_true", help="启用实时编译验证（需要安装Rust）")
    parser.add_argument("--max-fix-rounds", type=int, default=5, help="最大修复轮数（默认5轮）")
    
    args = parser.parse_args()
    
    # 使用命令行参数或默认值
    input_path = args.input or default_input_path
    output_path = args.output or default_output_path
    max_items = 1 if args.test else (args.max_items or default_max_items)
    
    # 配置日志级别
    if args.debug:
        for logger in [main_logger, interaction_logger, stats_logger, item_logger]:
            logger.logger.setLevel(logging.DEBUG)
    
    # 获取API密钥
    api_key = args.api_key or default_api_key
    if not api_key:
        main_logger.error("未提供API密钥，请通过--api-key参数或OPENAI_API_KEY环境变量提供")
        sys.exit(1)
    
    try:
        # 测试模式提示
        if args.test:
            main_logger.warning("⚠️ 测试模式：只处理1个项目")
            
        # 编译验证提示
        if args.enable_compile_check:
            main_logger.info("🔧 已启用实时编译验证和修复功能")
            main_logger.info("   - 每次转换后会进行编译验证")
            main_logger.info("   - 编译失败时会自动启动5轮修复流程")
            main_logger.info("   - 需要本地安装Rust (cargo命令)")
        else:
            main_logger.info("⚠️ 未启用编译验证，转换后需要手动验证")
            
        # Dry Run模式
        if args.dry_run:
            main_logger.warning("⚠️ DRY-RUN模式：不会实际调用API")
            # 模拟GPT类
            class MockGPT:
                def __init__(self, *args, **kwargs):
                    self.call_count = 0
                    self.total_tokens_in = 0
                    self.total_tokens_out = 0
                
                def ask(self, messages, **kwargs):
                    self.call_count += 1
                    self.total_tokens_in += 100
                    self.total_tokens_out += 50
                    return "```rust\n// 模拟的Rust代码\npub struct TestStruct {\n    field: i32\n}\n```"
                
                def get_stats(self):
                    return {
                        "calls": self.call_count,
                        "tokens_in": self.total_tokens_in,
                        "tokens_out": self.total_tokens_out,
                        "total_tokens": self.total_tokens_in + self.total_tokens_out
                    }
                    
            # 替换GPT类
            global GPT
            real_GPT = GPT
            GPT = MockGPT
        
        # 初始化转换器
        main_logger.info("初始化转换器...")
        converter = C2RustConverter(api_key, args.enable_compile_check, args.max_fix_rounds)
        
        # 开始处理
        main_logger.info(f"使用输入文件: {input_path}")
        main_logger.info(f"将输出到: {output_path}")
        main_logger.info(f"最大处理项数: {max_items}")
        
        result = converter.process_architecture_file(
            input_path,
            output_path,
            max_items
        )
        
        main_logger.info("转换完成!")
        main_logger.info(f"共处理项目保存到: {output_path}")
        
        # 生成验证项目
        if args.generate_validation:
            main_logger.info("正在生成函数签名验证项目...")
            validation_dir = converter.generate_validation_project(result, args.validation_dir)
            main_logger.info(f"验证项目已生成到: {validation_dir}")
            main_logger.info("要验证签名正确性，请执行:")
            main_logger.info(f"  cd {validation_dir}")
            main_logger.info("  cargo check")
        
        # 恢复原始GPT类
        if args.dry_run:
            GPT = real_GPT
        
    except Exception as e:
        main_logger.error(f"程序执行出错: {str(e)}")
        main_logger.error(traceback.format_exc())
        sys.exit(1)

# 单个文件转换函数（方便直接在代码中调用）
def convert_single_code(c_code, kind, api_key=None, model="gpt-4o"):
    """转换单个C代码片段为Rust代码"""
    api_key = api_key or os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("未提供API密钥，请提供api_key参数或设置OPENAI_API_KEY环境变量")
    
    converter = C2RustConverter(api_key)
    result = converter.convert_with_dependencies("single_code", kind, c_code)
    
    return result

# 用于导入其他Python模块时使用的API
def enrich_architecture_with_rust(input_path, output_path=None, api_key=None, max_items=None):
    """将项目架构JSON文件中的C代码转换为Rust代码"""
    api_key = api_key or os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("未提供API密钥，请提供api_key参数或设置OPENAI_API_KEY环境变量")
    
    converter = C2RustConverter(api_key)
    return converter.process_architecture_file(input_path, output_path, max_items)

if __name__ == "__main__":
    main() 