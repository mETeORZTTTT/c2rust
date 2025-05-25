#!/usr/bin/env python3

from typing import Dict, Set, Any, List, Tuple

class DependencyResolver:
    """依赖关系解析器，处理项目间的依赖关系"""
    
    def __init__(self):
        self.processed_items = set()
        self.processing_items = set()
    
    def is_dependency_processed(self, dep_id: str, dep_info: Dict[str, Any], 
                               data: Dict[str, Any], processed_items: Set[str],
                               processing_items: Set[str] = None) -> bool:
        """检查依赖项是否已处理（支持跨类型搜索）"""
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
            if dep_type in data[dep_file] and dep_name in data[dep_file][dep_type]:
                item = data[dep_file][dep_type][dep_name]
                if item.get("conversion_status") == "success":
                    return True
            
            # 如果指定类型中找不到，搜索其他类型（解决类型分类错误问题）
            for actual_type in ["fields", "defines", "typedefs", "structs", "functions"]:
                if actual_type == dep_type:
                    continue  # 跳过已检查的类型
                    
                if actual_type in data[dep_file] and dep_name in data[dep_file][actual_type]:
                    item = data[dep_file][actual_type][dep_name]
                    if item.get("conversion_status") == "success":
                        # 找到了！检查是否在processed_items中
                        actual_full_id = f"{dep_file}::{actual_type}::{dep_name}"
                        if actual_full_id in processed_items:
                            # 记录类型不匹配的警告（但不影响处理）
                            print(f"⚠️ 依赖项类型不匹配: {dep_qualified_name} 期望={dep_type}, 实际={actual_type}")
                            return True
        
        return False
    
    def collect_dependency_code(self, dep_id: str, dep_info: Dict[str, Any], 
                               data: Dict[str, Any]) -> Dict[str, str]:
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
        
        # 查找依赖项（支持跨类型搜索）
        found_item = None
        found_in_type = None
        
        if dep_file in data:
            # 首先尝试指定类型
            if dep_type in data[dep_file] and dep_name in data[dep_file][dep_type]:
                item = data[dep_file][dep_type][dep_name]
                if item.get("conversion_status") == "success":
                    found_item = item
                    found_in_type = dep_type
            
            # 如果没找到，搜索其他类型
            if not found_item:
                for search_type in ["fields", "defines", "typedefs", "structs", "functions"]:
                    if search_type == dep_type:
                        continue
                    
                    if search_type in data[dep_file] and dep_name in data[dep_file][search_type]:
                        item = data[dep_file][search_type][dep_name]
                        if item.get("conversion_status") == "success":
                            found_item = item
                            found_in_type = search_type
                            break
        
        if found_item:
            rust_code = found_item.get("rust_signature", "")
            if rust_code:
                # 对于函数，确保有默认实现（用于编译验证）
                if found_in_type == "functions" or found_item.get("original_type") == "define":
                    # 如果是函数，生成默认实现用于编译验证
                    if "fn " in rust_code:
                        rust_code = self._generate_default_implementation(rust_code)
                
                dependency_code[dep_id] = rust_code
        
        return dependency_code
    
    def sort_items_by_dependencies(self, items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """按依赖关系对项目进行拓扑排序"""
        sorted_items = []
        processed = set()
        
        def can_process(item):
            # 检查是否所有依赖都已处理
            for dep_id in item.get("dependencies", {}):
                if dep_id not in processed:
                    return False
            return True
        
        remaining_items = items[:]
        max_iterations = len(items) * 2  # 防止无限循环
        iteration = 0
        
        while remaining_items and iteration < max_iterations:
            made_progress = False
            iteration += 1
            
            for i, item in enumerate(remaining_items):
                if can_process(item):
                    sorted_items.append(item)
                    processed.add(item.get("id", item.get("name", "")))
                    remaining_items.pop(i)
                    made_progress = True
                    break
            
            if not made_progress:
                # 可能有循环依赖，添加剩余项目
                print(f"⚠️ 检测到可能的循环依赖，剩余 {len(remaining_items)} 个项目")
                sorted_items.extend(remaining_items)
                break
        
        return sorted_items
    
    def find_unprocessed_items(self, data: Dict[str, Any], processed_items: Set[str]) -> List[Dict[str, Any]]:
        """查找所有未处理的项目及其依赖关系"""
        unprocessed = []
        
        for file_name, content in data.items():
            for kind in ["fields", "defines", "typedefs", "structs", "functions"]:
                if kind not in content:
                    continue
                    
                for item_name, item_data in content[kind].items():
                    full_id = f"{file_name}::{kind}::{item_name}"
                    
                    if full_id not in processed_items:
                        deps = item_data.get("dependencies", {})
                        missing_deps = []
                        
                        for dep_id, dep_info in deps.items():
                            if not self.is_dependency_processed(dep_id, dep_info, data, processed_items, set()):
                                missing_deps.append(dep_id)
                        
                        unprocessed.append({
                            "id": full_id,
                            "file": file_name,
                            "kind": kind,
                            "name": item_name,
                            "dependencies": list(deps.keys()),
                            "missing_dependencies": missing_deps,
                            "ready_to_process": len(missing_deps) == 0
                        })
        
        return unprocessed
    
    def get_processing_statistics(self, data: Dict[str, Any], processed_items: Set[str]) -> Dict[str, Any]:
        """获取处理统计信息"""
        total_items = 0
        processed_count = len(processed_items)
        
        type_stats = {}
        
        for file_name, content in data.items():
            for kind in ["fields", "defines", "typedefs", "structs", "functions"]:
                if kind not in content:
                    continue
                
                kind_total = len(content[kind])
                total_items += kind_total
                
                kind_processed = 0
                for item_name in content[kind]:
                    full_id = f"{file_name}::{kind}::{item_name}"
                    if full_id in processed_items:
                        kind_processed += 1
                
                type_stats[kind] = {
                    "total": kind_total,
                    "processed": kind_processed,
                    "remaining": kind_total - kind_processed
                }
        
        return {
            "total_items": total_items,
            "processed_items": processed_count,
            "remaining_items": total_items - processed_count,
            "by_type": type_stats
        }
    
    def _generate_default_implementation(self, rust_signature: str) -> str:
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