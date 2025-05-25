"""
代码清理器模块

专门用于清理AI生成的代码，确保：
1. 函数只有简单签名+占位符实现
2. 移除复杂的业务逻辑
3. 禁止函数调用其他函数
4. 强制保持代码纯净性
"""

import re
import logging
from typing import Dict, List, Tuple, Optional

logger = logging.getLogger(__name__)

class CodeSanitizer:
    """代码清理器 - AI行为强制约束"""
    
    def __init__(self):
        """初始化清理器"""
        self.violation_stats = {
            "complex_functions_cleaned": 0,
            "function_calls_removed": 0,
            "complex_logic_removed": 0,
            "total_cleanups": 0
        }
        
        # 禁止的复杂模式
        self.forbidden_patterns = {
            "function_calls": [
                r'\w+\s*\(',  # 函数调用模式
                r'std::\w+',  # 标准库调用
                r'::\w+\(',   # 模块函数调用
            ],
            "complex_logic": [
                r'if\s+\w+\s*[><=!]',  # 条件判断
                r'for\s+\w+\s+in',     # 循环
                r'while\s+\w+',        # while循环
                r'match\s+\w+',        # match表达式
                r'let\s+\w+\s*=',      # 变量定义
                r'let\s+mut\s+\w+',    # 可变变量
            ],
            "complex_operations": [
                r'\w+\s*[\+\-\*\/\%]\s*\w+',  # 算术运算
                r'\w+\s*[&\|!]\s*\w+',        # 逻辑运算
                r'\w+\s*<<\s*\w+',            # 位运算
                r'\w+\s*>>\s*\w+',            # 位运算
            ]
        }
        
        # 允许的简单占位符
        self.allowed_placeholders = [
            "unimplemented!()",
            "todo!()",
            "panic!()",
            "return",
            r'return\s+\w+',  # 简单返回值
            r'\d+',           # 数字字面量
            r'true|false',    # 布尔字面量
            r'None',          # Option::None
            r'Some\(\w+\)',   # 简单Some
            r'Ok\(\w+\)',     # 简单Ok
            r'Err\(".*?"\)',  # 简单Err
        ]
    
    def sanitize_rust_code(self, rust_code: str, code_type: str) -> Dict:
        """
        清理Rust代码，移除复杂实现
        
        Args:
            rust_code: 原始Rust代码
            code_type: 代码类型 (functions, structs, defines等)
            
        Returns:
            Dict: {
                "cleaned_code": str,
                "violations_found": List[str],
                "was_modified": bool,
                "severity": str  # "none", "minor", "major"
            }
        """
        logger.debug(f"开始清理代码: {code_type}")
        
        violations = []
        cleaned_code = rust_code
        was_modified = False
        
        # 对于函数类型，进行严格清理
        if code_type == "functions" or "fn " in rust_code:
            result = self._sanitize_function(rust_code)
            cleaned_code = result["code"]
            violations.extend(result["violations"])
            was_modified = result["modified"]
        
        # 对于其他类型，进行基础清理
        else:
            result = self._sanitize_non_function(rust_code, code_type)
            cleaned_code = result["code"]
            violations.extend(result["violations"])
            was_modified = was_modified or result["modified"]
        
        # 统计违规情况
        if violations:
            self.violation_stats["total_cleanups"] += 1
            
        severity = self._assess_severity(violations)
        
        if was_modified:
            logger.warning(f"代码已清理，发现 {len(violations)} 个违规: {severity}")
            for violation in violations:
                logger.debug(f"  - {violation}")
        
        return {
            "cleaned_code": cleaned_code,
            "violations_found": violations,
            "was_modified": was_modified,
            "severity": severity
        }
    
    def _sanitize_function(self, rust_code: str) -> Dict:
        """清理函数代码"""
        violations = []
        modified = False
        
        # 解析函数签名和函数体
        functions = self._extract_functions(rust_code)
        
        if not functions:
            # 如果没有找到函数，直接返回
            return {"code": rust_code, "violations": [], "modified": False}
        
        cleaned_functions = []
        
        for func_info in functions:
            signature = func_info["signature"]
            body = func_info["body"]
            original_body = body
            
            # 检查函数体的复杂度
            complexity_violations = self._check_function_complexity(body)
            
            if complexity_violations:
                violations.extend(complexity_violations)
                # 强制替换为简单占位符
                simple_body = self._generate_simple_body(signature)
                cleaned_functions.append(f"{signature} {{\n    {simple_body}\n}}")
                modified = True
                self.violation_stats["complex_functions_cleaned"] += 1
                logger.info(f"强制清理复杂函数: {func_info['name']}")
            else:
                # 函数体简单，保持原样
                cleaned_functions.append(f"{signature} {{\n{body}\n}}")
        
        # 重新组装代码
        if modified:
            cleaned_code = "\n\n".join(cleaned_functions)
        else:
            cleaned_code = rust_code
        
        return {
            "code": cleaned_code,
            "violations": violations,
            "modified": modified
        }
    
    def _sanitize_non_function(self, rust_code: str, code_type: str) -> Dict:
        """清理非函数代码"""
        violations = []
        cleaned_code = rust_code
        modified = False
        
        # 检查是否包含不应该有的函数调用
        for pattern in self.forbidden_patterns["function_calls"]:
            if re.search(pattern, rust_code):
                violations.append(f"非函数代码中发现函数调用: {pattern}")
        
        # 对于结构体和类型定义，一般不需要特殊处理
        # 只需要确保没有函数调用或复杂逻辑
        
        return {
            "code": cleaned_code,
            "violations": violations,
            "modified": modified
        }
    
    def _extract_functions(self, rust_code: str) -> List[Dict]:
        """提取所有函数定义"""
        functions = []
        
        # 匹配函数签名和函数体
        pattern = r'((?:pub\s+)?(?:unsafe\s+)?fn\s+(\w+)\s*\([^)]*\)(?:\s*->\s*[^{]+)?)\s*\{([^}]*(?:\{[^}]*\}[^}]*)*)\}'
        
        matches = re.finditer(pattern, rust_code, re.MULTILINE | re.DOTALL)
        
        for match in matches:
            signature = match.group(1).strip()
            func_name = match.group(2)
            body = match.group(3).strip()
            
            functions.append({
                "signature": signature,
                "name": func_name,
                "body": body,
                "full_match": match.group(0)
            })
        
        return functions
    
    def _check_function_complexity(self, function_body: str) -> List[str]:
        """检查函数体的复杂度"""
        violations = []
        
        # 检查函数调用
        for pattern in self.forbidden_patterns["function_calls"]:
            matches = re.findall(pattern, function_body)
            for match in matches:
                # 排除允许的占位符
                if not self._is_allowed_placeholder(match):
                    violations.append(f"禁止的函数调用: {match}")
                    self.violation_stats["function_calls_removed"] += 1
        
        # 检查复杂逻辑
        for pattern in self.forbidden_patterns["complex_logic"]:
            if re.search(pattern, function_body):
                violations.append(f"禁止的复杂逻辑: {pattern}")
                self.violation_stats["complex_logic_removed"] += 1
        
        # 检查复杂运算
        for pattern in self.forbidden_patterns["complex_operations"]:
            if re.search(pattern, function_body):
                violations.append(f"禁止的复杂运算: {pattern}")
        
        # 检查行数（如果函数体超过3行，可能太复杂）
        lines = [line.strip() for line in function_body.split('\n') if line.strip()]
        if len(lines) > 3:
            violations.append(f"函数体过长: {len(lines)} 行，应该只有1-2行简单占位符")
        
        return violations
    
    def _is_allowed_placeholder(self, text: str) -> bool:
        """检查是否为允许的占位符"""
        text = text.strip()
        
        for placeholder_pattern in self.allowed_placeholders:
            if re.fullmatch(placeholder_pattern, text):
                return True
        
        return False
    
    def _generate_simple_body(self, function_signature: str) -> str:
        """根据函数签名生成简单的函数体"""
        # 提取返回类型
        if " -> " in function_signature:
            return_part = function_signature.split(" -> ")[1].strip()
            
            # 根据返回类型选择合适的占位符
            if return_part == "()":
                return "return"
            elif return_part in ["i32", "i64", "u32", "u64", "usize", "isize"]:
                return "0"
            elif return_part in ["f32", "f64"]:
                return "0.0"
            elif return_part == "bool":
                return "false"
            elif return_part.startswith("Option<"):
                return "None"
            elif return_part.startswith("Result<"):
                return 'Err("未实现".into())'
            elif "*" in return_part:
                return "std::ptr::null_mut()" if "mut" in return_part else "std::ptr::null()"
            else:
                return "unimplemented!()"
        else:
            # 无返回值
            return "return"
    
    def _assess_severity(self, violations: List[str]) -> str:
        """评估违规严重程度"""
        if not violations:
            return "none"
        elif len(violations) <= 2:
            return "minor"
        else:
            return "major"
    
    def get_stats(self) -> Dict:
        """获取清理统计"""
        return self.violation_stats.copy()
    
    def reset_stats(self):
        """重置统计"""
        self.violation_stats = {
            "complex_functions_cleaned": 0,
            "function_calls_removed": 0,
            "complex_logic_removed": 0,
            "total_cleanups": 0
        }


# 全局清理器实例
_global_sanitizer = None

def get_sanitizer() -> CodeSanitizer:
    """获取全局清理器实例"""
    global _global_sanitizer
    if _global_sanitizer is None:
        _global_sanitizer = CodeSanitizer()
    return _global_sanitizer

def sanitize_code(rust_code: str, code_type: str) -> Dict:
    """便捷的代码清理函数"""
    sanitizer = get_sanitizer()
    return sanitizer.sanitize_rust_code(rust_code, code_type)

def force_simple_function(rust_code: str) -> str:
    """强制简化函数实现"""
    result = sanitize_code(rust_code, "functions")
    return result["cleaned_code"] 