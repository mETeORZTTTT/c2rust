import os
import re
import subprocess
import tempfile
import logging

logger = logging.getLogger("implement")

class RustCompiler:
    """Rust代码编译验证工具"""
    
    @staticmethod
    def create_test_project(function_name, rust_implementation, dependencies_info, temp_dir=None):
        """创建临时Rust测试项目
        
        Args:
            function_name: 函数名称
            rust_implementation: Rust函数实现
            dependencies_info: 依赖项信息字典
            temp_dir: 临时目录路径，如果不提供则创建新的
            
        Returns:
            项目目录路径
        """
        # 创建临时目录
        if not temp_dir:
            temp_dir = tempfile.mkdtemp(prefix="rust_compile_")
        
        project_dir = os.path.join(temp_dir, f"test_{function_name}")
        os.makedirs(project_dir, exist_ok=True)
        os.makedirs(os.path.join(project_dir, "src"), exist_ok=True)
        
        # 创建Cargo.toml
        with open(os.path.join(project_dir, "Cargo.toml"), "w") as f:
            f.write("""
[package]
name = "rust_test"
version = "0.1.0"
edition = "2021"

[dependencies]
libc = "0.2"
""")
        
        # 跟踪已经添加的类型和函数，防止重复定义
        added_definitions = set()
        
        # 处理结构体依赖
        structs_code = ""
        for dep_id, info in dependencies_info.items():
            if info["type"] == "structs":
                # 为结构体添加C内存布局
                struct_sig = info["rust_signature"]
                if not "#[repr(C)]" in struct_sig and not "#[derive" in struct_sig:
                    struct_sig = "#[repr(C)]\n" + struct_sig
                
                # 提取结构体名称
                struct_match = re.search(r'struct\s+(\w+)', struct_sig)
                if struct_match:
                    struct_name = struct_match.group(1)
                    if struct_name not in added_definitions:
                        structs_code += f"{struct_sig}\n\n"
                        added_definitions.add(struct_name)
        
        # 处理其他类型依赖
        types_code = ""
        for dep_id, info in dependencies_info.items():
            if info["type"] in ["typedefs", "defines"]:
                # 添加类型定义
                type_sig = info["rust_signature"]
                
                # 提取类型名称
                type_match = re.search(r'type\s+(\w+)', type_sig) or re.search(r'const\s+(\w+)', type_sig)
                if type_match:
                    type_name = type_match.group(1)
                    if type_name not in added_definitions:
                        types_code += f"{type_sig}\n\n"
                        added_definitions.add(type_name)
        
        # 处理函数签名依赖
        functions_code = ""
        for dep_id, info in dependencies_info.items():
            if info["type"] == "functions":
                # 优先使用实现，如果没有则使用签名
                if info.get("rust_implementation"):
                    fn_code = info["rust_implementation"]
                    # 提取函数名称
                    fn_match = re.search(r'fn\s+(\w+)', fn_code)
                    if fn_match:
                        fn_name = fn_match.group(1)
                        if fn_name not in added_definitions:
                            functions_code += f"{fn_code}\n\n"
                            added_definitions.add(fn_name)
                else:
                    # 添加函数签名
                    fn_sig = info["rust_signature"]
                    
                    # 提取函数名称
                    fn_match = re.search(r'fn\s+(\w+)', fn_sig)
                    if fn_match:
                        fn_name = fn_match.group(1)
                        if fn_name not in added_definitions:
                            # 如果只有签名没有实现，将函数体改为unimplemented!()
                            if "{" not in fn_sig and ";" not in fn_sig:
                                fn_sig += " { unimplemented!() }"
                            functions_code += f"{fn_sig}\n\n"
                            added_definitions.add(fn_name)
        
        # 提取要实现的函数名
        target_fn_match = re.search(r'fn\s+(\w+)', rust_implementation)
        if target_fn_match:
            target_fn_name = target_fn_match.group(1)
            # 确保不会重复定义
            added_definitions.add(target_fn_name)
        
        # 创建main.rs
        with open(os.path.join(project_dir, "src", "main.rs"), "w") as f:
            f.write("""
extern crate libc;

// 基础结构体定义
""")
            # 添加结构体
            f.write(structs_code)
            
            # 添加类型定义
            f.write("// 类型定义\n")
            f.write(types_code)
            
            # 添加函数签名
            f.write("// 函数签名\n")
            f.write(functions_code)
            
            # 添加要测试的函数实现
            f.write("\n// 要测试的函数实现\n")
            f.write(f"{rust_implementation}\n\n")
            
            # 添加简单的main函数
            f.write("""
fn main() {
    println!("Compilation successful!");
}
""")
            
        return project_dir
    
    @staticmethod
    def verify_compilation(project_dir, timeout=30):
        """验证Rust代码是否能编译
        
        Args:
            project_dir: Rust项目目录
            timeout: 超时时间（秒）
            
        Returns:
            (成功标志, 错误信息)
        """
        try:
            result = subprocess.run(
                ["cargo", "check"],
                cwd=project_dir,
                capture_output=True,
                text=True,
                timeout=timeout
            )
            
            if result.returncode == 0:
                return True, "编译成功"
            else:
                return False, f"编译失败:\n{result.stderr}"
        except subprocess.TimeoutExpired:
            return False, "编译超时"
        except Exception as e:
            return False, f"编译异常: {str(e)}" 