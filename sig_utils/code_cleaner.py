#!/usr/bin/env python3

import re
import json
from typing import Dict, List, Set, Any

class CodeCleaner:
    """代码清理工具，用于清理重复定义和优化代码结构"""
    
    def __init__(self):
        self.global_constants = set()
        self.global_types = set()
        self.global_functions = set()
    
    def clean_architecture_file(self, input_path: str, output_path: str = None) -> Dict[str, Any]:
        """清理整个架构文件，去除重复定义"""
        if not output_path:
            output_path = input_path.replace('.json', '_cleaned.json')
        
        # 读取数据
        with open(input_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        print(f"=== 开始清理架构文件 ===")
        print(f"输入: {input_path}")
        print(f"输出: {output_path}")
        
        # 第一遍：收集所有全局定义
        self._collect_global_definitions(data)
        
        print(f"收集到全局常量: {len(self.global_constants)} 个")
        print(f"收集到全局类型: {len(self.global_types)} 个")
        print(f"收集到全局函数: {len(self.global_functions)} 个")
        
        # 第二遍：清理重复定义
        cleaned_data = self._clean_all_code(data)
        
        # 保存清理后的数据
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(cleaned_data, f, indent=4, ensure_ascii=False)
        
        print(f"✅ 清理完成，结果保存到: {output_path}")
        return cleaned_data
    
    def _collect_global_definitions(self, data: Dict[str, Any]):
        """收集所有全局定义（来自defines、typedefs、structs的顶级定义）"""
        for file_name, content in data.items():
            # 收集全局常量（来自defines）
            if "defines" in content:
                for item_name, item_data in content["defines"].items():
                    if item_data.get("conversion_status") == "success":
                        rust_code = item_data.get("rust_signature", "")
                        constants = self._extract_constants_from_code(rust_code)
                        self.global_constants.update(constants)
            
            # 收集全局类型（来自typedefs和structs）
            for kind in ["typedefs", "structs"]:
                if kind in content:
                    for item_name, item_data in content[kind].items():
                        if item_data.get("conversion_status") == "success":
                            rust_code = item_data.get("rust_signature", "")
                            types = self._extract_types_from_code(rust_code, kind)
                            self.global_types.update(types)
            
            # 收集全局函数（来自functions）
            if "functions" in content:
                for item_name, item_data in content["functions"].items():
                    if item_data.get("conversion_status") == "success":
                        rust_code = item_data.get("rust_signature", "")
                        functions = self._extract_functions_from_code(rust_code)
                        self.global_functions.update(functions)
    
    def _clean_all_code(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """清理所有代码中的重复定义"""
        cleaned_data = {}
        
        for file_name, content in data.items():
            cleaned_content = {}
            
            for kind in ["fields", "defines", "typedefs", "structs", "functions"]:
                if kind not in content:
                    continue
                
                cleaned_content[kind] = {}
                
                for item_name, item_data in content[kind].items():
                    if item_data.get("conversion_status") == "success":
                        rust_code = item_data.get("rust_signature", "")
                        
                        # 清理重复定义
                        if kind == "functions" or item_data.get("original_type") == "define":
                            # 清理函数中的重复定义
                            cleaned_code = self._clean_function_code(rust_code)
                        else:
                            # 其他类型直接使用原代码
                            cleaned_code = rust_code
                        
                        # 更新清理后的代码
                        cleaned_item = item_data.copy()
                        cleaned_item["rust_signature"] = cleaned_code
                        
                        # 添加清理标记
                        if cleaned_code != rust_code:
                            cleaned_item["cleaned"] = True
                            cleaned_item["original_rust_signature"] = rust_code
                        
                        cleaned_content[kind][item_name] = cleaned_item
                    else:
                        # 未成功转换的项目直接复制
                        cleaned_content[kind][item_name] = item_data.copy()
            
            cleaned_data[file_name] = cleaned_content
        
        return cleaned_data
    
    def _clean_function_code(self, rust_code: str) -> str:
        """清理函数代码中的重复定义"""
        lines = rust_code.split('\n')
        cleaned_lines = []
        
        for line in lines:
            line_stripped = line.strip()
            
            # 检查是否为常量定义行
            const_match = re.match(r'(\s*)(?:pub )?const (\w+):', line_stripped)
            if const_match:
                const_name = const_match.group(2)
                if const_name in self.global_constants:
                    # 完全跳过重复的常量定义，添加注释说明
                    cleaned_lines.append(f"{const_match.group(1)}// 重复常量 {const_name} 已在全局定义，此处移除")
                    continue
            
            # 检查是否为类型定义行（简化版本）
            type_match = re.match(r'(\s*)(?:pub )?(?:struct|type|enum) (\w+)', line_stripped)
            if type_match:
                type_name = type_match.group(2)
                if type_name in self.global_types:
                    # 如果是在函数内部重新定义全局类型，也移除
                    cleaned_lines.append(f"{type_match.group(1)}// 重复类型 {type_name} 已在全局定义，此处移除")
                    continue
            
            # 保留其他行
            cleaned_lines.append(line)
        
        return '\n'.join(cleaned_lines)
    
    def _extract_constants_from_code(self, rust_code: str) -> Set[str]:
        """从Rust代码中提取常量名"""
        matches = re.findall(r'(?:pub )?const (\w+):', rust_code)
        return set(matches)
    
    def _extract_types_from_code(self, rust_code: str, kind: str) -> Set[str]:
        """从Rust代码中提取类型名"""
        if kind == "structs":
            matches = re.findall(r'(?:pub )?struct (\w+)', rust_code)
        elif kind == "typedefs":
            matches = re.findall(r'(?:pub )?type (\w+) =', rust_code)
        else:
            matches = []
        return set(matches)
    
    def _extract_functions_from_code(self, rust_code: str) -> Set[str]:
        """从Rust代码中提取函数名"""
        matches = re.findall(r'fn (\w+)\(', rust_code)
        return set(matches)
    
    def generate_unified_validation_file(self, data: Dict[str, Any], output_path: str = "unified_validation.rs"):
        """生成统一的验证文件，包含所有转换后的代码"""
        all_code_sections = {
            "defines": [],
            "typedefs": [],
            "structs": [],
            "functions": []
        }
        
        # 收集所有已成功转换的代码
        seen_definitions = {
            "constants": set(),    # 常量名去重
            "types": set(),        # 类型名去重
            "functions": set(),    # 函数名去重
            "forward_declarations": set(),  # 前置声明
            "full_definitions": set(),      # 完整定义
            "items": set()         # 项目ID去重
        }
        
        for file_name, content in data.items():
            # 改变处理顺序：先处理structs(完整定义)，再处理typedefs(可能的前置声明)
            for kind in ["defines", "structs", "typedefs", "functions"]:
                if kind not in content:
                    continue
                
                for item_name, item_data in content[kind].items():
                    if item_data.get("conversion_status") == "success":
                        rust_code = item_data.get("rust_signature", "")
                        if rust_code and rust_code.strip():
                            
                            # 生成唯一标识符
                            unique_id = f"{kind}::{item_name}"
                            
                            # 提取实际定义的名称
                            actual_names = self._extract_all_names_from_rust_code(rust_code, kind)
                            
                            # 检查是否有重复定义
                            has_duplicate, duplicate_info = self._check_duplicate_with_precedence(actual_names, seen_definitions)
                            
                            # 显示重复信息
                            for name, reason in duplicate_info:
                                if "replacing" in reason:
                                    print(f"✅ 替换前置声明: {name} 来自 {file_name}::{kind}::{item_name}")
                                else:
                                    print(f"⚠️ 跳过重复定义: {name} ({reason}) 来自 {file_name}::{kind}::{item_name}")
                            
                            # 如果没有重复定义，则添加
                            if not has_duplicate and unique_id not in seen_definitions["items"]:
                                # 为函数生成默认实现
                                if kind == "functions" or item_data.get("original_type") == "define":
                                    if "fn " in rust_code and not "{" in rust_code:
                                        # 添加默认实现
                                        impl_code = self._generate_default_implementation(rust_code)
                                    else:
                                        impl_code = rust_code
                                else:
                                    impl_code = rust_code
                                
                                all_code_sections[kind].append({
                                    "code": impl_code,
                                    "source": f"{file_name}::{kind}::{item_name}",
                                    "original_type": item_data.get("original_type", kind),
                                    "names": actual_names
                                })
                                
                                # 记录所有已定义的名称
                                for name_type, names in actual_names.items():
                                    seen_definitions[name_type].update(names)
                                
                                seen_definitions["items"].add(unique_id)
        
        # 生成验证文件
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write("// 统一验证文件 - 包含所有转换后的代码（已去重）\n")
            f.write("#![allow(unused_variables, dead_code, unused_imports, non_camel_case_types, non_snake_case, non_upper_case_globals)]\n\n")
            
            # 添加常用导入
            f.write("use std::os::raw::*;\n")
            f.write("use std::ptr;\n")
            f.write("use std::ffi::c_void;\n\n")
            
            f.write("fn main() {\n")
            f.write("    println!(\"验证了所有转换项目（已去重）\");\n")
            f.write("}\n\n")
            
            # 按类型顺序输出
            for kind in ["defines", "typedefs", "structs", "functions"]:
                if all_code_sections[kind]:
                    f.write(f"// ==================== {kind.upper()} ====================\n\n")
                    
                    for item in all_code_sections[kind]:
                        f.write(f"// 来源: {item['source']}")
                        if item["original_type"] != kind:
                            f.write(f" (原类型: {item['original_type']})")
                        
                        # 显示定义的名称
                        name_info = []
                        for name_type, names in item["names"].items():
                            if names:
                                name_info.append(f"{name_type}: {', '.join(sorted(names))}")
                        if name_info:
                            f.write(f" [{'; '.join(name_info)}]")
                        
                        f.write("\n")
                        f.write(f"{item['code']}\n\n")
        
        print(f"✅ 生成统一验证文件: {output_path}")
        
        # 统计信息
        total_items = sum(len(sections) for sections in all_code_sections.values())
        print(f"包含项目总数: {total_items}（已去重）")
        for kind, items in all_code_sections.items():
            if items:
                print(f"  {kind}: {len(items)} 个")
        
        # 显示去重统计
        print(f"去重统计:")
        for name_type, names in seen_definitions.items():
            if name_type != "items":
                print(f"  {name_type}: {len(names)} 个唯一定义")
    
    def _extract_all_names_from_rust_code(self, rust_code: str, kind: str) -> Dict[str, set]:
        """从Rust代码中提取所有定义的名称，按类型分类"""
        names = {
            "constants": set(),
            "types": set(),
            "functions": set(),
            "forward_declarations": set(),  # 前置声明
            "full_definitions": set()       # 完整定义
        }
        
        # 提取常量名
        const_matches = re.findall(r'(?:pub )?const (\w+):', rust_code)
        names["constants"].update(const_matches)
        
        # 提取类型名，区分前置声明和完整定义
        if kind == "structs":
            # 检查是否为前置声明（只有struct Name;格式）
            forward_struct_matches = re.findall(r'(?:pub )?struct (\w+);', rust_code)
            if forward_struct_matches:
                names["forward_declarations"].update(forward_struct_matches)
            else:
                # 完整的结构体定义
                struct_matches = re.findall(r'(?:pub )?struct (\w+)\s*\{', rust_code)
                names["full_definitions"].update(struct_matches)
            
            enum_matches = re.findall(r'(?:pub )?enum (\w+)', rust_code)
            names["types"].update(enum_matches)
        elif kind == "typedefs":
            # typedef中的前置声明
            forward_typedef_matches = re.findall(r'struct (\w+);', rust_code)
            if forward_typedef_matches:
                names["forward_declarations"].update(forward_typedef_matches)
            else:
                type_matches = re.findall(r'(?:pub )?type (\w+) =', rust_code)
                names["types"].update(type_matches)
        
        # 提取函数名
        fn_matches = re.findall(r'(?:pub )?(?:unsafe )?fn (\w+)\(', rust_code)
        names["functions"].update(fn_matches)
        
        return names
    
    def _check_duplicate_with_precedence(self, actual_names: Dict[str, set], seen_definitions: Dict[str, set]) -> tuple:
        """检查重复定义，处理前置声明vs完整定义的优先级"""
        has_duplicate = False
        duplicate_info = []
        should_skip = False  # 新增：明确标记是否应该跳过当前项目
        
        # 常量和函数直接检查重复
        for name_type in ["constants", "functions"]:
            for name in actual_names[name_type]:
                if name in seen_definitions[name_type]:
                    has_duplicate = True
                    duplicate_info.append((name, name_type))
        
        # 普通类型直接检查重复
        for name in actual_names["types"]:
            if name in seen_definitions["types"]:
                has_duplicate = True
                duplicate_info.append((name, "types"))
        
        # 处理前置声明和完整定义的优先级
        for name in actual_names["forward_declarations"]:
            # 如果已经有完整定义，跳过前置声明
            if name in seen_definitions["full_definitions"]:
                should_skip = True
                duplicate_info.append((name, "forward_declarations -> full_definitions"))
            # 如果已经有前置声明，也跳过
            elif name in seen_definitions["forward_declarations"]:
                has_duplicate = True
                duplicate_info.append((name, "forward_declarations"))
        
        for name in actual_names["full_definitions"]:
            # 完整定义总是优先，如果有前置声明则替换
            if name in seen_definitions["forward_declarations"]:
                # 移除前置声明，允许完整定义
                seen_definitions["forward_declarations"].discard(name)
                duplicate_info.append((name, "replacing forward_declaration with full_definition"))
            # 如果已经有完整定义，则跳过
            elif name in seen_definitions["full_definitions"]:
                has_duplicate = True
                duplicate_info.append((name, "full_definitions"))
        
        # 如果应该跳过或有重复定义，则返回True
        return has_duplicate or should_skip, duplicate_info
    
    def _generate_default_implementation(self, rust_signature: str) -> str:
        """为函数签名生成默认实现"""
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