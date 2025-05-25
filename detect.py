import json
import sys
from collections import defaultdict, deque

def detect_circular_dependencies(json_file):
    """检测JSON文件中的循环依赖"""
    # 读取JSON文件
    with open(json_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    # 构建依赖图
    dependency_graph = defaultdict(list)
    id_to_info = {}  # 用于存储项目信息，方便输出
    
    # 遍历所有项目，构建依赖关系图
    for file_name, file_content in data.items():
        for kind in ["fields", "defines", "typedefs", "structs", "functions"]:
            if kind not in file_content:
                continue
                
            for item_name, item in file_content[kind].items():
                # 构建项目ID
                item_id = f"{file_name}::{kind}::{item_name}"
                
                # 存储项目信息
                id_to_info[item_id] = {
                    "file": file_name,
                    "type": kind,
                    "name": item_name
                }
                
                # 获取依赖项
                deps = item.get("dependencies", {})
                for dep_id, dep_info in deps.items():
                    # 如果是自引用，跳过
                    if _is_self_reference(item_id, dep_id, dep_info):
                        continue
                        
                    # 规范化依赖ID
                    normalized_dep_id = _normalize_dependency_id(dep_id, dep_info)
                    
                    # 添加依赖关系
                    dependency_graph[item_id].append(normalized_dep_id)
    
    # 检测循环依赖
    circular_deps = find_circular_dependencies(dependency_graph)
    
    # 输出结果
    if circular_deps:
        print(f"发现 {len(circular_deps)} 个循环依赖:")
        for i, cycle in enumerate(circular_deps, 1):
            print(f"\n循环依赖 #{i}:")
            print("→ ".join([format_item_id(id_to_info.get(item_id, {"name": item_id})) for item_id in cycle]))
            print("详细信息:")
            for item_id in cycle:
                info = id_to_info.get(item_id, {})
                print(f"  - {format_item_id(info)}")
                print(f"    文件: {info.get('file', '未知')}")
                print(f"    类型: {info.get('type', '未知')}")
    else:
        print("未发现循环依赖")
    
    return circular_deps

def _normalize_dependency_id(dep_id, dep_info):
    """规范化依赖ID，确保格式一致"""
    if not dep_info:
        return dep_id
        
    dep_type = dep_info.get("type")
    dep_qualified_name = dep_info.get("qualified_name")
    
    if not dep_type or not dep_qualified_name:
        return dep_id
    
    dep_parts = dep_qualified_name.split("::")
    if len(dep_parts) < 2:
        return dep_id
    
    dep_file = dep_parts[0]
    dep_name = "::".join(dep_parts[1:])
    
    return f"{dep_file}::{dep_type}::{dep_name}"

def _is_self_reference(current_id, dep_id, dep_info):
    """检查依赖项是否是自引用"""
    # 直接比较ID
    if current_id == dep_id:
        return True
        
    # 比较限定名称
    if not dep_info:
        return False
        
    # 获取当前项目的名称
    current_parts = current_id.split("::")
    if len(current_parts) < 3:
        return False
        
    current_file = current_parts[0]
    current_type = current_parts[1]
    current_name = "::".join(current_parts[2:])
    
    # 获取依赖项的名称
    dep_qualified_name = dep_info.get("qualified_name")
    if not dep_qualified_name:
        return False
        
    dep_parts = dep_qualified_name.split("::")
    if len(dep_parts) < 2:
        return False
        
    dep_file = dep_parts[0]
    dep_name = "::".join(dep_parts[1:])
    
    # 检查是否是同一个项目
    if current_file == dep_file and current_name == dep_name:
        return True
        
    # 检查函数自调用（递归）
    if current_type == "functions" and dep_info.get("type") == "functions":
        # 提取函数名（不含参数）
        current_func_name = current_name.split("(")[0].strip()
        dep_func_name = dep_name.split("(")[0].strip()
        
        if current_file == dep_file and current_func_name == dep_func_name:
            return True
            
    return False

def find_circular_dependencies(graph):
    """使用DFS查找依赖图中的循环"""
    visited = set()  # 所有访问过的节点
    path = []  # 当前路径
    path_set = set()  # 当前路径中的节点集合，用于快速检查
    cycles = []  # 发现的所有循环
    
    def dfs(node):
        """深度优先搜索查找循环"""
        if node not in graph:  # 如果节点不在图中，直接返回
            return
            
        visited.add(node)
        path.append(node)
        path_set.add(node)
        
        for neighbor in graph.get(node, []):
            if neighbor in path_set:  # 发现循环
                # 提取循环路径
                idx = path.index(neighbor)
                cycle = path[idx:] + [neighbor]
                cycles.append(cycle)
            elif neighbor not in visited:
                dfs(neighbor)
        
        path_set.remove(node)
        path.pop()
    
    # 对图中的每个节点进行DFS
    # 使用list()创建一个键的副本，防止在迭代过程中修改字典
    for node in list(graph.keys()):
        if node not in visited:
            dfs(node)
    
    return cycles

def format_item_id(info):
    """格式化项目ID以便于阅读"""
    name = info.get("name", "未知")
    if "::" in name:
        # 如果是函数，只显示函数名（不含参数）
        if "(" in name:
            return name.split("(")[0].strip()
        return name.split("::")[-1]
    return name

if __name__ == "__main__":
    # 获取JSON文件路径
    json_file = sys.argv[1] if len(sys.argv) > 1 else "merged_architecture.json"
    
    try:
        detect_circular_dependencies(json_file)
    except Exception as e:
        print(f"错误: {str(e)}")
        import traceback
        traceback.print_exc()