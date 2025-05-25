"""
跨文件验证工具模块

专门处理转换过程中的实时验证需求：
1. 在每个签名转换时立即进行编译验证
2. 智能处理跨文件依赖关系
3. 避免重复定义问题
4. 提供高效的增量验证机制
"""

import os
import subprocess
import tempfile
import re
from typing import Dict, List, Set, Optional, Tuple
import logging

# 配置日志
logger = logging.getLogger(__name__)

class CrossFileValidator:
    """跨文件编译验证器 - 强制验证每个转换项目"""
    
    def __init__(self, base_dir: str = None):
        """初始化验证器"""
        self.base_dir = base_dir or os.getcwd()
        
        # 全局已转换代码集合（去重）
        self.global_converted_items = {}  # unique_key -> CodeItem
        self.global_constants = set()  # 全局常量名集合
        self.type_definitions = {}  # type_name -> definition
        
        # 验证统计
        self.validation_stats = {
            "total_validations": 0,
            "successful_validations": 0,
            "failed_validations": 0,
            "duplicate_skipped": 0,
            "compilation_errors": []
        }
        
        # 强制验证模式 - 所有转换必须通过验证
        self.strict_mode = True
        
        logger.info("跨文件验证器初始化完成 - 严格验证模式")
    
    def validate_conversion(self, file_name: str, kind: str, item_name: str, 
                          rust_code: str, original_c_code: str = None) -> Dict:
        """
        强制验证转换结果 - 这是转换流程的必要步骤
        
        Args:
            file_name: 源文件名
            kind: 代码类型 (functions, structs, defines等)
            item_name: 项目名称
            rust_code: 生成的Rust代码
            original_c_code: 原始C代码（用于错误报告）
            
        Returns:
            Dict: {
                "success": bool,
                "errors": List[str],
                "warnings": List[str],
                "duplicate": bool,  # 是否为重复项
                "added": bool       # 是否已添加到全局集合
            }
        """
        logger.info(f"🔍 强制验证: {file_name}::{kind}::{item_name}")
        
        # 1. 检查和添加到全局集合（去重）
        unique_key = self._generate_unique_key(kind, item_name, rust_code)
        is_duplicate = unique_key in self.global_converted_items
        
        if is_duplicate:
            logger.info(f"⚠️ 跳过重复项: {item_name}")
            self.validation_stats["duplicate_skipped"] += 1
            return {
                "success": True,
                "errors": [],
                "warnings": [f"跳过重复定义: {item_name}"],
                "duplicate": True,
                "added": False
            }
        
        # 2. 添加到全局集合
        code_item = CodeItem(
            file_name=file_name,
            kind=kind,
            item_name=item_name,
            actual_name=self._extract_actual_name(rust_code, kind),
            rust_code=rust_code.strip(),
            original_type=kind
        )
        
        self.global_converted_items[unique_key] = code_item
        self._update_global_state(code_item)
        
        # 3. 强制编译验证
        validation_result = self._perform_compilation_check(
            rust_code, kind, f"{file_name}::{item_name}"
        )
        
        self.validation_stats["total_validations"] += 1
        
        if validation_result["success"]:
            self.validation_stats["successful_validations"] += 1
            logger.info(f"✅ 验证成功: {item_name}")
            return {
                "success": True,
                "errors": [],
                "warnings": validation_result.get("warnings", []),
                "duplicate": False,
                "added": True
            }
        else:
            self.validation_stats["failed_validations"] += 1
            logger.error(f"❌ 验证失败: {item_name}")
            
            # 严格模式下，验证失败是致命错误
            if self.strict_mode:
                return {
                    "success": False,
                    "errors": validation_result["errors"],
                    "warnings": validation_result.get("warnings", []),
                    "duplicate": False,
                    "added": True  # 虽然验证失败，但已添加到集合用于后续分析
                }
            else:
                logger.warning(f"⚠️ 宽松模式: 忽略验证错误")
                return {
                    "success": True,
                    "errors": [],
                    "warnings": validation_result["errors"] + validation_result.get("warnings", []),
                    "duplicate": False,
                    "added": True
                }

    def _perform_compilation_check(self, rust_code: str, item_type: str, item_name: str) -> Dict:
        """执行真实的Rust编译检查"""
        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                # 创建Cargo项目
                self._create_cargo_project(temp_dir)
                
                # 生成main.rs文件，包含所有已转换的代码
                main_rs_path = os.path.join(temp_dir, "src", "main.rs")
                self._generate_complete_validation_file(main_rs_path, rust_code, item_type, item_name)
                
                # 执行编译检查
                return self._run_cargo_check(temp_dir)
                
        except Exception as e:
            logger.error(f"编译验证异常: {e}")
            return {
                "success": False,
                "errors": [f"验证过程异常: {str(e)}"],
                "warnings": []
            }

    def _generate_complete_validation_file(self, main_rs_path: str, new_rust_code: str, 
                                         item_type: str, item_name: str):
        """生成包含所有已转换代码的完整验证文件"""
        with open(main_rs_path, 'w', encoding='utf-8') as f:
            f.write("// 自动生成的Rust代码验证文件\n")
            f.write("// 用于验证C到Rust转换的正确性\n\n")
            
            # 添加必要的允许属性
            f.write("#![allow(dead_code)]\n")
            f.write("#![allow(unused_variables)]\n")
            f.write("#![allow(unused_imports)]\n")
            f.write("#![allow(non_snake_case)]\n")
            f.write("#![allow(non_camel_case_types)]\n")
            f.write("#![allow(non_upper_case_globals)]\n\n")
            
            # 1. 首先写入所有已转换的代码（按类型排序）
            f.write("// ============ 已转换的全局定义 ============\n\n")
            
            # 按类型顺序：constants -> defines -> typedefs -> structs -> functions
            type_order = ["constants", "defines", "typedefs", "structs", "functions"]
            
            for code_type in type_order:
                items = [item for item in self.global_converted_items.values() 
                        if item.kind == code_type]
                
                if items:
                    f.write(f"// --- {code_type.upper()} ---\n")
                    for item in items:
                        f.write(f"// 来源: {item.file_name}\n")
                        f.write(f"{item.rust_code}\n\n")
            
            # 2. 然后添加当前要验证的新代码
            f.write("// ============ 当前验证项目 ============\n\n")
            f.write(f"// 类型: {item_type}, 名称: {item_name}\n")
            f.write(f"{new_rust_code}\n\n")
            
            # 3. 添加main函数和基本测试
            f.write("// ============ 验证入口 ============\n\n")
            f.write("fn main() {\n")
            f.write("    println!(\"编译验证成功!\");\n")
            f.write("}\n")

    def get_current_status(self) -> Dict:
        """获取当前验证器状态"""
        return {
            "total_items": len(self.global_converted_items),
            "by_type": self._count_by_type(),
            "validation_stats": self.validation_stats.copy(),
            "global_constants": len(self.global_constants),
            "type_definitions": len(self.type_definitions),
            "strict_mode": self.strict_mode
        }

    def _count_by_type(self) -> Dict[str, int]:
        """按类型统计项目数量"""
        counts = {}
        for item in self.global_converted_items.values():
            counts[item.kind] = counts.get(item.kind, 0) + 1
        return counts
    
    def add_converted_item(self, file_name: str, kind: str, item_name: str, 
                          rust_code: str, original_type: str = None) -> bool:
        """
        添加已转换的项目到全局集合
        
        Args:
            file_name: 源文件名
            kind: 项目类型 (defines, typedefs, structs, functions)
            item_name: 项目名称
            rust_code: 转换后的Rust代码
            original_type: 原始类型（如果有重分类）
            
        Returns:
            bool: 是否成功添加（如果重复会返回False）
        """
        # 提取实际的类型名进行去重
        actual_name = self._extract_type_name_from_rust_code(rust_code, kind)
        
        if not actual_name:
            logger.warning(f"无法从代码中提取类型名: {rust_code[:50]}...")
            actual_name = item_name
        
        # 使用实际类型名作为去重键
        unique_key = f"{kind}::{actual_name}"
        
        # 检查是否重复定义
        if unique_key in self.global_converted_items:
            existing = self.global_converted_items[unique_key]
            logger.debug(f"跳过重复定义: {actual_name} (来自 {file_name}::{kind}::{item_name}, "
                        f"已有来自 {existing.file_name}::{existing.kind}::{existing.item_name})")
            return False
        
        # 为函数生成默认实现
        if kind == "functions" or original_type == "define":
            if "fn " in rust_code:
                impl_code = self._generate_default_implementation(rust_code)
            else:
                impl_code = rust_code
        else:
            impl_code = rust_code
        
        # 创建代码项目
        code_item = CodeItem(
            file_name=file_name,
            kind=kind,
            item_name=item_name,
            actual_name=actual_name,
            rust_code=impl_code,
            original_type=original_type or kind
        )
        
        # 添加到全局集合
        self.global_converted_items[unique_key] = code_item
        
        # 如果是常量定义，添加到全局常量集合
        if kind == "defines":
            constants = re.findall(r'(?:pub )?const (\w+):', rust_code)
            self.global_constants.update(constants)
        
        # 如果是类型定义，添加到类型定义集合
        if kind in ["typedefs", "structs"]:
            self.type_definitions[actual_name] = impl_code
        
        logger.debug(f"添加转换项目: {unique_key} -> {actual_name}")
        return True
    
    def validate_rust_code(self, rust_code: str, item_type: str = "unknown", 
                          item_name: str = "unknown") -> Dict:
        """
        验证单个Rust代码片段的编译正确性
        
        Args:
            rust_code: 要验证的Rust代码
            item_type: 项目类型
            item_name: 项目名称
            
        Returns:
            Dict: 验证结果 {"success": bool, "errors": List[str], "warnings": List[str]}
        """
        self.validation_stats["total_validations"] += 1
        
        try:
            # 创建临时验证项目
            with tempfile.TemporaryDirectory() as temp_dir:
                # 创建Cargo项目结构
                self._create_cargo_project(temp_dir)
                
                # 生成包含所有已转换代码的main.rs
                main_rs_path = os.path.join(temp_dir, "src", "main.rs")
                self._generate_validation_main_rs(main_rs_path, rust_code, item_type, item_name)
                
                # 运行编译验证
                result = self._run_cargo_check(temp_dir)
                
                if result["success"]:
                    self.validation_stats["successful_validations"] += 1
                    logger.info(f"✅ 验证成功: {item_type}::{item_name}")
                else:
                    self.validation_stats["failed_validations"] += 1
                    self.validation_stats["compilation_errors"].extend(result["errors"])
                    logger.warning(f"❌ 验证失败: {item_type}::{item_name}, 错误数: {len(result['errors'])}")
                
                return result
                
        except Exception as e:
            error_msg = f"验证过程异常: {str(e)}"
            logger.error(error_msg)
            self.validation_stats["failed_validations"] += 1
            return {
                "success": False,
                "errors": [error_msg],
                "warnings": []
            }
    
    def _create_cargo_project(self, temp_dir: str):
        """创建临时Cargo项目"""
        # 创建src目录
        src_dir = os.path.join(temp_dir, "src")
        os.makedirs(src_dir, exist_ok=True)
        
        # 创建Cargo.toml
        cargo_toml = """[package]
name = "cross_file_validation"
version = "0.1.0"
edition = "2021"

[dependencies]
"""
        with open(os.path.join(temp_dir, "Cargo.toml"), "w") as f:
            f.write(cargo_toml)
    
    def _generate_validation_main_rs(self, main_rs_path: str, current_rust_code: str, 
                                   item_type: str, item_name: str):
        """生成包含所有已转换代码的main.rs文件"""
        with open(main_rs_path, "w", encoding="utf-8") as f:
            # 写入文件头
            f.write("// 自动生成的跨文件验证代码\n")
            f.write("#![allow(unused_variables, dead_code, unused_imports, ")
            f.write("non_camel_case_types, non_snake_case, non_upper_case_globals)]\n\n")
            
            # 添加常用导入
            f.write("use std::os::raw::*;\n")
            f.write("use std::ptr;\n")
            f.write("use std::any::Any;\n")
            f.write("use std::ffi::c_void;\n\n")
            
            f.write("fn main() {}\n\n")
            
            # 按类型顺序输出已转换的代码
            type_order = ["fields", "defines", "typedefs", "structs", "functions"]
            
            for kind in type_order:
                kind_items = [
                    (key, item) for key, item in self.global_converted_items.items() 
                    if item.kind == kind
                ]
                
                if kind_items:
                    f.write(f"// ==================== {kind.upper()} ====================\n\n")
                    
                    for unique_key, item in kind_items:
                        f.write(f"// 来源: {item.file_name}::{item.kind}::{item.item_name}")
                        if item.original_type != item.kind:
                            f.write(f" (原类型: {item.original_type})")
                        f.write(f" -> {item.actual_name}\n")
                        f.write(f"{item.rust_code}\n\n")
            
            # 写入当前验证的代码
            f.write("// ==================== 当前验证项目 ====================\n\n")
            f.write(f"// {item_type}::{item_name} validation\n")
            
            # 清理当前代码中的重复常量定义
            current_code_clean = self._remove_duplicate_constants(current_rust_code)
            
            # 检查当前代码是否会重复定义类型
            current_type_name = self._extract_type_name_from_rust_code(current_code_clean, item_type)
            if current_type_name and current_type_name in self.type_definitions:
                f.write(f"// 警告：{current_type_name} 已在上面定义，当前代码应该只引用不重新定义\n")
            
            f.write(current_code_clean)
    
    def _run_cargo_check(self, temp_dir: str) -> Dict:
        """运行cargo check进行编译验证"""
        try:
            result = subprocess.run(
                ["cargo", "check"],
                cwd=temp_dir,
                capture_output=True,
                text=True,
                timeout=30
            )
            
            success = result.returncode == 0
            errors = self._extract_compile_errors(result.stderr) if not success else []
            warnings = self._extract_compile_warnings(result.stderr)
            
            return {
                "success": success,
                "errors": errors,
                "warnings": warnings,
                "stdout": result.stdout,
                "stderr": result.stderr
            }
            
        except subprocess.TimeoutExpired:
            return {
                "success": False,
                "errors": ["编译超时"],
                "warnings": [],
                "stdout": "",
                "stderr": "编译超时"
            }
        except FileNotFoundError:
            return {
                "success": False,
                "errors": ["未找到cargo命令，请确保已安装Rust"],
                "warnings": [],
                "stdout": "",
                "stderr": "未找到cargo命令"
            }
    
    def _extract_compile_errors(self, stderr: str) -> List[str]:
        """从编译输出中提取错误信息"""
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
            # 继续收集错误信息
            elif in_error and (line.startswith('  ') or line.startswith(' -->') or line.strip().startswith('|')):
                current_error.append(line)
            # 空行或其他内容表示错误结束
            elif in_error and (line.strip() == '' or 'warning[' in line):
                if current_error:
                    errors.append('\n'.join(current_error))
                current_error = []
                in_error = False
        
        # 添加最后一个错误
        if current_error and in_error:
            errors.append('\n'.join(current_error))
        
        return errors
    
    def _extract_compile_warnings(self, stderr: str) -> List[str]:
        """从编译输出中提取警告信息"""
        warnings = []
        lines = stderr.split('\n')
        current_warning = []
        in_warning = False
        
        for line in lines:
            # 检测警告开始
            if 'warning[' in line or line.strip().startswith('warning:'):
                if current_warning:
                    warnings.append('\n'.join(current_warning))
                current_warning = [line]
                in_warning = True
            # 继续收集警告信息
            elif in_warning and (line.startswith('  ') or line.startswith(' -->') or line.strip().startswith('|')):
                current_warning.append(line)
            # 空行或错误开始表示警告结束
            elif in_warning and (line.strip() == '' or 'error[' in line):
                if current_warning:
                    warnings.append('\n'.join(current_warning))
                current_warning = []
                in_warning = False
        
        # 添加最后一个警告
        if current_warning and in_warning:
            warnings.append('\n'.join(current_warning))
        
        return warnings
    
    def _extract_type_name_from_rust_code(self, rust_code: str, kind: str) -> Optional[str]:
        """从Rust代码中提取类型名"""
        patterns = {
            "fields": r'pub struct (\w+)',
            "defines": r'(?:pub )?const (\w+):',
            "typedefs": r'(?:pub )?type (\w+) =',
            "structs": r'(?:pub )?struct (\w+)',
            "functions": r'fn (\w+)\('
        }
        
        pattern = patterns.get(kind)
        if not pattern:
            return None
        
        matches = re.findall(pattern, rust_code)
        return matches[0] if matches else None
    
    def _remove_duplicate_constants(self, rust_code: str) -> str:
        """从代码中移除已在全局定义的重复常量"""
        if not self.global_constants:
            return rust_code
        
        lines = rust_code.split('\n')
        cleaned_lines = []
        
        for line in lines:
            line_stripped = line.strip()
            
            # 检查是否为常量定义行
            const_match = re.match(r'(\s*)(?:pub )?const (\w+):', line_stripped)
            if const_match:
                const_name = const_match.group(2)
                if const_name in self.global_constants:
                    # 跳过重复的常量定义，添加注释说明
                    indent = const_match.group(1)
                    cleaned_lines.append(f"{indent}// 重复常量 {const_name} 已在全局定义，此处移除")
                    continue
            
            # 保留其他行
            cleaned_lines.append(line)
        
        return '\n'.join(cleaned_lines)
    
    def _generate_default_implementation(self, rust_signature: str) -> str:
        """为Rust函数签名生成默认实现"""
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
    
    def get_validation_statistics(self) -> Dict:
        """获取验证统计信息"""
        return self.validation_stats.copy()
    
    def reset_global_state(self):
        """重置全局状态（用于新的验证会话）"""
        self.global_converted_items.clear()
        self.global_constants.clear()
        self.type_definitions.clear()
        self.validation_stats = {
            "total_validations": 0,
            "successful_validations": 0,
            "failed_validations": 0,
            "duplicate_skipped": 0,
            "compilation_errors": []
        }
        logger.info("全局验证状态已重置")

    def _generate_unique_key(self, kind: str, item_name: str, rust_code: str) -> str:
        """
        为转换项目生成唯一键，用于去重检查
        
        Args:
            kind: 项目类型 (defines, typedefs, structs, functions)
            item_name: 项目名称
            rust_code: Rust代码
            
        Returns:
            str: 唯一键
        """
        # 提取实际的类型名进行去重
        actual_name = self._extract_type_name_from_rust_code(rust_code, kind)
        
        if not actual_name:
            # 如果无法提取类型名，使用原始项目名
            actual_name = item_name
        
        # 使用实际类型名作为去重键
        return f"{kind}::{actual_name}"
    
    def _extract_actual_name(self, rust_code: str, kind: str) -> str:
        """
        从Rust代码中提取实际的名称
        
        Args:
            rust_code: Rust代码
            kind: 项目类型
            
        Returns:
            str: 提取的实际名称
        """
        actual_name = self._extract_type_name_from_rust_code(rust_code, kind)
        return actual_name if actual_name else "unknown"
    
    def _update_global_state(self, code_item):
        """
        更新全局状态，包括常量集合和类型定义
        
        Args:
            code_item: CodeItem实例
        """
        # 如果是常量定义，添加到全局常量集合
        if code_item.kind == "defines":
            constants = re.findall(r'(?:pub )?const (\w+):', code_item.rust_code)
            self.global_constants.update(constants)
        
        # 如果是类型定义，添加到类型定义集合
        if code_item.kind in ["typedefs", "structs"]:
            self.type_definitions[code_item.actual_name] = code_item.rust_code


class CodeItem:
    """代码项目数据类"""
    
    def __init__(self, file_name: str, kind: str, item_name: str, actual_name: str,
                 rust_code: str, original_type: str):
        self.file_name = file_name
        self.kind = kind
        self.item_name = item_name
        self.actual_name = actual_name
        self.rust_code = rust_code
        self.original_type = original_type
    
    def __repr__(self):
        return f"CodeItem({self.file_name}::{self.kind}::{self.item_name} -> {self.actual_name})"


# 便捷函数
def create_validator() -> CrossFileValidator:
    """创建跨文件验证器实例"""
    return CrossFileValidator()


def validate_single_item(validator: CrossFileValidator, rust_code: str, 
                        item_type: str, item_name: str) -> bool:
    """验证单个项目的便捷函数"""
    result = validator.validate_rust_code(rust_code, item_type, item_name)
    return result["success"] 