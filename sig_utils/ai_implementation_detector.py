"""
AI实现检测器模块

专门用于检测AI生成的代码中是否有额外的实现：
1. 函数是否被实际实现（应该只有占位符）
2. 是否重定义了依赖项
3. 是否包含了复杂的业务逻辑
"""

import json
import logging
import re  # 添加re模块导入
from typing import Dict, List, Optional
from .gpt_client import GPT

logger = logging.getLogger(__name__)

class AIImplementationDetector:
    """AI实现检测器 - 用AI检测AI的额外实现"""
    
    def __init__(self, api_key: str):
        """初始化检测器"""
        self.detector_ai = GPT(api_key, model_name="gpt-4o")
        self.stats = {
            "total_checks": 0,
            "implementations_detected": 0,
            "redefinitions_detected": 0,
            "clean_code_count": 0
        }
        logger.info("AI实现检测器初始化完成")
    
    def detect_extra_implementation(self, rust_code: str, code_type: str, 
                                  dependencies: List[str] = None) -> Dict:
        """
        检测Rust代码中是否有额外的实现
        
        Args:
            rust_code: 要检测的Rust代码
            code_type: 代码类型 (functions, structs, defines等)
            dependencies: 已知的依赖项列表
            
        Returns:
            Dict: {
                "has_implementation": bool,      # 是否有具体实现
                "has_redefinition": bool,        # 是否重定义依赖项
                "is_clean": bool,                # 代码是否干净
                "violations": List[str],         # 违规列表
                "severity": str,                 # 严重程度: "none", "minor", "major"
                "recommendation": str            # 修复建议
            }
        """
        self.stats["total_checks"] += 1
        
        # 只对函数类型进行实现检测，其他类型应该有完整实现
        if code_type != "functions":
            # 对于非函数类型，只检查重定义问题，不检查实现
            logger.info(f"跳过非函数类型的实现检测: {code_type}")
            
            # 检查重定义
            has_redefinition = False
            violations = []
            
            if dependencies:
                # 简单检查是否重定义了依赖项
                for dep in dependencies:
                    if dep in rust_code:
                        has_redefinition = True
                        violations.append(f"可能重定义了依赖项: {dep}")
            
            result = {
                "has_implementation": False,  # 非函数类型允许有实现
                "has_redefinition": has_redefinition,
                "is_clean": not has_redefinition,
                "violations": violations,
                "severity": "major" if has_redefinition else "none",
                "recommendation": "代码符合要求" if not has_redefinition else "请检查重定义问题"
            }
            
            if result["is_clean"]:
                self.stats["clean_code_count"] += 1
            if result["has_redefinition"]:
                self.stats["redefinitions_detected"] += 1
            
            return result
        
        # 只对函数类型进行完整的AI检测
        detection_prompt = self._build_detection_prompt(rust_code, code_type, dependencies)
        
        try:
            # 让AI检测实现
            response = self.detector_ai.ask([
                {"role": "system", "content": self._get_detector_system_prompt()},
                {"role": "user", "content": detection_prompt}
            ])
            
            # 解析检测结果
            result = self._parse_detection_result(response)
            
            # 更新统计
            if result["has_implementation"]:
                self.stats["implementations_detected"] += 1
            if result["has_redefinition"]:
                self.stats["redefinitions_detected"] += 1
            if result["is_clean"]:
                self.stats["clean_code_count"] += 1
            
            logger.info(f"AI检测完成: 实现={result['has_implementation']}, "
                       f"重定义={result['has_redefinition']}, "
                       f"干净={result['is_clean']}")
            
            return result
            
        except Exception as e:
            logger.error(f"AI检测过程出错: {e}")
            return {
                "has_implementation": False,
                "has_redefinition": False,
                "is_clean": True,
                "violations": [f"检测过程出错: {str(e)}"],
                "severity": "none",
                "recommendation": "无法检测，建议手动检查"
            }
    
    def _build_detection_prompt(self, rust_code: str, code_type: str, 
                              dependencies: List[str] = None) -> str:
        """构建检测提示"""
        dependencies_text = ""
        if dependencies:
            dependencies_text = f"""
## 已知依赖项
以下是已存在的依赖项，不应该重新定义：
{chr(10).join(f"- {dep}" for dep in dependencies)}
"""
        
        return f"""请检测以下Rust函数代码是否包含额外的实现。

## 代码类型
{code_type} (函数类型)

## 待检测的Rust代码
```rust
{rust_code}
```

{dependencies_text}

## 检测标准（仅适用于函数）

### 1. 函数实现检测
- ✅ 允许：`unimplemented!()`, `todo!()`, `panic!()`, 简单返回值 (如 `0`, `false`, `None`)
- ❌ 禁止：具体的业务逻辑、算法实现、复杂运算、函数调用、变量定义

### 2. 重定义检测  
- ❌ 禁止：重新定义已知的依赖项
- ✅ 允许：定义新的函数

### 3. 复杂度检测
- ❌ 禁止：复杂的控制流 (if/for/while)、多行实现、算术运算、局部变量
- ✅ 允许：简单的函数签名和占位符

**重要说明：这个检测只针对函数类型。函数应该只包含签名和简单占位符，不应该有具体的业务逻辑实现。**

请以JSON格式返回检测结果：

```json
{{
  "has_implementation": false,
  "has_redefinition": false,
  "is_clean": true,
  "violations": [],
  "severity": "none",
  "recommendation": "代码符合要求"
}}
```

只返回JSON，不要其他文本。"""
    
    def _get_detector_system_prompt(self) -> str:
        """获取检测器的系统提示"""
        return """你是一个专业的Rust函数代码实现检测器。你的任务是检测函数代码中是否包含了不应该有的具体实现。

检测原则（仅适用于函数类型）：
1. **函数签名转换**：函数应该只有签名和简单占位符，不应该有具体的业务逻辑实现
2. **不检测其他类型**：不检测结构体、类型别名、常量定义等，只检测函数
3. **占位符实现**：函数体应该使用 unimplemented!()、todo!() 或简单返回值
4. **依赖项检查**：不应该重新定义已存在的依赖项

你的检测要**严格且准确**，任何超出简单函数签名转换的实现都应该被标记。

**重要**：这个检测器只用于函数类型，其他类型（defines、structs、typedefs）应该有完整实现。

输出格式必须是标准JSON，包含所有必需字段。"""
    
    def _parse_detection_result(self, response: str) -> Dict:
        """解析AI的检测结果"""
        try:
            # 尝试提取JSON
            import re
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if json_match:
                result_json = json.loads(json_match.group())
                
                # 验证必需字段
                required_fields = ["has_implementation", "has_redefinition", "is_clean", 
                                 "violations", "severity", "recommendation"]
                
                for field in required_fields:
                    if field not in result_json:
                        result_json[field] = False if field.startswith("has_") or field == "is_clean" else []
                
                # 统一处理violations格式：确保始终是字符串列表
                violations = result_json.get("violations", [])
                if violations:
                    normalized_violations = []
                    for violation in violations:
                        if isinstance(violation, dict):
                            # 如果是字典，提取有用的信息转换为字符串
                            if "details" in violation:
                                normalized_violations.append(violation["details"])
                            elif "description" in violation:
                                normalized_violations.append(violation["description"])
                            else:
                                # 其他字典格式，转换为描述性字符串
                                violation_type = violation.get("type", "未知违规")
                                violation_msg = violation.get("message", str(violation))
                                normalized_violations.append(f"{violation_type}: {violation_msg}")
                        else:
                            # 如果已经是字符串，直接使用
                            normalized_violations.append(str(violation))
                    result_json["violations"] = normalized_violations
                
                return result_json
            else:
                # JSON解析失败，尝试简单解析
                return self._fallback_parse(response)
                
        except json.JSONDecodeError:
            return self._fallback_parse(response)
    
    def _fallback_parse(self, response: str) -> Dict:
        """备用解析方法"""
        # 简单的关键词检测
        response_lower = response.lower()
        
        has_impl = any(keyword in response_lower for keyword in [
            "has_implementation", "implementation", "具体实现", "业务逻辑"
        ])
        
        has_redef = any(keyword in response_lower for keyword in [
            "has_redefinition", "redefinition", "重定义", "重复定义"
        ])
        
        return {
            "has_implementation": has_impl,
            "has_redefinition": has_redef,
            "is_clean": not (has_impl or has_redef),
            "violations": ["AI检测结果解析失败"],
            "severity": "major" if (has_impl or has_redef) else "none",
            "recommendation": "建议手动检查代码"
        }
    
    def get_stats(self) -> Dict:
        """获取检测统计"""
        return self.stats.copy()
    
    def reset_stats(self):
        """重置统计"""
        self.stats = {
            "total_checks": 0,
            "implementations_detected": 0,
            "redefinitions_detected": 0,
            "clean_code_count": 0
        }


