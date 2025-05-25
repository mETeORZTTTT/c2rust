#!/usr/bin/env python3

import tempfile
import subprocess
import os
import re
from typing import Dict, List, Any, Tuple

class CompilerValidator:
    """编译验证器，支持单文件和跨文件依赖验证"""
    
    def __init__(self):
        self.temp_dirs = []  # 跟踪临时目录，用于清理
    
    def validate_single_code(self, rust_code: str, dependencies: Dict[str, str] = None) -> Dict[str, Any]:
        """验证单个代码片段（原有功能，保持兼容性）"""
        return self._compile_in_temp_project(rust_code, dependencies or {})
    
    def validate_architecture_project(self, data: Dict[str, Any], output_dir: str = None) -> Dict[str, Any]:
        """验证整个架构项目，生成完整的Rust项目结构"""
        if not output_dir:
            temp_dir = tempfile.mkdtemp(prefix="rust_validation_")
            self.temp_dirs.append(temp_dir)
            output_dir = temp_dir
        
        print(f"=== 生成验证项目: {output_dir} ===")
        
        # 创建项目结构
        self._create_project_structure(output_dir, data)
        
        # 编译验证
        compile_result = self._compile_project(output_dir)
        
        return {
            "success": compile_result["success"],
            "project_dir": output_dir,
            "compile_result": compile_result,
            "files_generated": self._count_generated_files(output_dir)
        }
    
    def _create_project_structure(self, project_dir: str, data: Dict[str, Any]):
        """创建完整的Rust项目结构"""
        # 创建基本目录
        os.makedirs(project_dir, exist_ok=True)
        src_dir = os.path.join(project_dir, "src")
        os.makedirs(src_dir, exist_ok=True)
        
        # 创建Cargo.toml
        self._create_cargo_toml(project_dir)
        
        # 按文件分组创建模块
        file_modules = {}
        
        for file_name, content in data.items():
            # 生成模块名（将文件名转换为合法的Rust模块名）
            module_name = self._file_name_to_module_name(file_name)
            
            # 收集文件中的所有成功转换项目
            file_items = self._collect_file_items(content)
            
            if file_items:
                file_modules[module_name] = {
                    "original_file": file_name,
                    "items": file_items
                }
        
        # 生成每个模块文件
        for module_name, module_info in file_modules.items():
            module_path = os.path.join(src_dir, f"{module_name}.rs")
            self._create_module_file(module_path, module_info)
        
        # 生成主文件（lib.rs）
        self._create_lib_rs(src_dir, file_modules)
        
        print(f"✅ 生成了 {len(file_modules)} 个模块文件")
    
    def _create_cargo_toml(self, project_dir: str):
        """创建Cargo.toml文件"""
        cargo_toml = """[package]
name = "c2rust-validation"
version = "0.1.0"
edition = "2021"

[dependencies]
"""
        with open(os.path.join(project_dir, "Cargo.toml"), "w") as f:
            f.write(cargo_toml)
    
    def _file_name_to_module_name(self, file_name: str) -> str:
        """将文件名转换为合法的Rust模块名"""
        # 移除扩展名
        name = os.path.splitext(file_name)[0]
        # 替换非法字符
        name = re.sub(r'[^a-zA-Z0-9_]', '_', name)
        # 确保以字母或下划线开头
        if name and name[0].isdigit():
            name = f"_{name}"
        return name or "unknown"
    
    def _collect_file_items(self, content: Dict[str, Any]) -> List[Dict[str, Any]]:
        """收集文件中的所有已转换项目"""
        items = []
        
        # 按依赖顺序排列类型
        for kind in ["fields", "defines", "typedefs", "structs", "functions"]:
            if kind not in content:
                continue
                
            for item_name, item_data in content[kind].items():
                if item_data.get("conversion_status") == "success":
                    rust_code = item_data.get("rust_signature", "")
                    if rust_code and rust_code.strip():
                        
                        # 为函数生成默认实现
                        if kind == "functions" or item_data.get("original_type") == "define":
                            if "fn " in rust_code and not "{" in rust_code:
                                impl_code = self._generate_default_implementation(rust_code)
                            else:
                                impl_code = rust_code
                        else:
                            impl_code = rust_code
                        
                        items.append({
                            "name": item_name,
                            "kind": kind,
                            "code": impl_code,
                            "original_type": item_data.get("original_type", kind),
                            "dependencies": item_data.get("dependencies", {})
                        })
        
        return items
    
    def _create_module_file(self, module_path: str, module_info: Dict[str, Any]):
        """创建单个模块文件"""
        with open(module_path, "w", encoding="utf-8") as f:
            f.write(f"// 从 {module_info['original_file']} 转换的Rust模块\n")
            f.write("#![allow(unused_variables, dead_code, unused_imports, non_camel_case_types, non_snake_case, non_upper_case_globals)]\n\n")
            
            # 添加常用导入
            f.write("use std::os::raw::*;\n")
            f.write("use std::ptr;\n")
            f.write("use std::ffi::c_void;\n\n")
            
            # 按类型分组输出
            current_kind = None
            for item in module_info["items"]:
                if item["kind"] != current_kind:
                    current_kind = item["kind"]
                    f.write(f"// ==================== {current_kind.upper()} ====================\n\n")
                
                f.write(f"// {item['name']}")
                if item["original_type"] != item["kind"]:
                    f.write(f" (原类型: {item['original_type']})")
                
                # 显示依赖关系
                if item["dependencies"]:
                    deps = list(item["dependencies"].keys())
                    f.write(f" [依赖: {', '.join(deps[:3])}{'...' if len(deps) > 3 else ''}]")
                
                f.write("\n")
                f.write(f"{item['code']}\n\n")
    
    def _create_lib_rs(self, src_dir: str, file_modules: Dict[str, Dict[str, Any]]):
        """创建lib.rs主文件"""
        lib_path = os.path.join(src_dir, "lib.rs")
        
        with open(lib_path, "w", encoding="utf-8") as f:
            f.write("// C到Rust转换验证库\n")
            f.write("#![allow(unused_variables, dead_code, unused_imports, non_camel_case_types, non_snake_case, non_upper_case_globals)]\n\n")
            
            # 声明所有模块
            f.write("// 模块声明\n")
            for module_name in sorted(file_modules.keys()):
                f.write(f"pub mod {module_name};\n")
            
            f.write("\n// 重新导出主要类型和函数\n")
            for module_name, module_info in file_modules.items():
                f.write(f"pub use {module_name}::*;\n")
            
            f.write("""
#[cfg(test)]
mod tests {
    use super::*;
    
    #[test]
    fn test_compilation() {
        // 这个测试只是为了验证所有代码能够编译通过
        println!("所有转换代码编译通过！");
    }
}
""")
    
    def _compile_project(self, project_dir: str) -> Dict[str, Any]:
        """编译整个项目"""
        try:
            # 先尝试cargo check（更快）
            result = subprocess.run(
                ["cargo", "check"],
                cwd=project_dir,
                capture_output=True,
                text=True,
                timeout=60
            )
            
            if result.returncode == 0:
                # 如果check通过，再尝试build（确保真的能编译）
                build_result = subprocess.run(
                    ["cargo", "build"],
                    cwd=project_dir,
                    capture_output=True,
                    text=True,
                    timeout=120
                )
                
                return {
                    "success": build_result.returncode == 0,
                    "check_stderr": result.stderr,
                    "build_stderr": build_result.stderr,
                    "stdout": build_result.stdout,
                    "errors": self._extract_compile_errors(build_result.stderr) if build_result.returncode != 0 else []
                }
            else:
                return {
                    "success": False,
                    "check_stderr": result.stderr,
                    "build_stderr": "",
                    "stdout": result.stdout,
                    "errors": self._extract_compile_errors(result.stderr)
                }
                
        except subprocess.TimeoutExpired:
            return {
                "success": False,
                "error": "编译超时",
                "errors": ["编译超时"]
            }
        except FileNotFoundError:
            return {
                "success": False,
                "error": "未找到cargo命令，请确保已安装Rust",
                "errors": ["未找到cargo命令"]
            }
    
    def _compile_in_temp_project(self, rust_code: str, dependencies: Dict[str, str]) -> Dict[str, Any]:
        """在临时项目中编译单个代码片段（保持原有兼容性）"""
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
                f.write("// 自动生成的编译验证代码\n")
                f.write("#![allow(unused_variables, dead_code, unused_imports, non_camel_case_types, non_snake_case, non_upper_case_globals)]\n\n")
                
                # 添加常用导入
                f.write("use std::os::raw::*;\n")
                f.write("use std::ptr;\n")
                f.write("use std::ffi::c_void;\n\n")
                
                f.write("fn main() {}\n\n")
                
                # 添加依赖项
                if dependencies:
                    f.write("// ==================== 依赖项 ====================\n\n")
                    for dep_id, dep_code in dependencies.items():
                        f.write(f"// 依赖项: {dep_id}\n")
                        f.write(f"{dep_code}\n\n")
                
                f.write("// ==================== 当前验证项目 ====================\n\n")
                f.write(rust_code)
            
            # 编译
            return self._compile_project(temp_dir)
    
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
        
        return errors
    
    def _count_generated_files(self, project_dir: str) -> Dict[str, int]:
        """统计生成的文件数量"""
        src_dir = os.path.join(project_dir, "src")
        if not os.path.exists(src_dir):
            return {}
        
        files = os.listdir(src_dir)
        rust_files = [f for f in files if f.endswith('.rs')]
        
        return {
            "total_files": len(rust_files),
            "module_files": len([f for f in rust_files if f != "lib.rs"]),
            "has_lib_rs": "lib.rs" in rust_files
        }
    
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
    
    def cleanup(self):
        """清理临时目录"""
        for temp_dir in self.temp_dirs:
            try:
                import shutil
                shutil.rmtree(temp_dir)
            except Exception as e:
                print(f"清理临时目录失败: {temp_dir}, 错误: {e}")
        self.temp_dirs.clear() 