class SimpleImplementationChecker:
    """简单的实现检查器（不依赖AI，作为备用）"""
    
    @staticmethod
    def quick_check(rust_code: str, code_type: str = "functions") -> Dict:
        """快速检查代码是否有明显的实现"""
        violations = []
        
        # 只检查函数类型
        if code_type != "functions":
            return {
                "has_implementation": False,  # 非函数类型允许有实现
                "has_redefinition": False,    # 简单检查器不检查重定义
                "is_clean": True,
                "violations": [],
                "severity": "none",
                "recommendation": "非函数类型，允许完整实现"
            }
        
        # 检查明显的实现模式（仅用于函数）
        forbidden_patterns = [
            (r'\w+\s*\+\s*\w+', "算术运算"),
            (r'if\s+\w+', "条件判断"),
            (r'for\s+\w+', "循环"),
            (r'while\s+\w+', "while循环"),
            (r'let\s+\w+\s*=', "变量定义"),
            (r'\w+\.\w+\(', "方法调用"),
            (r'impl\s+\w+', "实现块"),
        ]
        
        for pattern, description in forbidden_patterns:
            if re.search(pattern, rust_code):
                violations.append(description)
        
        # 检查函数体长度
        if "fn " in rust_code:
            lines = [line.strip() for line in rust_code.split('\n') if line.strip()]
            if len(lines) > 4:  # 函数签名 + 开括号 + 占位符 + 闭括号
                violations.append("函数体过长")
        
        has_implementation = len(violations) > 0
        
        return {
            "has_implementation": has_implementation,
            "has_redefinition": False,  # 简单检查器不检查重定义
            "is_clean": not has_implementation,
            "violations": violations,
            "severity": "major" if len(violations) > 2 else ("minor" if violations else "none"),
            "recommendation": "发现可能的实现，建议简化" if violations else "代码看起来正常"
        }


# 全局检测器实例
_global_detector = None

def get_detector(api_key: str) -> AIImplementationDetector:
    """获取全局检测器实例"""
    global _global_detector
    if _global_detector is None:
        _global_detector = AIImplementationDetector(api_key)
    return _global_detector

def detect_implementation(rust_code: str, code_type: str, api_key: str,
                         dependencies: List[str] = None) -> Dict:
    """便捷的检测函数"""
    detector = get_detector(api_key)
    return detector.detect_extra_implementation(rust_code, code_type, dependencies)

def quick_check_implementation(rust_code: str, code_type: str = "functions") -> Dict:
    """快速检查实现（不使用AI）"""
    return SimpleImplementationChecker.quick_check(rust_code, code_type) 